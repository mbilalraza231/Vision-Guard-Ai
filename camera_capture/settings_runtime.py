"""
Load camera capture tuning from Redis system settings (vg:system_settings).

Applies defaultFps and motionThreshold from the Dashboard "Camera Rules" section
so that container restarts do not silently revert to .env defaults.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

import redis

logger = logging.getLogger(__name__)


def _load_redis_settings() -> Dict[str, Any]:
    try:
        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=0,
            socket_connect_timeout=2,
        )
        raw = r.get("vg:system_settings")
        r.close()
        if raw:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug(f"Could not load Redis settings for camera service: {e}")
    return {}


def load_camera_runtime_settings() -> Dict[str, Any]:
    """
    Read Dashboard 'Camera Rules' settings from Redis.

    Returns a dict with:
      - default_fps: int         (from cameraCapture.defaultFps)
      - motion_threshold: float  (from cameraCapture.motionThreshold)
      - global_fps_target: int   (from cameras.globalFpsTarget)
      - max_queue_size: int      (from queueManagement.maxQueueSize)
      - task_ttl_seconds: int    (from queueManagement.taskTtlSeconds)

    Falls back to .env / hardcoded defaults if Redis is unavailable.
    """
    blob = _load_redis_settings()

    camera_capture = blob.get("cameraCapture", {})
    cameras_section = blob.get("cameras", {})
    queue_management = blob.get("queueManagement", {})

    default_fps = int(
        camera_capture.get(
            "defaultFps",
            int(os.getenv("CAMERA_DEFAULT_FPS", "5"))
        )
    )
    motion_threshold = float(
        camera_capture.get(
            "motionThreshold",
            float(os.getenv("CAMERA_MOTION_THRESHOLD", "0.02"))
        )
    )
    global_fps_target = int(
        cameras_section.get(
            "globalFpsTarget",
            int(os.getenv("VG_GLOBAL_FPS_TARGET", "15"))
        )
    )
    max_queue_size = int(
        queue_management.get(
            "maxQueueSize",
            1000
        )
    )
    # Clamp to maximum limit
    max_queue_size = min(max_queue_size, 10000)

    task_ttl_seconds = int(
        queue_management.get(
            "taskTtlSeconds",
            60
        )
    )
    # Clamp to maximum limit
    task_ttl_seconds = min(task_ttl_seconds, 5000)

    return {
        "default_fps": default_fps,
        "motion_threshold": motion_threshold,
        "global_fps_target": global_fps_target,
        "max_queue_size": max_queue_size,
        "task_ttl_seconds": task_ttl_seconds,
    }
