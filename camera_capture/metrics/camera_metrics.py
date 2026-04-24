"""
VisionGuard AI - Camera Metrics

Shared metrics for cross-process camera monitoring.
Uses multiprocessing primitives for thread-safe access.
"""

import time
from dataclasses import dataclass, field, asdict
from multiprocessing import Manager, Value
from typing import Dict, Any, Optional
from ctypes import c_double, c_long, c_bool


@dataclass
class CameraMetricsSnapshot:
    """Point-in-time snapshot of camera metrics."""
    camera_id: str
    fps_current: float = 0.0
    frames_generated_total: int = 0
    frames_dropped_total: int = 0
    frames_with_motion: int = 0
    shared_memory_failures: int = 0
    redis_publish_failures: int = 0
    last_frame_ts: float = 0.0
    is_alive: bool = False
    stall_detected: bool = False
    uptime_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SharedCameraMetrics:
    """
    Thread-safe shared camera metrics.
    
    Uses multiprocessing shared memory for cross-process access.
    Parent process can read metrics from child camera process.
    """
    
    def __init__(self, camera_id: str, manager: Optional[Manager] = None):
        """
        Initialize shared metrics.
        
        Args:
            camera_id: Camera identifier
            manager: Optional multiprocessing.Manager (creates one if not provided)
        """
        self.camera_id = camera_id
        self._manager = manager or Manager()
        
        # Shared values (cross-process safe)
        self._metrics = self._manager.dict({
            'camera_id': camera_id,
            'fps_current': 0.0,
            'frames_generated_total': 0,
            'frames_dropped_total': 0,
            'frames_with_motion': 0,
            'shared_memory_failures': 0,
            'redis_publish_failures': 0,
            'last_frame_ts': 0.0,
            'is_alive': False,
            'started_at': 0.0,
        })
        
        # FPS calculation window
        self._fps_window_start = time.time()
        self._fps_frame_count = 0
    
    def mark_alive(self) -> None:
        """Mark camera as alive (call on process start)."""
        self._metrics['is_alive'] = True
        self._metrics['started_at'] = time.time()
    
    def mark_dead(self) -> None:
        """Mark camera as dead (call on process stop)."""
        self._metrics['is_alive'] = False
    
    def record_frame(self, has_motion: bool = False) -> None:
        """
        Record a frame capture event.
        
        Args:
            has_motion: Whether motion was detected
        """
        self._metrics['frames_generated_total'] = self._metrics.get('frames_generated_total', 0) + 1
        self._metrics['last_frame_ts'] = time.time()
        
        if has_motion:
            self._metrics['frames_with_motion'] = self._metrics.get('frames_with_motion', 0) + 1
        
        # Update FPS calculation
        self._fps_frame_count += 1
        elapsed = time.time() - self._fps_window_start
        
        if elapsed >= 1.0:  # Update FPS every second
            self._metrics['fps_current'] = round(self._fps_frame_count / elapsed, 2)
            self._fps_window_start = time.time()
            self._fps_frame_count = 0
    
    def record_frame_drop(self) -> None:
        """Record a dropped frame."""
        self._metrics['frames_dropped_total'] = self._metrics.get('frames_dropped_total', 0) + 1
    
    def record_shared_memory_failure(self) -> None:
        """Record a shared memory write failure."""
        self._metrics['shared_memory_failures'] = self._metrics.get('shared_memory_failures', 0) + 1
    
    def record_redis_failure(self) -> None:
        """Record a Redis publish failure."""
        self._metrics['redis_publish_failures'] = self._metrics.get('redis_publish_failures', 0) + 1
    
    def get_snapshot(self, stall_threshold_seconds: float = 5.0) -> CameraMetricsSnapshot:
        """
        Get a point-in-time metrics snapshot.
        
        Args:
            stall_threshold_seconds: Seconds without frames before stall detected
            
        Returns:
            CameraMetricsSnapshot with current values
        """
        now = time.time()
        last_frame = self._metrics.get('last_frame_ts', 0.0)
        started_at = self._metrics.get('started_at', now)
        is_alive = self._metrics.get('is_alive', False)
        
        # Detect stall (no frames for threshold seconds when alive)
        stall_detected = False
        if is_alive and last_frame > 0:
            stall_detected = (now - last_frame) > stall_threshold_seconds
        
        return CameraMetricsSnapshot(
            camera_id=self.camera_id,
            fps_current=self._metrics.get('fps_current', 0.0),
            frames_generated_total=self._metrics.get('frames_generated_total', 0),
            frames_dropped_total=self._metrics.get('frames_dropped_total', 0),
            frames_with_motion=self._metrics.get('frames_with_motion', 0),
            shared_memory_failures=self._metrics.get('shared_memory_failures', 0),
            redis_publish_failures=self._metrics.get('redis_publish_failures', 0),
            last_frame_ts=last_frame,
            is_alive=is_alive,
            stall_detected=stall_detected,
            uptime_seconds=round(now - started_at, 2) if is_alive else 0.0
        )
    
    def reset(self) -> None:
        """Reset all metrics to zero."""
        self._metrics['fps_current'] = 0.0
        self._metrics['frames_generated_total'] = 0
        self._metrics['frames_dropped_total'] = 0
        self._metrics['frames_with_motion'] = 0
        self._metrics['shared_memory_failures'] = 0
        self._metrics['redis_publish_failures'] = 0
        self._metrics['last_frame_ts'] = 0.0
        self._metrics['is_alive'] = False
        self._metrics['started_at'] = 0.0
        self._fps_window_start = time.time()
        self._fps_frame_count = 0
