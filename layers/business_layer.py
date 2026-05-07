"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LAYER 2 — BUSINESS LOGIC LAYER  (Layered Architecture)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Responsibility:
    All processing algorithms (search, stats, sentiment, JSON).
    Parallel execution via ThreadPoolExecutor.
    Uses Design Patterns — NO Streamlit imports here.

Design Patterns used here:
    Strategy  → TextExtractor dispatches to the right algorithm
    Singleton → ThreadPoolManager provides the shared executor
    Observer  → ProgressNotifier notifies all subscribed observers
    (Factory  → FileProcessorFactory lives in patterns/factory.py
                and returns functions defined in this module)
"""

import io
import json
import logging
import collections
from concurrent.futures import as_completed
from datetime import datetime
from typing import Optional

import pandas as pd

# ── Pattern imports ────────────────────────────────────────────────────────────
from patterns.strategy  import TextExtractor
from patterns.singleton import ThreadPoolManager
from patterns.observer  import ProgressNotifier, ProgressEvent

logger = logging.getLogger("MTFP.BusinessLayer")

# ── Shared TextExtractor instance (Strategy Pattern context) ───────────────────
_extractor = TextExtractor()


# ══════════════════════════════════════════════════════════════════════════════
# WORKER FUNCTIONS
# (referenced by FileProcessorFactory — keep names stable)
# ══════════════════════════════════════════════════════════════════════════════

def _worker_search(name: str, raw: bytes, query: str, case_sensitive: bool) -> list:
    """Search for query across a single file. Returns list of match rows."""
    rows = []
    try:
        # Strategy Pattern: _extractor picks TxtStrategy / CsvStrategy / PdfStrategy
        text = _extractor.extract(name, raw)
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
        logger.error(f"_worker_search({name}): {e}")
    return rows


def _worker_stats(name: str, raw: bytes) -> dict:
    """Compute statistics for a single file."""
    try:
        text       = _extractor.extract(name, raw)    # Strategy Pattern
        lines      = text.splitlines()
        words      = text.split()
        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        return {
            "File":       name,
            "Type":       name.lower().rsplit(".", 1)[-1].upper(),
            "Words":      len(words),
            "Characters": len(text),
            "Lines":      len(lines),
            "Paragraphs": max(1, len(paragraphs)),
            "Size (KB)":  round(len(raw) / 1024, 2),
        }
    except Exception as e:
        logger.error(f"_worker_stats({name}): {e}")
        return {"File": name, "Type": "?", "Words": 0,
                "Characters": 0, "Lines": 0, "Paragraphs": 0, "Size (KB)": 0}


def _worker_sentiment(name: str, raw: bytes, keyword_filter: str = "") -> dict:
    """VADER sentiment analysis for a single file."""
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()
        text = _extractor.extract(name, raw)           # Strategy Pattern

        if keyword_filter:
            kf    = keyword_filter.lower()
            lines = [l for l in text.splitlines() if kf in l.lower()]
            text  = "\n".join(lines)

        if not text.strip():
            return {"File": name, "Compound": 0, "Positive": 0,
                    "Neutral": 0, "Negative": 0, "Label": "neutral", "Word_Freq": {}}

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
        logger.error(f"_worker_sentiment({name}): {e}")
        return {"File": name, "Compound": None, "error": str(e)}


def _worker_json(name: str, raw: bytes, include_meta: bool) -> dict:
    """Convert a single file to a JSON-serialisable dict."""
    ext   = name.lower().rsplit(".", 1)[-1]
    entry: dict = {"filename": name, "type": ext.upper()}

    if include_meta:
        entry["size_bytes"]   = len(raw)
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
            text  = _extractor.extract(name, raw)      # Strategy Pattern
            pages = [{"page": i + 1, "text": t}
                     for i, t in enumerate(text.split("\n\n")) if t.strip()]
            entry["page_count"] = len(pages)
            entry["data"]       = pages

    except Exception as e:
        logger.error(f"_worker_json({name}): {e}")
        entry["error"] = str(e)
        entry["data"]  = []

    return entry


# ══════════════════════════════════════════════════════════════════════════════
# PARALLEL EXECUTOR
# Uses Singleton (shared pool) + Observer (progress events)
# ══════════════════════════════════════════════════════════════════════════════

def run_parallel(
    fn,
    tasks: list,
    label: str,
    notifier: Optional[ProgressNotifier] = None,
) -> list:
    """
    Execute fn(*task) for every task in parallel.

    Singleton Pattern → ThreadPoolManager provides the shared executor.
    Observer Pattern  → notifier.notify(event) decouples progress from UI.
    """
    results = []
    total   = len(tasks)
    if total == 0:
        return results

    # Singleton Pattern: one shared executor across all tabs
    pool = ThreadPoolManager()

    future_map = {pool.executor.submit(fn, *t): t[0] for t in tasks}
    done = 0
    for future in as_completed(future_map):
        try:
            results.append(future.result())
        except Exception as e:
            logger.error(f"Future error [{future_map[future]}]: {e}")
        done += 1

        # Observer Pattern: fire a ProgressEvent — UI observers handle rendering
        if notifier:
            notifier.notify(ProgressEvent(done=done, total=total, label=label))

    return results


def run_sequential(fn, tasks: list) -> list:
    """Single-threaded run — used only for timing comparison."""
    out = []
    for t in tasks:
        try:
            out.append(fn(*t))
        except Exception as e:
            logger.error(f"Sequential error: {e}")
    return out


def build_merged_json(entries: list, max_workers: int, indent: int) -> tuple:
    """Assemble the final merged JSON structure."""
    sorted_entries = sorted(entries, key=lambda x: x["filename"])
    final = {
        "generated_at": datetime.now().isoformat(),
        "total_files":  len(sorted_entries),
        "workers_used": max_workers,
        "files":        sorted_entries,
    }
    json_str   = json.dumps(final, ensure_ascii=False, indent=indent or None)
    json_bytes = json_str.encode("utf-8")
    total_items = sum(len(e.get("data", [])) for e in sorted_entries)
    size_kb     = len(json_bytes) / 1024
    return json_str, json_bytes, total_items, size_kb
