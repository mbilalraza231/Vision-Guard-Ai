"""Load AI worker thresholds from Redis system settings."""

from __future__ import annotations

import json
import os
from typing import Optional

import redis


def load_worker_confidence_threshold(model_type: str) -> float:
    """
    Resolve confidence threshold for this worker's model type.

    Order: Redis settings.workers.thresholds.{model} -> WORKER_CONFIDENCE_THRESHOLD env -> 0.40
    """
    env_default = float(os.getenv("WORKER_CONFIDENCE_THRESHOLD", "0.40"))
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
            thresholds = data.get("workers", {}).get("thresholds", {})
            val = thresholds.get(model_type)
            if val is not None:
                return float(val)
    except Exception:
        pass
    return env_default
