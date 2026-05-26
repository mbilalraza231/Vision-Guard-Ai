"""
VisionGuard AI - Storage Cleaner Background Worker

Periodically enforces storage settings:
  - retentionDays: Deletes events/alerts older than N days from the database.
  - maxStorage (GB): Deletes the oldest local video/snapshot files when the
    /shared-frames directory exceeds the configured limit.
  - autoDelete: Master switch — if False, this worker does nothing.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# How often the cleaner wakes up and checks storage (in seconds)
CLEANER_INTERVAL_SECONDS = 3600  # 1 hour


class StorageCleaner:
    """
    Background async task that enforces the storage settings configured
    by the administrator in the Settings → Storage page.
    """

    def __init__(self, shared_frames_dir: str = "/shared-frames"):
        self.shared_frames_dir = shared_frames_dir
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task = None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def start(self):
        """Launch the background cleaner task."""
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="storage-cleaner")
        logger.info("StorageCleaner started (interval: %ds)", CLEANER_INTERVAL_SECONDS)

    async def stop(self):
        """Gracefully stop the background cleaner task."""
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        logger.info("StorageCleaner stopped")

    # ------------------------------------------------------------------ #
    # Main Loop                                                            #
    # ------------------------------------------------------------------ #

    async def _run(self):
        """Main loop — sleep for CLEANER_INTERVAL_SECONDS between each run."""
        # Run once immediately on start, then on interval
        while not self._stop_event.is_set():
            try:
                await self._run_cycle()
            except Exception as exc:
                logger.error("StorageCleaner cycle failed: %s", exc, exc_info=True)

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=CLEANER_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                pass  # Normal — means the interval elapsed, run again

    async def _run_cycle(self):
        """Single cleanup cycle — reads settings and applies all rules."""
        settings = await self._fetch_storage_settings()
        auto_delete = settings.get("autoDelete", False)

        if not auto_delete:
            logger.debug("StorageCleaner: autoDelete is OFF — skipping cycle")
            return

        retention_days = int(settings.get("retentionDays", 30))
        max_storage_gb = float(settings.get("maxStorage", 50))

        logger.info(
            "StorageCleaner cycle: retentionDays=%d, maxStorageGB=%.1f",
            retention_days, max_storage_gb
        )

        # Enforce retention policy
        await self._enforce_retention(retention_days)

        # Enforce disk usage limit
        await self._enforce_max_storage(max_storage_gb)

    # ------------------------------------------------------------------ #
    # Settings Fetch                                                        #
    # ------------------------------------------------------------------ #

    async def _fetch_storage_settings(self) -> Dict[str, Any]:
        """Read storage settings from the DB."""
        try:
            from backend.app.core.database import db
            row = await db.fetch_one(
                "SELECT data FROM system_settings ORDER BY id DESC LIMIT 1"
            )
            if row and row["data"]:
                data = row["data"]
                if isinstance(data, str):
                    data = json.loads(data)
                return data.get("storage", {})
        except Exception as exc:
            logger.error("StorageCleaner: could not fetch settings: %s", exc)
        return {}

    # ------------------------------------------------------------------ #
    # Rule: Retention Days                                                  #
    # ------------------------------------------------------------------ #

    async def _enforce_retention(self, retention_days: int):
        """Delete events (and cascading alerts) older than retention_days."""
        if retention_days <= 0:
            return
        try:
            from backend.app.core.database import db
            cutoff_ts = time.time() - (retention_days * 86400)

            # Delete alerts whose linked event is older than the cutoff
            deleted_alerts = await db.execute(
                """
                DELETE FROM alerts
                WHERE event_id IN (
                    SELECT id FROM events WHERE created_at < $1
                )
                """,
                cutoff_ts,
            )

            # Delete the old events themselves
            deleted_events = await db.execute(
                "DELETE FROM events WHERE created_at < $1",
                cutoff_ts,
            )

            logger.info(
                "StorageCleaner [retention]: removed events before %.0f (cutoff=%dd). "
                "alerts=%s events=%s",
                cutoff_ts, retention_days, deleted_alerts, deleted_events,
            )
        except Exception as exc:
            logger.error("StorageCleaner retention enforcement failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Rule: Max Storage                                                     #
    # ------------------------------------------------------------------ #

    async def _enforce_max_storage(self, max_storage_gb: float):
        """Delete the oldest media files until disk usage is below max_storage_gb."""
        max_bytes = max_storage_gb * 1024 * 1024 * 1024
        current_bytes = self._get_dir_size(self.shared_frames_dir)

        if current_bytes <= max_bytes:
            logger.debug(
                "StorageCleaner [max storage]: %.2f GB used / %.2f GB limit — OK",
                current_bytes / 1e9, max_storage_gb
            )
            return

        logger.warning(
            "StorageCleaner [max storage]: %.2f GB used exceeds %.2f GB limit — purging oldest files",
            current_bytes / 1e9, max_storage_gb
        )

        # Gather all media files, sorted oldest-first
        media_files = self._collect_media_files(self.shared_frames_dir)

        bytes_freed = 0
        for file_path, file_size in media_files:
            if current_bytes - bytes_freed <= max_bytes:
                break
            try:
                os.remove(file_path)
                bytes_freed += file_size
                logger.info("StorageCleaner: deleted %s (%.1f KB)", file_path, file_size / 1024)
            except OSError as exc:
                logger.warning("StorageCleaner: could not delete %s: %s", file_path, exc)

        logger.info(
            "StorageCleaner [max storage]: freed %.2f MB across %d files",
            bytes_freed / 1e6, len([f for f in media_files if f[1] <= bytes_freed])
        )

    # ------------------------------------------------------------------ #
    # Helpers                                                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_dir_size(directory: str) -> float:
        """Return total size in bytes for all files under directory."""
        total = 0
        try:
            for dirpath, _, filenames in os.walk(directory):
                for fname in filenames:
                    fpath = os.path.join(dirpath, fname)
                    try:
                        total += os.path.getsize(fpath)
                    except OSError:
                        pass
        except Exception:
            pass
        return total

    @staticmethod
    def _collect_media_files(directory: str) -> List[tuple]:
        """
        Return a sorted list of (path, size_bytes) tuples for all .mp4/.jpg files
        under the given directory, sorted oldest-first by modification time.
        """
        MEDIA_EXTENSIONS = {".mp4", ".jpg", ".jpeg", ".png"}
        files = []
        try:
            for dirpath, _, filenames in os.walk(directory):
                for fname in filenames:
                    if Path(fname).suffix.lower() in MEDIA_EXTENSIONS:
                        fpath = os.path.join(dirpath, fname)
                        try:
                            stat = os.stat(fpath)
                            files.append((fpath, stat.st_size, stat.st_mtime))
                        except OSError:
                            pass
        except Exception:
            pass
        # Sort oldest first
        files.sort(key=lambda x: x[2])
        # Return only (path, size) — drop mtime
        return [(f[0], f[1]) for f in files]


# Singleton instance
_cleaner: StorageCleaner = None


def get_storage_cleaner(shared_frames_dir: str = None) -> StorageCleaner:
    global _cleaner
    if _cleaner is None:
        _cleaner = StorageCleaner(
            shared_frames_dir=shared_frames_dir
            or os.environ.get("SHARED_FRAMES_DIR", "/shared-frames")
        )
    return _cleaner
