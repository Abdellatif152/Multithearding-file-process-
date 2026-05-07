"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DESIGN PATTERN 2 — OBSERVER PATTERN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Intent:
    Define a one-to-many dependency so that when one
    object (Subject) changes state, all registered
    dependents (Observers) are notified automatically.

Structure (exactly as shown in the presentation):
    Worker Thread (Producer)
        → fires event →
    ProgressNotifier (Subject)
        → carries data →
    ProgressEvent
        → updates UI →
    StreamlitProgressObserver (Concrete Observer)

Benefits:
    Decoupled  — Workers never import Streamlit
    Extensible — Add new observer without touching workers
    Testable   — Swap in a mock observer for unit tests
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger("MTFP.Observer")


# ─────────────────────────────────────────────────────────────
# Event (Data carrier)
# ─────────────────────────────────────────────────────────────
@dataclass
class ProgressEvent:
    """
    Carries progress data from Subject to Observers.
    Workers create this — they know nothing about Streamlit.
    """
    done:  int
    total: int
    label: str

    @property
    def ratio(self) -> float:
        return self.done / self.total if self.total > 0 else 1.0

    @property
    def text(self) -> str:
        return f"{self.label}: {self.done}/{self.total} files"


# ─────────────────────────────────────────────────────────────
# Abstract Observer
# ─────────────────────────────────────────────────────────────
class ProgressObserver(ABC):
    """Abstract Observer — defines the interface all observers must implement."""

    @abstractmethod
    def on_progress(self, event: ProgressEvent) -> None:
        """Called by the Subject whenever progress changes."""


# ─────────────────────────────────────────────────────────────
# Concrete Observer A — Streamlit UI
# ─────────────────────────────────────────────────────────────
class StreamlitProgressObserver(ProgressObserver):
    """
    Concrete Observer — updates a Streamlit progress bar widget.
    The business layer never imports this class or Streamlit.
    """

    def __init__(self, st_progress_widget):
        self._bar = st_progress_widget

    def on_progress(self, event: ProgressEvent) -> None:
        try:
            self._bar.progress(event.ratio, text=event.text)
        except Exception as e:
            logger.warning(f"StreamlitProgressObserver: {e}")


# ─────────────────────────────────────────────────────────────
# Concrete Observer B — Logger
# ─────────────────────────────────────────────────────────────
class LogProgressObserver(ProgressObserver):
    """
    Concrete Observer — logs progress to console.
    Useful for CLI usage, CI pipelines, or unit tests.
    Swap Streamlit with CLI? Just subscribe this observer instead.
    """

    def on_progress(self, event: ProgressEvent) -> None:
        logger.info(f"[Progress] {event.text}")


# ─────────────────────────────────────────────────────────────
# Subject — ProgressNotifier
# ─────────────────────────────────────────────────────────────
class ProgressNotifier:
    """
    Subject (Observable) in the Observer Pattern.

    Workers hold a reference to this and call notify().
    The notifier fans the event out to every subscribed observer.
    Workers NEVER know which observers are subscribed.
    """

    def __init__(self):
        self._observers: list[ProgressObserver] = []

    def subscribe(self, observer: ProgressObserver) -> None:
        """Register an observer to receive progress updates."""
        self._observers.append(observer)

    def unsubscribe(self, observer: ProgressObserver) -> None:
        """Remove a previously registered observer."""
        self._observers = [o for o in self._observers if o is not observer]

    def notify(self, event: ProgressEvent) -> None:
        """
        Fire the event — all observers are updated automatically.
        Called from inside _run_parallel() in the business layer.
        """
        for obs in self._observers:
            try:
                obs.on_progress(event)
            except Exception as e:
                logger.warning(f"Observer error: {e}")
