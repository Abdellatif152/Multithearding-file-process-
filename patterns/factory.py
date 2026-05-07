"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DESIGN PATTERN 4 — FACTORY PATTERN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Intent:
    Define an interface for creating objects, but let
    the factory method decide which concrete class to
    instantiate. Centralises creation logic and
    decouples callers from concrete classes.

Structure (exactly as shown in the presentation):
    Tab 1 ─┐
    Tab 2 ─┤─► FileProcessorFactory.create(task) ─►  _worker_search()
    Tab 3 ─┘                                       ─►  _worker_stats()
                                                   ─►  _worker_json()

Benefits:
    Decoupled  — Tabs never import worker functions directly
    Extensible — Add a new task? Add one entry to the dict
    Centralised — All processor creation in one place
"""

import logging
from typing import Callable

logger = logging.getLogger("MTFP.Factory")


class FileProcessorFactory:
    """
    Factory Pattern — FileProcessorFactory.

    Tabs call FileProcessorFactory.create(task) and receive
    the correct worker function without knowing its name
    or module location.

    Usage (exactly as in the presentation):
        processor = FileProcessorFactory.create("search")
        results   = processor(name, raw, query, case_sensitive)
    """

    # Registry: task name → worker function
    # Import lazily to avoid circular imports at module load time
    _registry: dict[str, Callable] = {}

    @classmethod
    def _ensure_registered(cls) -> None:
        """Populate registry on first use (lazy import)."""
        if cls._registry:
            return
        from layers.business_layer import (
            _worker_search,
            _worker_stats,
            _worker_json,
            _worker_sentiment,
        )
        cls._registry = {
            "search":    _worker_search,
            "stats":     _worker_stats,
            "json":      _worker_json,
            "sentiment": _worker_sentiment,
        }
        logger.info(f"FileProcessorFactory registered tasks: {list(cls._registry)}")

    @classmethod
    def create(cls, task: str) -> Callable:
        """
        Factory method — returns the worker function for the given task.
        Raises ValueError for unknown tasks (fail-fast, not silent).
        """
        cls._ensure_registered()
        fn = cls._registry.get(task)
        if fn is None:
            raise ValueError(
                f"Unknown task '{task}'. "
                f"Valid tasks: {list(cls._registry)}"
            )
        logger.debug(f"FileProcessorFactory.create('{task}') → {fn.__name__}")
        return fn

    @classmethod
    def available_tasks(cls) -> list:
        cls._ensure_registered()
        return list(cls._registry)
