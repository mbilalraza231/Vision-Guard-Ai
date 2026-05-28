"""
Runtime settings resolver.

Resolution order:
1) Redis cache (vg:system_settings)
2) PostgreSQL system_settings row
3) Environment-derived defaults
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict

import redis

from ..core.database import db
from ..core.config import get_redis_config
from ..api.settings import _deep_merge, _load_default_settings

logger = logging.getLogger(__name__)


def _read_from_redis_sync() -> Dict[str, Any]:
    try:
        client = redis.Redis(**get_redis_config())
        raw = client.get("vg:system_settings")
        client.close()
        if not raw:
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def _read_from_db_async() -> Dict[str, Any]:
    try:
        row = await db.fetch_one("SELECT data FROM system_settings ORDER BY id DESC LIMIT 1")
        if not row or not row.get("data"):
            return {}
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def resolve_runtime_settings() -> Dict[str, Any]:
    """
    Resolve settings for runtime consumers.
    Prefer Redis cache, fallback to DB, then .env defaults.
    """
    defaults = _load_default_settings()

    redis_data = _read_from_redis_sync()
    if redis_data:
        return _deep_merge(defaults, redis_data)

    db_data = await _read_from_db_async()
    if db_data:
        return _deep_merge(defaults, db_data)

    return defaults


def resolve_runtime_settings_sync() -> Dict[str, Any]:
    """
    Synchronous wrapper for services running in sync paths.
    """
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            # If called from an active loop in a sync context, avoid blocking loop.
            # Return best-effort Redis/defaults to stay safe and fast.
            defaults = _load_default_settings()
            redis_data = _read_from_redis_sync()
            return _deep_merge(defaults, redis_data) if redis_data else defaults
    except RuntimeError:
        pass

    return asyncio.run(resolve_runtime_settings())

