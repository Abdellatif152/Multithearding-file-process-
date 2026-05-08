"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DESIGN PATTERNS MODULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Patterns implemented:
  1. Strategy Pattern  — swappable text-extraction algorithms
  2. Factory Pattern   — creates the correct Strategy at startup
  3. Observer Pattern  — progress reporting decoupled from UI
  4. Singleton Pattern — one shared ThreadPoolExecutor for all tabs
"""

import os
import io
import threading
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

logger = logging.getLogger("MTFP.Patterns")

# ══════════════════════════════════════════════════════════════
# 1. STRATEGY PATTERN — Text Extraction
#    Each file type has its own encapsulated algorithm.
#    TextExtractor (Context) picks the right one at runtime.
# ══════════════════════════════════════════════════════════════

class TextExtractionStrategy(ABC):
    """Abstract Strategy — interface every extractor must follow."""
    @abstractmethod
    def extract(self, raw: bytes) -> str: ...
    @abstractmethod
    def extension(self) -> str: ...


class TxtExtractionStrategy(TextExtractionStrategy):
    """Concrete Strategy A — plain text files."""
    def extract(self, raw: bytes) -> str:
        return raw.decode("utf-8", errors="replace")
    def extension(self) -> str:
        return "txt"


class CsvExtractionStrategy(TextExtractionStrategy):
    """Concrete Strategy B — CSV files."""
    def extract(self, raw: bytes) -> str:
        try:
            df = pd.read_csv(io.BytesIO(raw), on_bad_lines="skip")
            return df.to_string(index=False)
        except Exception as e:
            logger.error(f"CsvExtractionStrategy: {e}")
            return ""
    def extension(self) -> str:
        return "csv"


class PdfExtractionStrategy(TextExtractionStrategy):
    """Concrete Strategy C — PDF files (pdfplumber → PyMuPDF fallback)."""
    def extract(self, raw: bytes) -> str:
        try:
            import pdfplumber
            pages = []
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        pages.append(t)
            return "\n".join(pages)
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"PdfExtractionStrategy(pdfplumber): {e}")
        try:
            import fitz
            doc = fitz.open(stream=raw, filetype="pdf")
            return "\n".join(p.get_text() for p in doc)
        except Exception as e:
            logger.error(f"PdfExtractionStrategy(pymupdf): {e}")
        return "[No PDF backend — pip install pdfplumber]"
    def extension(self) -> str:
        return "pdf"


class TextExtractor:
    """
    Context (Strategy Pattern).
    Holds a registry of strategies and dispatches to the correct one
    based on file extension. Client code never touches concrete classes.
    """
    def __init__(self):
        self._strategies: dict[str, TextExtractionStrategy] = {}
        for s in [TxtExtractionStrategy(),
                  CsvExtractionStrategy(),
                  PdfExtractionStrategy()]:
            self._strategies[s.extension()] = s

    def extract(self, filename: str, raw: bytes) -> str:
        ext = filename.lower().rsplit(".", 1)[-1]
        s   = self._strategies.get(ext)
        if s is None:
            logger.warning(f"No strategy for '.{ext}'")
            return ""
        return s.extract(raw)

    def supported_extensions(self) -> list:
        return list(self._strategies.keys())


# ══════════════════════════════════════════════════════════════
# 2. FACTORY PATTERN — PDFStrategyFactory (kept for compatibility)
#    and FileProcessorFactory (returns worker functions by name)
# ══════════════════════════════════════════════════════════════

class PDFStrategyFactory:
    """Factory — auto-detects best PDF backend at startup."""
    @staticmethod
    def create() -> PdfExtractionStrategy:
        return PdfExtractionStrategy()   # strategy handles fallback internally

    @staticmethod
    def backend_name() -> str:
        try:
            import pdfplumber; return "pdfplumber"  # noqa: E401
        except ImportError:
            pass
        try:
            import fitz; return "pymupdf"           # noqa: E401
        except ImportError:
            pass
        return "none"


class FileProcessorFactory:
    """
    Factory Pattern — FileProcessorFactory.
    Tabs call FileProcessorFactory.create(task) and receive
    the correct worker without knowing its name or module.
    """
    _registry: dict = {}

    @classmethod
    def _register(cls):
        if cls._registry:
            return
        from layers.business_layer import (
            worker_search_timed, worker_stats_timed,
            worker_sentiment_timed, worker_json_timed,
        )
        cls._registry = {
            "search":    worker_search_timed,
            "stats":     worker_stats_timed,
            "sentiment": worker_sentiment_timed,
            "json":      worker_json_timed,
        }

    @classmethod
    def create(cls, task: str):
        cls._register()
        fn = cls._registry.get(task)
        if fn is None:
            raise ValueError(f"Unknown task '{task}'. Valid: {list(cls._registry)}")
        return fn


# ══════════════════════════════════════════════════════════════
# 3. OBSERVER PATTERN — Progress Reporting
#    Workers fire ProgressEvent → ProgressNotifier fans it out
#    to all subscribed observers. Workers never import Streamlit.
# ══════════════════════════════════════════════════════════════

@dataclass
class ProgressEvent:
    done:  int
    total: int
    label: str

    @property
    def ratio(self) -> float:
        return self.done / self.total if self.total > 0 else 1.0

    @property
    def text(self) -> str:
        return f"{self.label}: {self.done}/{self.total} files"


class ProgressObserver(ABC):
    """Abstract Observer."""
    @abstractmethod
    def on_progress(self, event: ProgressEvent) -> None: ...


class StreamlitProgressObserver(ProgressObserver):
    """Concrete Observer A — updates a Streamlit progress bar."""
    def __init__(self, bar):
        self._bar = bar

    def on_progress(self, event: ProgressEvent) -> None:
        try:
            self._bar.progress(event.ratio, text=event.text)
        except Exception:
            pass


class LogProgressObserver(ProgressObserver):
    """Concrete Observer B — logs to console (useful for testing)."""
    def on_progress(self, event: ProgressEvent) -> None:
        logger.info(f"[Progress] {event.text}")


class ProgressNotifier:
    """
    Subject (Observer Pattern).
    Workers call notify() — never touches UI code.
    """
    def __init__(self):
        self._observers: list[ProgressObserver] = []

    def subscribe(self, o: ProgressObserver) -> None:
        self._observers.append(o)

    def notify(self, done: int, total: int, label: str) -> None:
        ev = ProgressEvent(done=done, total=total, label=label)
        for o in self._observers:
            try:
                o.on_progress(ev)
            except Exception as e:
                logger.warning(f"Observer error: {e}")


# ══════════════════════════════════════════════════════════════
# 4. SINGLETON PATTERN — ThreadPoolManager
#    One shared ThreadPoolExecutor for the whole app.
#    Prevents thread explosion when user clicks buttons rapidly.
# ══════════════════════════════════════════════════════════════

MAX_WORKERS = min(12, (os.cpu_count() or 2) * 4)
PDF_BACKEND = PDFStrategyFactory.backend_name()


class ThreadPoolManager:
    """
    Singleton Pattern — ThreadPoolManager.
    No matter how many times ThreadPoolManager() is called,
    only ONE ThreadPoolExecutor is ever created.
    """
    _instance = None
    _lock     = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._executor = ThreadPoolExecutor(
                        max_workers=MAX_WORKERS,
                        thread_name_prefix="MTFP_Worker",
                    )
                    cls._instance = inst
                    logger.info(f"ThreadPoolManager created — max_workers={MAX_WORKERS}")
        return cls._instance

    @property
    def executor(self) -> ThreadPoolExecutor:
        return self._executor
