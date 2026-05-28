"""
Load ECS tuning from Redis dashboard settings (vg:system_settings).

Resolution order for thresholds:
  Redis ecs.thresholds -> ECS_* env vars -> 0.30
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Tuple

import redis

from .config import ECSConfig


def _redis_client() -> redis.Redis:
    return redis.Redis(
        host=os.getenv("ECS_REDIS_HOST", os.getenv("REDIS_HOST", "localhost")),
        port=int(os.getenv("ECS_REDIS_PORT", os.getenv("REDIS_PORT", "6379"))),
        db=int(os.getenv("REDIS_DB", "0")),
        socket_connect_timeout=2,
    )


def _load_settings_blob() -> Dict[str, Any]:
    try:
        client = _redis_client()
        raw = client.get("vg:system_settings")
        client.close()
        if not raw:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def resolve_ecs_thresholds() -> Dict[str, float]:
    """Per-model ECS confidence gates (persistence counting threshold)."""
    resolved = {
        "weapon": _env_float("ECS_WEAPON_THRESHOLD", 0.30),
        "fire": _env_float("ECS_FIRE_THRESHOLD", 0.30),
        "fall": _env_float("ECS_FALL_THRESHOLD", 0.30),
    }
    thresholds = _load_settings_blob().get("ecs", {}).get("thresholds", {})
    if isinstance(thresholds, dict):
        for key in resolved:
            val = thresholds.get(key)
            if val is not None:
                try:
                    resolved[key] = float(val)
                except (TypeError, ValueError):
                    pass
    return resolved


def apply_runtime_settings(config: ECSConfig) -> Tuple[bool, Dict[str, Any]]:
    """
    Apply dashboard / Redis overrides onto the live ECSConfig.

    Returns:
        (changed, snapshot of applied values for logging)
    """
    blob = _load_settings_blob()
    ecs = blob.get("ecs", {}) if isinstance(blob.get("ecs"), dict) else {}

    thresholds = resolve_ecs_thresholds()
    correlation_ms = ecs.get("correlationWindowMs")
    if correlation_ms is None:
        correlation_ms = _env_int("ECS_CORRELATION_WINDOW_MS", config.correlation_window_ms)
    else:
        correlation_ms = int(correlation_ms)

    hard_ttl = ecs.get("hardTtlSeconds")
    if hard_ttl is None:
        hard_ttl = _env_float("ECS_HARD_TTL_SECONDS", config.hard_ttl_seconds)
    else:
        hard_ttl = float(hard_ttl)

    updates = {
        "weapon_confidence_threshold": thresholds["weapon"],
        "fire_confidence_threshold": thresholds["fire"],
        "fall_confidence_threshold": thresholds["fall"],
        "correlation_window_ms": correlation_ms,
        "hard_ttl_seconds": hard_ttl,
    }

    changed = False
    for field, new_val in updates.items():
        old_val = getattr(config, field)
        if isinstance(new_val, float):
            diff = abs(float(old_val) - float(new_val)) > 1e-6
        else:
            diff = old_val != new_val
        if diff:
            setattr(config, field, new_val)
            changed = True

    snapshot = {
        "weapon_threshold": config.weapon_confidence_threshold,
        "fire_threshold": config.fire_confidence_threshold,
        "fall_threshold": config.fall_confidence_threshold,
        "correlation_window_ms": config.correlation_window_ms,
        "hard_ttl_seconds": config.hard_ttl_seconds,
    }
    return changed, snapshot
