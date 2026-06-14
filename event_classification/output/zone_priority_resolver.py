"""
VisionGuard AI - Zone Priority Resolver

Resolves camera -> zone -> per-detection-type severity overrides.
Provides a cached, auto-refreshing mapping so ECS can override the
rule-engine's default severity based on which zone the camera belongs to.

Fail-safe: on any error, returns the original default severity so
classification is never blocked.
"""

import logging
import os
import threading
import time
from typing import Dict, Optional

import psycopg2

# Map rule-engine model_type values to the zone table column suffix.
# model_type comes from Event.model_type: "weapon", "fire", "fall"
_MODEL_TYPE_TO_COLUMN = {
    "weapon": "priority_weapon",
    "fire": "priority_fire",
    "fall": "priority_fall",
}

# Default fallback priorities (must match rule_engine.py defaults)
_DEFAULT_PRIORITIES = {
    "weapon": "critical",
    "fire": "high",
    "fall": "medium",
}


class ZonePriorityResolver:
    """
    Caches camera_id -> zone priority overrides from PostgreSQL.

    Cache structure:
    {
        "cam1": {
            "zone_id": "uuid-string",
            "weapon": "high",      # zone's priority_weapon
            "fire": "critical",    # zone's priority_fire
            "fall": "medium"       # zone's priority_fall
        },
        ...
    }

    Cameras with no zone_id assigned are NOT in the cache; they keep
    the rule-engine default severity.
    """

    def __init__(
        self,
        postgres_config: dict,
        refresh_interval_sec: float = 60.0,
    ):
        """
        Args:
            postgres_config: Dict with keys user, password, host, port, db
            refresh_interval_sec: How often to refresh the cache (seconds)
        """
        self.logger = logging.getLogger(__name__)
        self._dsn = (
            f"postgresql://{postgres_config['user']}:{postgres_config['password']}"
            f"@{postgres_config['host']}:{postgres_config['port']}/{postgres_config['db']}"
        )
        self._refresh_interval = refresh_interval_sec

        # The cache: camera_id -> {zone_id, weapon, fire, fall}
        self._cache: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        # Initial load
        self._refresh()

        # Background refresh thread
        self._thread = threading.Thread(
            target=self._refresh_loop,
            name="ZonePriorityRefresh",
            daemon=True,
        )
        self._thread.start()

        self.logger.info(
            f"ZonePriorityResolver initialized ({len(self._cache)} cameras with zones)",
            extra={"cameras_with_zones": list(self._cache.keys())},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, camera_id: str, model_type: str, default_severity: str) -> str:
        """
        Return the zone-adjusted severity for this camera + detection type.

        Args:
            camera_id: The camera that produced the detection
            model_type: "weapon", "fire", or "fall"
            default_severity: The rule-engine's default (e.g. "CRITICAL", "HIGH")

        Returns:
            Zone-adjusted severity string (lowercase), or the default if
            no zone override exists for this camera.
        """
        with self._lock:
            entry = self._cache.get(camera_id)

        if entry is None:
            # Camera has no zone — keep the default
            return default_severity.lower()

        column = _MODEL_TYPE_TO_COLUMN.get(model_type)
        if column is None:
            # Unknown model_type — keep the default
            return default_severity.lower()

        # The cache stores the zone column value directly
        zone_severity = entry.get(model_type)
        if zone_severity is None:
            return default_severity.lower()

        return zone_severity.lower()

    def stop(self) -> None:
        """Stop the background refresh thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self.logger.info("ZonePriorityResolver stopped")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh_loop(self) -> None:
        """Background thread that periodically refreshes the cache."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self._refresh_interval)
            if self._stop_event.is_set():
                break
            self._refresh()

    def _refresh(self) -> None:
        """Query PostgreSQL and rebuild the camera -> zone priority cache."""
        conn = None
        try:
            conn = psycopg2.connect(self._dsn, connect_timeout=5)
            cursor = conn.cursor()

            # Join cameras with zones; only include cameras that have a zone_id
            # that matches an existing zone with priority columns.
            cursor.execute("""
                SELECT
                    c.id AS camera_id,
                    c.zone_id,
                    z.priority_weapon,
                    z.priority_fire,
                    z.priority_fall
                FROM cameras c
                INNER JOIN zones z ON c.zone_id = z.id::text
                WHERE c.zone_id IS NOT NULL
                  AND c.zone_id != ''
            """)

            rows = cursor.fetchall()
            new_cache: Dict[str, dict] = {}
            for row in rows:
                cam_id, zone_id, p_weapon, p_fire, p_fall = row
                new_cache[cam_id] = {
                    "zone_id": zone_id,
                    "weapon": (p_weapon or _DEFAULT_PRIORITIES["weapon"]).lower(),
                    "fire": (p_fire or _DEFAULT_PRIORITIES["fire"]).lower(),
                    "fall": (p_fall or _DEFAULT_PRIORITIES["fall"]).lower(),
                }

            with self._lock:
                self._cache = new_cache

            self.logger.debug(
                f"Zone priority cache refreshed: {len(new_cache)} camera(s) with zones"
            )

        except Exception as e:
            self.logger.warning(
                f"Zone priority cache refresh failed: {e}",
                extra={"error": str(e)},
            )
        finally:
            if conn:
                conn.close()
