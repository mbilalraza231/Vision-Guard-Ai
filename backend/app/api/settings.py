"""
VisionGuard AI - System Settings API

GET  /api/v1/settings          → return stored settings (merged with defaults)
GET  /api/v1/settings/defaults → return hard-coded defaults only
PUT  /api/v1/settings          → upsert settings JSON

All routes require an admin JWT.
"""

import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.database import db
from ..auth import admin_jwt_required
from ..utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])

# ------------------------------------------------------------------ #
# Default settings – single source of truth                          #
# Must stay in sync with the frontend's `defaultSettings` object.    #
# ------------------------------------------------------------------ #

DEFAULT_SETTINGS: Dict[str, Any] = {
    "general": {
        "siteName": "VisionGuard AI",
        "timezone": "UTC",
        "language": "en",
    },
    "alerts": {
        "emailNotifications": False,
        "smsNotifications": False,
        "pushNotifications": False,
        "alertThreshold": "low",
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
        "twilio": {"sid": "", "token": "", "from": ""},
        "gmail": {"server": "smtp.gmail.com", "user": "", "pass": ""},
    },
}


# ------------------------------------------------------------------ #
# Helpers                                                            #
# ------------------------------------------------------------------ #

def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict."""
    merged = dict(base)
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


async def _read_settings() -> Dict[str, Any]:
    """Read settings from DB, merged with defaults."""
    row = await db.fetch_one("SELECT data FROM system_settings ORDER BY id LIMIT 1")
    stored = row["data"] if row and row.get("data") else {}
    # asyncpg returns JSONB as a string or dict depending on the driver version
    if isinstance(stored, str):
        stored = json.loads(stored)
    return _deep_merge(DEFAULT_SETTINGS, stored)


async def _write_settings(data: Dict[str, Any]) -> None:
    """Upsert settings into DB."""
    payload = json.dumps(data)
    existing = await db.fetch_one("SELECT id FROM system_settings ORDER BY id LIMIT 1")
    if existing:
        await db.execute(
            "UPDATE system_settings SET data = $1::jsonb, updated_at = now() WHERE id = $2",
            payload, existing["id"],
        )
    else:
        await db.execute(
            "INSERT INTO system_settings (data) VALUES ($1::jsonb)",
            payload,
        )


# ------------------------------------------------------------------ #
# Pydantic model for the PUT body                                    #
# ------------------------------------------------------------------ #

class SettingsPayload(BaseModel):
    general: Dict[str, Any] | None = None
    alerts: Dict[str, Any] | None = None
    storage: Dict[str, Any] | None = None
    models: Dict[str, Any] | None = None
    privacy: Dict[str, Any] | None = None
    notifications: Dict[str, Any] | None = None

    model_config = {"extra": "allow"}


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@router.get("")
async def get_settings(_user=Depends(admin_jwt_required)):
    """Return the current settings, merged with defaults."""
    try:
        return await _read_settings()
    except Exception as e:
        logger.error(f"Failed to read settings: {e}")
        # Fall back to defaults if the table doesn't exist yet
        return DEFAULT_SETTINGS


@router.get("/defaults")
async def get_defaults(_user=Depends(admin_jwt_required)):
    """Return hard-coded default settings (useful for the Reset button)."""
    return DEFAULT_SETTINGS


@router.put("")
async def update_settings(
    payload: SettingsPayload,
    _user=Depends(admin_jwt_required),
):
    """Save the supplied settings to the database."""
    try:
        incoming = payload.model_dump(exclude_none=True)
        # Merge with existing stored values so partial updates work
        current = await _read_settings()
        merged = _deep_merge(current, incoming)
        await _write_settings(merged)
        return merged
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to save settings")


@router.post("/reset")
async def reset_settings(_user=Depends(admin_jwt_required)):
    """Reset settings to defaults in DB."""
    try:
        await _write_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS
    except Exception as e:
        logger.error(f"Failed to reset settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset settings")
