"""
LAYER 1 — DATA ACCESS LAYER  (Layered Architecture)
Responsibility: file I/O ONLY. No processing. No UI imports.
"""
import os
import logging

logger = logging.getLogger("MTFP.DataLayer")

ALLOWED = (".csv", ".txt", ".pdf")


class FileRepository:
    @staticmethod
    def from_folder(folder_path: str) -> dict:
        store = {}
        if not os.path.isdir(folder_path):
            logger.error(f"Folder not found: {folder_path}")
            return store
        for fname in os.listdir(folder_path):
            if fname.lower().endswith(ALLOWED):
                try:
                    with open(os.path.join(folder_path, fname), "rb") as fh:
                        store[fname] = fh.read()
                except Exception as e:
                    logger.warning(f"Cannot read '{fname}': {e}")
        return store
