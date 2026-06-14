"""
Zone priority severity override - Redis-based implementation.

Reads the camera->zone-priority mapping from Redis 'vg:zone_priorities'
(published by the backend whenever zones/cameras change).

Follows the same pattern as settings_runtime.py:
  - Redis key: vg:zone_priorities (JSON: { camera_id: { weapon, fire, fall } })
  - Redis channel: vg:zone:updates (pub/sub notification)

Usage:
    resolver = ZonePriorityResolver(
        redis_host="localhost", redis_port=6379, redis_db=0,
    )
    severity = resolver.resolve("cam1", "fire", "HIGH")  # -> "critical"
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

try:
    import redis
except ImportError:
    redis = None

logger = logging.getLogger("ecs.zone_priority")


class ZonePriorityResolver:
    """
    Resolve event severity by looking up the camera's zone detection
    priority from Redis (populated by backend on zone/camera save).

    Fail-safe: on any error, returns the default severity unchanged.
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        refresh_interval_sec: float = 10.0,
    ) -> None:
        if redis is None:
            logger.warning(
                "redis package not installed; zone priority override disabled")
            self._client: Optional[redis.Redis] = None
            return

        self._client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True,
            socket_connect_timeout=3,
        )
        self._redis_host = redis_host
        self._redis_port = redis_port
        self._redis_db = redis_db

        self._cache: Dict[str, Dict[str, str]] = {}
        self._refresh_interval = refresh_interval_sec
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self._refresh()

        self._listener_thread = threading.Thread(
            target=self._pubsub_listener,
            daemon=True,
            name="zone-priority-listener",
        )
        self._listener_thread.start()

        logger.info(
            f"ZonePriorityResolver initialized via Redis ({len(self._cache)} cameras with zones)"
        )

    # ── public API ──────────────────────────────────────────────────────

    def resolve(self, camera_id: str, model_type: str, default_severity: str) -> str:
        """Return zone-adjusted severity or default if no zone override exists."""
        with self._lock:
            entry = self._cache.get(camera_id)

        if entry is None:
            return default_severity.lower()

        zone_severity = entry.get(model_type)
        if zone_severity is None:
            return default_severity.lower()

        return zone_severity.lower()

    def stop(self) -> None:
        """Stop the background refresh thread and pub/sub listener."""
        self._stop_event.set()
        if hasattr(self, '_pubsub') and self._pubsub:
            try:
                self._pubsub.unsubscribe()
                self._pubsub.close()
            except Exception:
                pass
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        logger.info("ZonePriorityResolver stopped")

    # ── internal ────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        """Reload zone priority mapping from Redis key 'vg:zone_priorities'."""
        if not self._client:
            return

        try:
            raw = self._client.get("vg:zone_priorities")
            if not raw:
                with self._lock:
                    self._cache = {}
                logger.debug(
                    "No 'vg:zone_priorities' key in Redis; using defaults")
                return

            data = json.loads(raw)
            if not isinstance(data, dict):
                with self._lock:
                    self._cache = {}
                return

            with self._lock:
                self._cache = {
                    cam_id: {
                        "weapon": str(p.get("weapon", "critical")).lower(),
                        "fire": str(p.get("fire", "high")).lower(),
                        "fall": str(p.get("fall", "medium")).lower(),
                    }
                    for cam_id, p in data.items()
                    if isinstance(p, dict)
                }

            logger.debug(
                f"Zone priority cache refreshed: {len(self._cache)} cameras")

        except Exception as e:
            logger.warning(
                f"Failed to refresh zone priorities from Redis: {e}")

    def _pubsub_listener(self) -> None:
        """Listen for 'vg:zone:updates' pub/sub messages and refresh cache instantly."""
        while not self._stop_event.is_set():
            try:
                if not self._client:
                    self._stop_event.wait(timeout=self._refresh_interval)
                    continue

                self._pubsub = self._client.pubsub()
                self._pubsub.subscribe("vg:zone:updates")

                logger.info("Subscribed to vg:zone:updates pub/sub channel")

                for message in self._pubsub.listen():
                    if self._stop_event.is_set():
                        break

                    if message["type"] == "message":
                        logger.info(
                            "Received zone priority update via pub/sub")
                        self._refresh()

            except Exception as e:
                if self._stop_event.is_set():
                    break
                logger.warning(
                    f"Zone pub/sub listener error: {e}; reconnecting in 5s")
                self._stop_event.wait(timeout=5.0)

        logger.debug("Zone pub/sub listener thread exited")
