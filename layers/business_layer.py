"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LAYER 2 — BUSINESS LOGIC LAYER  (Layered Architecture)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

All processing algorithms live here.
NO Streamlit imports — ever.

Design Patterns used:
  Strategy  → TextExtractor picks the right extraction algorithm
  Singleton → ThreadPoolManager provides the one shared executor
  Observer  → ProgressNotifier fires events to all subscribed observers
  (Factory  → FileProcessorFactory in patterns/ returns workers from here)

WHY MULTITHREADING IS FASTER (I/O-bound work):
  Python's GIL is released during I/O (file reads, sleep, network).
  time.sleep() inside _simulate_io() models real-world disk/network latency.
  With N workers, N files are processed simultaneously instead of one-by-one.
  Sequential time ≈ N × per_file_time
  Parallel  time ≈ per_file_time                 → Speedup ≈ N×
"""

import io
import json
import time
import hashlib
import logging
import collections
from concurrent.futures import as_completed
from datetime import datetime
from typing import Optional

import pandas as pd

from patterns.design_patterns import (
    TextExtractor, ProgressNotifier, ThreadPoolManager, MAX_WORKERS,
)

logger = logging.getLogger("MTFP.BusinessLayer")

# ── Shared TextExtractor (Strategy Pattern context) ────────────────────────────
_extractor = TextExtractor()


# ══════════════════════════════════════════════════════════════════════════════
# I/O SIMULATOR
# Models real-world file I/O latency (disk seeks, network, PDF parsing wait).
# time.sleep() releases the GIL → other threads run during the wait.
# Scales with file size so larger files show bigger speedup.
# ══════════════════════════════════════════════════════════════════════════════

def _simulate_io(raw: bytes) -> None:
    """Release GIL by sleeping — models real file/network I/O latency."""
    wait = min(0.08 + len(raw) / 300_000, 0.35)   # 80 ms – 350 ms per file
    time.sleep(wait)


# ══════════════════════════════════════════════════════════════════════════════
# RAW WORKER FUNCTIONS  (no I/O simulation — for production use)
# ══════════════════════════════════════════════════════════════════════════════

def worker_search(name: str, raw: bytes, query: str, case_sensitive: bool) -> list:
    """Search for query in a single file. Returns list of match dicts."""
    rows = []
    try:
        text = _extractor.extract(name, raw)          # ← Strategy Pattern
        ext  = name.lower().rsplit(".", 1)[-1].upper()
        q    = query if case_sensitive else query.lower()
        for idx, line in enumerate(text.splitlines(), start=1):
            hay   = line if case_sensitive else line.lower()
            count = hay.count(q)
            if count:
                rows.append({
                    "File":        name,
                    "Type":        ext,
                    "Line/Row":    idx,
                    "Context":     line.strip()[:150],
                    "Occurrences": count,
                })
    except Exception as e:
        logger.error(f"worker_search({name}): {e}")
    return rows


def worker_stats(name: str, raw: bytes) -> dict:
    """Compute detailed statistics for a single file."""
    try:
        text       = _extractor.extract(name, raw)    # ← Strategy Pattern
        lines      = text.splitlines()
        words      = text.split()
        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        freq       = collections.Counter(w.lower() for w in words if len(w) > 2)
        cksum      = hashlib.md5(raw).hexdigest()
        return {
            "File":       name,
            "Type":       name.lower().rsplit(".", 1)[-1].upper(),
            "Words":      len(words),
            "Characters": len(text),
            "Lines":      len(lines),
            "Paragraphs": max(1, len(paragraphs)),
            "Size (KB)":  round(len(raw) / 1024, 2),
            "Top Word":   freq.most_common(1)[0][0] if freq else "",
            "MD5":        cksum,
        }
    except Exception as e:
        logger.error(f"worker_stats({name}): {e}")
        return {"File": name, "Type": "?", "Words": 0, "Characters": 0,
                "Lines": 0, "Paragraphs": 0, "Size (KB)": 0, "Top Word": "", "MD5": ""}


def worker_sentiment(name: str, raw: bytes, keyword_filter: str = "") -> dict:
    """VADER sentiment analysis for a single file."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()
        text     = _extractor.extract(name, raw)      # ← Strategy Pattern

        if keyword_filter:
            kf    = keyword_filter.lower()
            lines = [l for l in text.splitlines() if kf in l.lower()]
            text  = "\n".join(lines)

        if not text.strip():
            return {"File": name, "Compound": 0.0, "Positive": 0.0,
                    "Neutral": 1.0, "Negative": 0.0, "Label": "neutral", "Word_Freq": {}}

        scores = analyzer.polarity_scores(text)
        label  = ("positive" if scores["compound"] >= 0.05
                  else "negative" if scores["compound"] <= -0.05
                  else "neutral")
        freq   = collections.Counter(
            w.lower().strip(".,!?;:\"'") for w in text.split() if len(w) > 3
        )
        return {
            "File":      name,
            "Compound":  round(scores["compound"], 4),
            "Positive":  round(scores["pos"],      4),
            "Neutral":   round(scores["neu"],      4),
            "Negative":  round(scores["neg"],      4),
            "Label":     label,
            "Word_Freq": dict(freq.most_common(20)),
        }
    except ImportError:
        return {"File": name, "Compound": None,
                "error": "vaderSentiment not installed — pip install vaderSentiment"}
    except Exception as e:
        logger.error(f"worker_sentiment({name}): {e}")
        return {"File": name, "Compound": None, "error": str(e)}


def worker_json(name: str, raw: bytes, include_meta: bool) -> dict:
    """Convert a single file to a JSON-serialisable dict."""
    ext   = name.lower().rsplit(".", 1)[-1]
    entry: dict = {"filename": name, "type": ext.upper()}
    if include_meta:
        entry["size_bytes"]   = len(raw)
        entry["md5"]          = hashlib.md5(raw).hexdigest()
        entry["processed_at"] = datetime.now().isoformat()
    try:
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(raw), on_bad_lines="skip")
            entry["row_count"] = len(df)
            entry["columns"]   = list(df.columns)
            entry["data"]      = df.where(df.notna(), None).to_dict(orient="records")
        elif ext == "txt":
            lines = [l for l in raw.decode("utf-8", errors="replace").splitlines()
                     if l.strip()]
            entry["line_count"] = len(lines)
            entry["data"]       = lines
        elif ext == "pdf":
            text  = _extractor.extract(name, raw)     # ← Strategy Pattern
            pages = [{"page": i + 1, "text": t}
                     for i, t in enumerate(text.split("\n\n")) if t.strip()]
            entry["page_count"] = len(pages)
            entry["data"]       = pages
    except Exception as e:
        logger.error(f"worker_json({name}): {e}")
        entry["error"] = str(e)
        entry["data"]  = []
    return entry


# ══════════════════════════════════════════════════════════════════════════════
# TIMED WORKERS  (wrap raw workers + I/O simulation)
# Used for both sequential baseline AND parallel run so comparison is fair.
# The _simulate_io() releases the GIL → threads genuinely overlap.
# ══════════════════════════════════════════════════════════════════════════════

def worker_search_timed(name: str, raw: bytes, query: str, case_sensitive: bool) -> list:
    _simulate_io(raw)
    return worker_search(name, raw, query, case_sensitive)


def worker_stats_timed(name: str, raw: bytes) -> dict:
    _simulate_io(raw)
    return worker_stats(name, raw)


def worker_sentiment_timed(name: str, raw: bytes, keyword_filter: str = "") -> dict:
    _simulate_io(raw)
    return worker_sentiment(name, raw, keyword_filter)


def worker_json_timed(name: str, raw: bytes, include_meta: bool) -> dict:
    _simulate_io(raw)
    return worker_json(name, raw, include_meta)


# ══════════════════════════════════════════════════════════════════════════════
# PARALLEL EXECUTOR
# Singleton Pattern → ThreadPoolManager (shared pool)
# Observer Pattern  → ProgressNotifier fires events without touching UI
# ══════════════════════════════════════════════════════════════════════════════

def run_parallel(fn, tasks: list, label: str,
                 notifier: Optional[ProgressNotifier] = None) -> list:
    """
    Execute fn(*task) for every task using the shared ThreadPoolExecutor.

    Singleton  → ThreadPoolManager() always returns the same pool.
    Observer   → notifier.notify() decouples progress from UI.
    """
    results = []
    total   = len(tasks)
    if total == 0:
        return results

    pool = ThreadPoolManager()                        # ← Singleton Pattern
    future_map = {pool.executor.submit(fn, *t): t[0] for t in tasks}
    done = 0
    for future in as_completed(future_map):
        try:
            results.append(future.result())
        except Exception as e:
            logger.error(f"Future error [{future_map[future]}]: {e}")
        done += 1
        if notifier:
            notifier.notify(done, total, label)       # ← Observer Pattern

    return results


def run_sequential(fn, tasks: list) -> list:
    """Single-threaded run — used for timing baseline only."""
    out = []
    for t in tasks:
        try:
            out.append(fn(*t))
        except Exception as e:
            logger.error(f"Sequential error: {e}")
    return out


def build_merged_json(entries: list, indent: int) -> tuple:
    """Assemble the final merged JSON. Returns (str, bytes, total_items, size_kb)."""
    sorted_entries = sorted(entries, key=lambda x: x["filename"])
    final = {
        "generated_at": datetime.now().isoformat(),
        "total_files":  len(sorted_entries),
        "workers_used": MAX_WORKERS,
        "files":        sorted_entries,
    }
    json_str    = json.dumps(final, ensure_ascii=False, indent=indent or None)
    json_bytes  = json_str.encode("utf-8")
    total_items = sum(len(e.get("data", [])) for e in sorted_entries)
    size_kb     = len(json_bytes) / 1024
    return json_str, json_bytes, total_items, size_kb
