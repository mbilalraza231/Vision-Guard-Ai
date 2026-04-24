"""
VisionGuard AI - Camera Event History (ECS v2)

Per-camera temporal tracking for detection persistence
and event deduplication (cooldown).
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Optional
import time


@dataclass
class CameraEventHistory:
    """
    Tracks detection history and cooldown state per camera.
    Used for temporal persistence (fire) and deduplication
    (all event types).
    """
    camera_id: str
    history_window_seconds: float = 10.0

    # Sliding window detection history: (source_ts, ingest_ts, confidence)
    fire_detections: deque = field(default_factory=deque)
    weapon_detections: deque = field(default_factory=deque)
    fall_detections: deque = field(default_factory=deque)

    # Cooldown tracking: last time an event was WRITTEN to DB
    # per event type. Prevents duplicate DB writes for same threat.
    last_event_ts: Dict[str, float] = field(default_factory=dict)

    def add_detection(
        self,
        event_type: str,
        source_timestamp: float,
        ingest_timestamp: float,
        confidence: float,
    ) -> None:
        """Add detection to sliding window. Prune old entries."""
        cutoff = max(source_timestamp, ingest_timestamp) - self.history_window_seconds
        target = self._get_deque(event_type)
        if target is not None:
            target.append((source_timestamp, ingest_timestamp, confidence))
            while target and max(target[0][0], target[0][1]) < cutoff:
                target.popleft()

    def get_recent_count(
        self,
        event_type: str,
        window_seconds: float,
        time_axis: str = "source",
        now_ts: Optional[float] = None,
    ) -> int:
        """Count detections in last N seconds."""
        clock = now_ts if now_ts is not None else time.time()
        cutoff = clock - window_seconds
        target = self._get_deque(event_type)
        if target is None:
            return 0
        if time_axis == "ingest":
            return sum(1 for _src_ts, ingest_ts, _ in target if ingest_ts >= cutoff)
        return sum(1 for source_ts, _ingest_ts, _ in target if source_ts >= cutoff)

    def get_max_confidence(
        self,
        event_type: str,
        window_seconds: float,
        time_axis: str = "source",
        now_ts: Optional[float] = None,
    ) -> float:
        """Get highest confidence score in last N seconds."""
        clock = now_ts if now_ts is not None else time.time()
        cutoff = clock - window_seconds
        target = self._get_deque(event_type)
        if target is None:
            return 0.0
        if time_axis == "ingest":
            recent = [c for _src_ts, ingest_ts, c in target if ingest_ts >= cutoff]
        else:
            recent = [c for source_ts, _ingest_ts, c in target if source_ts >= cutoff]
        return max(recent) if recent else 0.0

    def is_in_cooldown(
        self,
        event_type: str,
        cooldown_seconds: float,
        now_ts: Optional[float] = None,
    ) -> bool:
        """
        Return True if an event of this type was already written
        to DB within the cooldown window.
        Prevents duplicate events for same ongoing threat.
        """
        last = self.last_event_ts.get(event_type, 0.0)
        clock = now_ts if now_ts is not None else time.time()
        return (clock - last) < cooldown_seconds

    def mark_event_written(self, event_type: str, now_ts: Optional[float] = None) -> None:
        """Call after writing an event to DB to start cooldown."""
        self.last_event_ts[event_type] = now_ts if now_ts is not None else time.time()

    def _get_deque(self, event_type: str) -> Optional[deque]:
        mapping = {
            'fire': self.fire_detections,
            'weapon': self.weapon_detections,
            'fall': self.fall_detections,
        }
        return mapping.get(event_type)


class CameraHistoryManager:
    """
    Manages CameraEventHistory instances for all cameras.
    Auto-creates history on first access.
    """

    def __init__(self, history_window_seconds: float = 10.0):
        self._histories: Dict[str, CameraEventHistory] = {}
        self.history_window_seconds = history_window_seconds

    def get(self, camera_id: str) -> CameraEventHistory:
        """Get or create history for a camera."""
        if camera_id not in self._histories:
            self._histories[camera_id] = CameraEventHistory(
                camera_id=camera_id,
                history_window_seconds=self.history_window_seconds
            )
        return self._histories[camera_id]

    def camera_count(self) -> int:
        return len(self._histories)
