"""
Environment-derived default system settings.

Shared by the FastAPI settings API and lightweight workers (alert-worker, etc.)
that must not import FastAPI.
"""

from __future__ import annotations

import os
from typing import Any, Dict

# Product defaults for dashboard Reset (not read from container env).
# ECS/worker containers may still get thresholds from compose until recreated.
ECS_THRESHOLD_DEFAULT = 0.30

# Fixed product defaults for Reset (match event_classification/config.py).
ECS_WEAPON_PERSISTENCE = {"minDetections": 5,
                          "windowSec": 5.0, "cooldownSec": 30.0}
ECS_FIRE_PERSISTENCE = {"minDetections": 3,
                        "windowSec": 8.0, "cooldownSec": 60.0}
ECS_FALL_PERSISTENCE = {"minDetections": 3,
                        "windowSec": 6.0, "cooldownSec": 30.0}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(float(raw))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except Exception:
        return default


def _load_default_settings() -> Dict[str, Any]:
    """
    Build defaults for dashboard Reset and API /defaults.

    ECS confidence thresholds use fixed product defaults (0.30) so Reset is not
    tied to stale ECS_* env vars inside a long-running backend container.
    Other sections still honor deployment env where appropriate.
    """
    return {
        "general": {
            "siteName": os.environ.get("VG_SITE_NAME", "VisionGuard AI"),
            "timezone": os.environ.get("VG_TIMEZONE", "UTC"),
            "language": os.environ.get("VG_LANGUAGE", "en"),
        },
        "cameras": {
            "globalFpsTarget": _env_int("VG_GLOBAL_FPS_TARGET", 15),
            "targetLatencyMs": _env_int("VG_TARGET_LATENCY_MS", 500),
            "targetMemoryGb": _env_float("VG_TARGET_MEMORY_GB", 8.0),
            "targetFalsePositiveRate": _env_float("VG_TARGET_FALSE_POSITIVE_RATE", 5.0),
        },
        "workers": {
            "thresholds": {
                "weapon": _env_float(
                    "WORKER_WEAPON_THRESHOLD",
                    _env_float("WORKER_CONFIDENCE_THRESHOLD", 0.70),
                ),
                "fire": _env_float(
                    "WORKER_FIRE_THRESHOLD",
                    _env_float("WORKER_CONFIDENCE_THRESHOLD", 0.40),
                ),
                "fall": _env_float(
                    "WORKER_FALL_THRESHOLD",
                    _env_float("WORKER_CONFIDENCE_THRESHOLD", 0.80),
                ),
            },
            "imageSaveThreshold": _env_float("IMAGE_SAVE_THRESHOLD", 0.30),
            "maxSnapshotBuffer": _env_int("WORKER_MAX_SNAPSHOT_BUFFER", 100),
            "fireModel": {
                "iouThreshold": _env_float("WORKER_IOU_THRESHOLD", 0.45),
                "agnosticNms": _env_bool("WORKER_AGNOSTIC_NMS", True),
                "allowedClassIds": os.environ.get("WORKER_ALLOWED_CLASS_IDS", "0"),
                "inputWidth": _env_int("WORKER_INPUT_WIDTH", 416),
                "inputHeight": _env_int("WORKER_INPUT_HEIGHT", 416),
            },
        },
        "ecs": {
            "thresholds": {
                "weapon": ECS_THRESHOLD_DEFAULT,
                "fire": ECS_THRESHOLD_DEFAULT,
                "fall": ECS_THRESHOLD_DEFAULT,
            },
            "correlationWindowMs": _env_int("ECS_CORRELATION_WINDOW_MS", 400),
            "hardTtlSeconds": _env_float("ECS_HARD_TTL_SECONDS", 2.0),
            "enableAlerts": _env_bool("ECS_ENABLE_ALERTS", True),
            "enableDatabase": _env_bool("ECS_ENABLE_DATABASE", True),
            "enableFrontend": _env_bool("ECS_ENABLE_FRONTEND", True),
            "maxSourceLagSec": _env_float("ECS_MAX_SOURCE_LAG_SEC", 20.0),
            "resumeFromLatest": _env_bool("ECS_RESUME_FROM_LATEST", True),
            "weaponPersistence": dict(ECS_WEAPON_PERSISTENCE),
            "firePersistence": dict(ECS_FIRE_PERSISTENCE),
            "fallPersistence": dict(ECS_FALL_PERSISTENCE),
        },
        "cameraCapture": {
            "defaultFps": _env_int("CAMERA_DEFAULT_FPS", 5),
            "motionThreshold": _env_float("CAMERA_MOTION_THRESHOLD", 0.02),
        },
        "clips": {
            "preSeconds": _env_int("CLIP_PRE_SECONDS", 0),
            "postSeconds": _env_int("CLIP_POST_SECONDS", 10),
            "enableBackgroundBuffer": _env_bool("CLIP_ENABLE_BACKGROUND_BUFFER", False),
        },
        "systemOverrides": {
            "memoryTotalGbOverride": _env_float("VG_SYSTEM_MEMORY_GB", 0.0),
        },
        "alerts": {
            "emailNotifications": _env_bool("VG_DEFAULT_EMAIL_ALERTS", True),
            "smsNotifications": _env_bool("VG_DEFAULT_SMS_ALERTS", True),
            "pushNotifications": _env_bool("VG_DEFAULT_PUSH_ALERTS", True),
            "alertThreshold": os.environ.get("VG_DEFAULT_ALERT_THRESHOLD", "low"),
        },
        "storage": {
            "retentionDays": 30,
            "autoDelete": False,
            "maxStorage": 50,
        },
        "models": {
            "detectionModel": "yolo-edge-v2",
            "confidenceThreshold": 0.7,
            "processingMode": "realtime",
        },
        "privacy": {
            "maskFaces": False,
            "anonymizeData": False,
            "gdprCompliant": False,
        },
        "notifications": {
            "recipients": [],
        },
        "queueManagement": {
            "maxQueueSize": 1000,
            "taskTtlSeconds": 300,
        },
    }


DEFAULT_SETTINGS: Dict[str, Any] = _load_default_settings()


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict."""
    merged = dict(base)
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged
