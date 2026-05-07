"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DESIGN PATTERN 3 — SINGLETON PATTERN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Intent:
    Ensure a class has only one instance, and provide
    a global access point to it.

Key Mechanism (exactly as in the presentation):
    1. Private class attribute _instance
    2. threading.Lock for thread safety
    3. __new__ checks before creating
    4. All callers get the same object
    5. One executor pool for the whole app

Benefit in our project:
    Prevents thread explosion when the user clicks
    buttons rapidly. All tabs share the same capped
    ThreadPoolExecutor.
"""

import os
import threading
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("MTFP.Singleton")

MAX_WORKERS = min(12, (os.cpu_count() or 2) * 4)


class ThreadPoolManager:
    """
    Singleton Pattern — ThreadPoolManager.

    No matter how many times ThreadPoolManager() is called
    (from Tab 1, Tab 2, Tab 3, Tab 4 — all at once), only
    ONE ThreadPoolExecutor is ever created.

    Usage:
        pool = ThreadPoolManager()
        pool.executor.submit(fn, *args)
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        # Double-checked locking for thread safety
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._executor = ThreadPoolExecutor(
                        max_workers=MAX_WORKERS,
                        thread_name_prefix="MTFP_Worker",
                    )
                    instance._max_workers = MAX_WORKERS
                    cls._instance = instance
                    logger.info(
                        f"ThreadPoolManager created — "
                        f"max_workers={MAX_WORKERS}"
                    )
        return cls._instance

    @property
    def executor(self) -> ThreadPoolExecutor:
        return self._executor

    @property
    def max_workers(self) -> int:
        return self._max_workers

    def shutdown(self, wait: bool = True) -> None:
        """Graceful shutdown — called on app exit."""
        self._executor.shutdown(wait=wait)
        logger.info("ThreadPoolManager shut down.")
