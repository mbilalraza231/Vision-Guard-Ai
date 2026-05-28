"""
Load ECS tuning from Redis dashboard settings (vg:system_settings).

Applies thresholds, persistence windows, cooldowns, and timing knobs live.
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


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _resolve_persistence(
    ecs: Dict[str, Any],
    key: str,
    env_min: str,
    env_window: str,
    env_cooldown: str,
    defaults: Dict[str, Any],
) -> Dict[str, Any]:
    block = ecs.get(key, {})
    if not isinstance(block, dict):
        block = {}
    return {
        "minDetections": int(block.get("minDetections", _env_int(env_min, defaults["minDetections"]))),
        "windowSec": float(block.get("windowSec", _env_float(env_window, defaults["windowSec"]))),
        "cooldownSec": float(block.get("cooldownSec", _env_float(env_cooldown, defaults["cooldownSec"]))),
    }


def apply_runtime_settings(config: ECSConfig) -> Tuple[bool, Dict[str, Any]]:
    """
    Apply dashboard / Redis overrides onto the live ECSConfig.

    Returns:
        (changed, snapshot of applied values for logging)
    """
    blob = _load_settings_blob()
    ecs = blob.get("ecs", {}) if isinstance(blob.get("ecs"), dict) else {}

    thresholds = ecs.get("thresholds", {}) if isinstance(ecs.get("thresholds"), dict) else {}
    weapon_thr = float(
        thresholds.get("weapon", _env_float("ECS_WEAPON_THRESHOLD", config.weapon_confidence_threshold))
    )
    fire_thr = float(
        thresholds.get("fire", _env_float("ECS_FIRE_THRESHOLD", config.fire_confidence_threshold))
    )
    fall_thr = float(
        thresholds.get("fall", _env_float("ECS_FALL_THRESHOLD", config.fall_confidence_threshold))
    )

    weapon_p = _resolve_persistence(
        ecs,
        "weaponPersistence",
        "ECS_WEAPON_MIN_DETECTIONS",
        "ECS_WEAPON_PERSISTENCE_WINDOW",
        "ECS_WEAPON_COOLDOWN_SECONDS",
        {"minDetections": 3, "windowSec": 5.0, "cooldownSec": 30.0},
    )
    fire_p = _resolve_persistence(
        ecs,
        "firePersistence",
        "ECS_FIRE_MIN_DETECTIONS",
        "ECS_FIRE_PERSISTENCE_WINDOW",
        "ECS_FIRE_COOLDOWN_SECONDS",
        {"minDetections": 3, "windowSec": 8.0, "cooldownSec": 60.0},
    )
    fall_p = _resolve_persistence(
        ecs,
        "fallPersistence",
        "ECS_FALL_MIN_DETECTIONS",
        "ECS_FALL_PERSISTENCE_WINDOW",
        "ECS_FALL_COOLDOWN_SECONDS",
        {"minDetections": 3, "windowSec": 6.0, "cooldownSec": 30.0},
    )

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

    max_lag = ecs.get("maxSourceLagSec")
    if max_lag is None:
        max_lag = _env_float("ECS_MAX_SOURCE_LAG_SEC", config.max_source_lag_for_persistence_sec)
    else:
        max_lag = float(max_lag)

    resume_latest = ecs.get("resumeFromLatest")
    if resume_latest is None:
        resume_latest = _env_bool("ECS_RESUME_FROM_LATEST", config.resume_from_latest)
    else:
        resume_latest = bool(resume_latest)

    updates = {
        "weapon_confidence_threshold": weapon_thr,
        "fire_confidence_threshold": fire_thr,
        "fall_confidence_threshold": fall_thr,
        "weapon_min_detections": weapon_p["minDetections"],
        "weapon_persistence_window_sec": weapon_p["windowSec"],
        "weapon_cooldown_seconds": weapon_p["cooldownSec"],
        "fire_min_detections": fire_p["minDetections"],
        "fire_persistence_window_sec": fire_p["windowSec"],
        "fire_cooldown_seconds": fire_p["cooldownSec"],
        "fall_min_detections": fall_p["minDetections"],
        "fall_persistence_window_sec": fall_p["windowSec"],
        "fall_cooldown_seconds": fall_p["cooldownSec"],
        "correlation_window_ms": correlation_ms,
        "hard_ttl_seconds": hard_ttl,
        "max_source_lag_for_persistence_sec": max_lag,
        "resume_from_latest": resume_latest,
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
        "weapon_min_detections": config.weapon_min_detections,
        "fire_min_detections": config.fire_min_detections,
        "fall_min_detections": config.fall_min_detections,
        "correlation_window_ms": config.correlation_window_ms,
        "hard_ttl_seconds": config.hard_ttl_seconds,
        "max_source_lag_sec": config.max_source_lag_for_persistence_sec,
    }
    return changed, snapshot
