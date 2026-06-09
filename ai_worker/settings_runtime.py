"""Load AI worker tuning from Redis system settings (vg:system_settings)."""

from __future__ import annotations

import json
import os
from typing import Any, Dict

import redis


def _redis_get_settings() -> Dict[str, Any]:
    try:
        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            socket_connect_timeout=2,
        )
        raw = r.get("vg:system_settings")
        r.close()
        if raw:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def load_worker_confidence_threshold(model_type: str) -> float:
    """
    Resolve confidence threshold for this worker's model type.

    Order: Redis settings.workers.thresholds.{model} -> WORKER_CONFIDENCE_THRESHOLD env -> 0.40
    """
    env_default = float(os.getenv("WORKER_CONFIDENCE_THRESHOLD", "0.40"))
    try:
        thresholds = _redis_get_settings().get("workers", {}).get("thresholds", {})
        val = thresholds.get(model_type)
        if val is not None:
            return float(val)
    except Exception:
        pass
    return env_default


def load_worker_runtime_settings(model_type: str) -> Dict[str, Any]:
    """
    Resolve worker tuning from Redis with env fallbacks.

    Returns keys: confidence_threshold, image_save_threshold, fire_model (dict, fire only).
    """
    workers = _redis_get_settings().get("workers", {})
    if not isinstance(workers, dict):
        workers = {}

    confidence = load_worker_confidence_threshold(model_type)

    image_save = workers.get("imageSaveThreshold")
    if image_save is None:
        image_save = float(os.getenv("IMAGE_SAVE_THRESHOLD", str(min(confidence, 0.30))))
    else:
        image_save = float(image_save)

    max_snapshot_buffer = workers.get("maxSnapshotBuffer")
    if max_snapshot_buffer is None:
        try:
            max_snapshot_buffer = int(os.getenv("WORKER_MAX_SNAPSHOT_BUFFER", "100"))
        except Exception:
            max_snapshot_buffer = 100
    else:
        try:
            max_snapshot_buffer = int(max_snapshot_buffer)
        except Exception:
            max_snapshot_buffer = 100

    fire_model = workers.get("fireModel", {})
    if not isinstance(fire_model, dict):
        fire_model = {}

    fire_runtime = {
        "iouThreshold": float(
            fire_model.get(
                "iouThreshold",
                os.getenv("WORKER_IOU_THRESHOLD", "0.45"),
            )
        ),
        "agnosticNms": bool(
            fire_model.get(
                "agnosticNms",
                os.getenv("WORKER_AGNOSTIC_NMS", "true").lower() == "true",
            )
        ),
        "allowedClassIds": str(
            fire_model.get(
                "allowedClassIds",
                os.getenv("WORKER_ALLOWED_CLASS_IDS", "0"),
            )
        ),
        "inputWidth": int(
            fire_model.get(
                "inputWidth",
                os.getenv("WORKER_INPUT_WIDTH", "416"),
            )
        ),
        "inputHeight": int(
            fire_model.get(
                "inputHeight",
                os.getenv("WORKER_INPUT_HEIGHT", "416"),
            )
        ),
    }

    return {
        "confidence_threshold": confidence,
        "image_save_threshold": image_save,
        "max_snapshot_buffer": max_snapshot_buffer,
        "fire_model": fire_runtime,
    }
