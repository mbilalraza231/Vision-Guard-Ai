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

    # Critical model settings: Use environment variables as PRIMARY source
    # Redis removed these settings to prevent frontend from breaking workers
    # Environment variables set in docker-compose.yml are the authoritative source
    fire_runtime = {
        "iouThreshold": float(
            os.getenv("WORKER_IOU_THRESHOLD", "0.45"),
        ),
        "agnosticNms": bool(
            os.getenv("WORKER_AGNOSTIC_NMS", "true").lower() == "true",
        ),
        "allowedClassIds": str(
            os.getenv("WORKER_ALLOWED_CLASS_IDS", "0"),
        ),
        "inputWidth": int(
            os.getenv("WORKER_INPUT_WIDTH", "640"),  # Default to 640 for weapon/fall
        ),
        "inputHeight": int(
            os.getenv("WORKER_INPUT_HEIGHT", "640"),  # Default to 640 for weapon/fall
        ),
    }

    return {
        "confidence_threshold": confidence,
        "image_save_threshold": image_save,
        "max_snapshot_buffer": max_snapshot_buffer,
        "fire_model": fire_runtime,
    }

def load_worker_onnx_threads(model_type: str) -> dict:
    """
    Read ONNX thread settings from Redis system_settings.
    Supports per-worker allocation:
      - workers.intraOpThreads.{model_type} (e.g., weapon: 2, fire: 1, fall: 2)
      - workers.onnxThreads.intra.{model_type}
    Falls back to global workers.onnxIntraOpThreads, env vars, then defaults.
    """
    workers = _redis_get_settings().get("workers", {})
    if not isinstance(workers, dict):
        workers = {}

    # Check per-model intra threads
    intra = None
    intra_map = workers.get("intraOpThreads")
    if isinstance(intra_map, dict) and model_type in intra_map:
        intra = intra_map.get(model_type)

    onnx = workers.get("onnxThreads", {})
    if intra is None and isinstance(onnx, dict):
        onnx_intra_map = onnx.get("intra")
        if isinstance(onnx_intra_map, dict) and model_type in onnx_intra_map:
            intra = onnx_intra_map.get(model_type)
        if intra is None:
            intra = onnx.get("intraOpNumThreads")

    if intra is None:
        intra = workers.get("onnxIntraOpThreads")

    if intra is None:
        # Check per-model env var e.g. ONNX_INTRA_OP_NUM_THREADS_WEAPON
        env_model = os.getenv(f"ONNX_INTRA_OP_NUM_THREADS_{model_type.upper()}")
        if env_model is not None:
            intra = env_model
        else:
            intra = os.getenv("ONNX_INTRA_OP_NUM_THREADS", "2")

    # Check per-model inter threads
    inter = None
    inter_map = workers.get("interOpThreads")
    if isinstance(inter_map, dict) and model_type in inter_map:
        inter = inter_map.get(model_type)

    if inter is None and isinstance(onnx, dict):
        onnx_inter_map = onnx.get("inter")
        if isinstance(onnx_inter_map, dict) and model_type in onnx_inter_map:
            inter = onnx_inter_map.get(model_type)
        if inter is None:
            inter = onnx.get("interOpNumThreads")

    if inter is None:
        inter = workers.get("onnxInterOpThreads")

    if inter is None:
        inter = os.getenv("ONNX_INTER_OP_NUM_THREADS", "1")

    return {"intra": max(1, int(intra)), "inter": max(1, int(inter))}
