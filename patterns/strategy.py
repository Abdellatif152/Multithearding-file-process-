"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DESIGN PATTERN 1 — STRATEGY PATTERN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Intent:
    Define a family of algorithms, encapsulate each one,
    and make them interchangeable. The client can switch
    algorithms at runtime without changing the context.

Structure (exactly as shown in the presentation):
    TextExtractionStrategy   ← Abstract Strategy
        ├── TxtExtractionStrategy   ← Concrete Strategy A
        ├── CsvExtractionStrategy   ← Concrete Strategy B
        └── PdfExtractionStrategy   ← Concrete Strategy C

Benefit:
    Adding DOCX support needs only one new class —
    zero changes to existing code.
"""

import io
import logging
from abc import ABC, abstractmethod

import pandas as pd

logger = logging.getLogger("MTFP.Strategy")


# ─────────────────────────────────────────────────────────────
# Abstract Strategy
# ─────────────────────────────────────────────────────────────
class TextExtractionStrategy(ABC):
    """
    Abstract Strategy.
    Defines the interface every concrete extraction algorithm must follow.
    """

    @abstractmethod
    def extract(self, raw: bytes) -> str:
        """Extract plain text from raw file bytes."""

    @abstractmethod
    def supported_extension(self) -> str:
        """Return the file extension this strategy handles (e.g. 'txt')."""


# ─────────────────────────────────────────────────────────────
# Concrete Strategy A — TXT
# ─────────────────────────────────────────────────────────────
class TxtExtractionStrategy(TextExtractionStrategy):
    """Concrete Strategy A — plain text files."""

    def extract(self, raw: bytes) -> str:
        return raw.decode("utf-8", errors="replace")

    def supported_extension(self) -> str:
        return "txt"


# ─────────────────────────────────────────────────────────────
# Concrete Strategy B — CSV
# ─────────────────────────────────────────────────────────────
class CsvExtractionStrategy(TextExtractionStrategy):
    """Concrete Strategy B — CSV files."""

    def extract(self, raw: bytes) -> str:
        try:
            df = pd.read_csv(io.BytesIO(raw), on_bad_lines="skip")
            return df.to_string(index=False)
        except Exception as e:
            logger.error(f"CsvExtractionStrategy: {e}")
            return ""

    def supported_extension(self) -> str:
        return "csv"


# ─────────────────────────────────────────────────────────────
# Concrete Strategy C — PDF
# ─────────────────────────────────────────────────────────────
class PdfExtractionStrategy(TextExtractionStrategy):
    """
    Concrete Strategy C — PDF files.
    Internally tries pdfplumber first, then PyMuPDF as fallback.
    """

    def extract(self, raw: bytes) -> str:
        # Try pdfplumber
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

        # Try PyMuPDF
        try:
            import fitz
            doc = fitz.open(stream=raw, filetype="pdf")
            return "\n".join(p.get_text() for p in doc)
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"PdfExtractionStrategy(pymupdf): {e}")

        return "[No PDF backend — pip install pdfplumber]"

    def supported_extension(self) -> str:
        return "pdf"


# ─────────────────────────────────────────────────────────────
# Context — TextExtractor
# Uses whichever strategy matches the file extension.
# ─────────────────────────────────────────────────────────────
class TextExtractor:
    """
    Context class (Strategy Pattern).
    Holds a registry of strategies and delegates extraction
    to the appropriate one based on file extension.
    Client code never sees the concrete strategy classes.
    """

    def __init__(self):
        self._strategies: dict[str, TextExtractionStrategy] = {}
        # Register all concrete strategies
        for strategy in [
            TxtExtractionStrategy(),
            CsvExtractionStrategy(),
            PdfExtractionStrategy(),
        ]:
            self._strategies[strategy.supported_extension()] = strategy

    def extract(self, filename: str, raw: bytes) -> str:
        """Dispatch to the correct strategy based on file extension."""
        ext = filename.lower().rsplit(".", 1)[-1]
        strategy = self._strategies.get(ext)
        if strategy is None:
            logger.warning(f"No strategy for extension '{ext}' — returning empty.")
            return ""
        return strategy.extract(raw)

    def supported_extensions(self) -> list:
        return list(self._strategies.keys())
