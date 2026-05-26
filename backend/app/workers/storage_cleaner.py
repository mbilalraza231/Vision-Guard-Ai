"""
VisionGuard AI - Storage Cleaner Background Worker

Periodically enforces storage settings:
  - retentionDays: Deletes events/alerts older than N days from the database.
                   Also destroys associated files from Local FS and Cloudinary.
  - maxStorage (GB): Deletes the oldest local video/snapshot files when the
                     /data/visionguard directories exceed the limit.
  - autoDelete: Master switch — if False, this worker does nothing.
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.parse

import cloudinary
import cloudinary.uploader

logger = logging.getLogger(__name__)

# How often the cleaner wakes up and checks storage (in seconds)
CLEANER_INTERVAL_SECONDS = 3600  # 1 hour


class StorageCleaner:
    """
    Background async task that enforces the storage settings configured
    by the administrator in the Settings → Storage page.
    """

    def __init__(self, data_dir: str = "/data/visionguard"):
        self.data_dir = data_dir
        self.clip_dir = os.path.join(data_dir, "clips")
        self.snapshot_dir = os.path.join(data_dir, "detections")
        
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task = None

        # Configure Cloudinary if credentials exist
        self.cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "")
        self.api_key = os.getenv("CLOUDINARY_API_KEY", "")
        self.api_secret = os.getenv("CLOUDINARY_API_SECRET", "")
        
        if self.cloud_name and self.api_key and self.api_secret:
            cloudinary.config(
                cloud_name=self.cloud_name,
                api_key=self.api_key,
                api_secret=self.api_secret,
                secure=True,
            )
            self.cloudinary_enabled = True
        else:
            self.cloudinary_enabled = False

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

        # Enforce retention policy (DB, Local, Cloud)
        await self._enforce_retention(retention_days)

        # Enforce disk usage limit (Local Files only)
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
        """Delete events, and securely delete their evidence from Local FS and Cloudinary."""
        if retention_days <= 0:
            return
        try:
            from backend.app.core.database import db
            cutoff_ts = time.time() - (retention_days * 86400)

            # 1. Fetch all evidence linked to expiring events BEFORE we delete the events
            evidence_rows = await db.fetch_all(
                """
                SELECT id, evidence_type, storage_provider, public_url 
                FROM event_evidence 
                WHERE event_id IN (
                    SELECT id FROM events WHERE created_at < $1
                )
                """,
                cutoff_ts,
            )

            # 2. Delete actual files (Local & Cloudinary)
            deleted_files = 0
            for row in evidence_rows:
                success = await self._destroy_evidence_file(
                    provider=row["storage_provider"],
                    url=row["public_url"],
                    evidence_type=row["evidence_type"]
                )
                if success:
                    deleted_files += 1

            # 3. Delete the events (ON DELETE CASCADE will automatically wipe alerts and event_evidence)
            deleted_events = await db.execute(
                "DELETE FROM events WHERE created_at < $1",
                cutoff_ts,
            )

            logger.info(
                "StorageCleaner [retention]: removed events before %.0f (cutoff=%dd). "
                "events_purged=%s, files_destroyed=%d/%d",
                cutoff_ts, retention_days, deleted_events, deleted_files, len(evidence_rows)
            )
        except Exception as exc:
            logger.error("StorageCleaner retention enforcement failed: %s", exc)

    async def _destroy_evidence_file(self, provider: str, url: str, evidence_type: str) -> bool:
        """Destroy the actual media file based on its provider."""
        if provider == "local":
            try:
                if os.path.exists(url):
                    os.remove(url)
                    return True
                return False  # Already gone
            except OSError as e:
                logger.warning("StorageCleaner: failed to remove local file %s: %s", url, e)
                return False

        elif provider == "cloudinary" and self.cloudinary_enabled:
            # Parse public_id from Cloudinary URL
            # Format usually: https://res.cloudinary.com/.../upload/v.../visionguard/clips/weapon/clip_123.mp4
            try:
                # Extract everything after the version folder or 'upload/'
                parsed = urllib.parse.urlparse(url)
                path_parts = parsed.path.split('/')
                
                # Find 'visionguard' index to get the folder structure
                try:
                    vg_idx = path_parts.index('visionguard')
                    public_id_with_ext = '/'.join(path_parts[vg_idx:])
                    # Remove extension
                    public_id = os.path.splitext(public_id_with_ext)[0]
                except ValueError:
                    # Fallback if structure is different
                    filename = path_parts[-1]
                    public_id = os.path.splitext(filename)[0]

                resource_type = "video" if evidence_type == "clip" else "image"
                
                # Cloudinary delete is blocking, use to_thread
                result = await asyncio.to_thread(
                    cloudinary.uploader.destroy,
                    public_id,
                    resource_type=resource_type
                )
                
                if result.get("result") == "ok":
                    return True
                else:
                    logger.warning("StorageCleaner: Cloudinary destroy returned %s for %s", result, public_id)
                    return False
            except Exception as e:
                logger.warning("StorageCleaner: failed to destroy Cloudinary asset %s: %s", url, e)
                return False
                
        return False

    # ------------------------------------------------------------------ #
    # Rule: Max Storage                                                     #
    # ------------------------------------------------------------------ #

    async def _enforce_max_storage(self, max_storage_gb: float):
        """Delete the oldest local media files until disk usage is below max_storage_gb."""
        max_bytes = max_storage_gb * 1024 * 1024 * 1024
        
        # We only care about the clips and detections folders
        clips_size = self._get_dir_size(self.clip_dir)
        snapshots_size = self._get_dir_size(self.snapshot_dir)
        current_bytes = clips_size + snapshots_size

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

        # Gather all media files from both directories, sorted oldest-first
        media_files = self._collect_media_files([self.clip_dir, self.snapshot_dir])

        bytes_freed = 0
        deleted_count = 0
        from backend.app.core.database import db

        for file_path, file_size in media_files:
            if current_bytes - bytes_freed <= max_bytes:
                break
            try:
                os.remove(file_path)
                bytes_freed += file_size
                deleted_count += 1
                
                # We must also clean up the database so the UI doesn't show broken links!
                await db.execute(
                    "DELETE FROM event_evidence WHERE storage_provider = 'local' AND public_url = $1",
                    file_path
                )
                
                logger.info("StorageCleaner: deleted %s (%.1f KB)", file_path, file_size / 1024)
            except OSError as exc:
                logger.warning("StorageCleaner: could not delete %s: %s", file_path, exc)
            except Exception as exc:
                logger.warning("StorageCleaner: failed to clean DB for %s: %s", file_path, exc)

        logger.info(
            "StorageCleaner [max storage]: freed %.2f MB across %d files",
            bytes_freed / 1e6, deleted_count
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
                        if not os.path.islink(fpath):
                            total += os.path.getsize(fpath)
                    except OSError:
                        pass
        except Exception:
            pass
        return total

    @staticmethod
    def _collect_media_files(directories: List[str]) -> List[tuple]:
        """
        Return a sorted list of (path, size_bytes) tuples for all .mp4/.jpg files
        under the given directories, sorted oldest-first by modification time.
        """
        MEDIA_EXTENSIONS = {".mp4", ".jpg", ".jpeg", ".png"}
        files = []
        for directory in directories:
            try:
                if not os.path.exists(directory):
                    continue
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
                
        # Sort oldest first (smallest mtime)
        files.sort(key=lambda x: x[2])
        # Return only (path, size) — drop mtime
        return [(f[0], f[1]) for f in files]


# Singleton instance
_cleaner: StorageCleaner = None


def get_storage_cleaner(data_dir: str = None) -> StorageCleaner:
    global _cleaner
    if _cleaner is None:
        _cleaner = StorageCleaner(
            data_dir=data_dir or os.environ.get("VG_DATA_DIR", "/data/visionguard")
        )
    return _cleaner
