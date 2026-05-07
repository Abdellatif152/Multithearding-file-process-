"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LAYER 1 — DATA ACCESS LAYER   (Layered Architecture)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Responsibility:
    File I/O ONLY.
    Reads raw bytes from uploads or the filesystem.
    No processing logic. No UI imports.

Rule:
    This layer is called by the Business Layer only.
    It never calls upward.
"""

import os
import logging

logger = logging.getLogger("MTFP.DataLayer")


class FileRepository:
    """
    Data Access Object (DAO).
    Abstracts all file I/O behind a clean interface.
    """

    ALLOWED_EXTENSIONS = (".csv", ".txt", ".pdf")

    @staticmethod
    def from_bytes(name: str, raw: bytes) -> dict:
        """Wrap raw bytes in a minimal metadata dict."""
        return {
            "name":       name,
            "raw":        raw,
            "size_bytes": len(raw),
            "ext":        name.lower().rsplit(".", 1)[-1],
        }

    @staticmethod
    def from_folder(folder_path: str) -> dict:
        """
        Load all allowed files from a folder.
        Returns {filename: bytes}.
        """
        store = {}
        if not os.path.isdir(folder_path):
            logger.error(f"Folder not found: {folder_path}")
            return store

        for fname in os.listdir(folder_path):
            if fname.lower().endswith(FileRepository.ALLOWED_EXTENSIONS):
                full = os.path.join(folder_path, fname)
                try:
                    with open(full, "rb") as fh:
                        store[fname] = fh.read()
                except Exception as e:
                    logger.warning(f"Cannot read '{fname}': {e}")

        logger.info(f"FileRepository loaded {len(store)} files from {folder_path}")
        return store
