"""
VisionGuard AI - System Settings API

GET  /api/v1/settings          → return stored settings (merged with defaults)
GET  /api/v1/settings/defaults → return hard-coded defaults only
PUT  /api/v1/settings          → upsert settings JSON

All routes require an admin JWT.
"""

import copy
import json
import logging
import os
import time
from typing import Any, Dict

import redis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.database import db
from ..auth import admin_jwt_required
from ..utils.logging import get_logger
from ..core.config import get_redis_config
from ..services.settings_defaults import (
    DEFAULT_SETTINGS,
    _deep_merge,
    _load_default_settings,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


async def _read_stored_settings() -> Dict[str, Any]:
    """Read raw settings JSON from DB (no merge with defaults)."""
    row = await db.fetch_one("SELECT data FROM system_settings ORDER BY id LIMIT 1")
    stored = row["data"] if row and row.get("data") else {}
    if isinstance(stored, str):
        stored = json.loads(stored)
    return stored if isinstance(stored, dict) else {}


async def _read_settings() -> Dict[str, Any]:
    """Read settings from DB, merged with defaults."""
    stored = await _read_stored_settings()
    return _deep_merge(_load_default_settings(), stored)


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


async def sync_settings_to_redis() -> Dict[str, Any]:
    """Sync latest PostgreSQL settings to Redis cache for stateless workers."""
    try:
        current = await _read_settings()
        r_config = get_redis_config()
        r_client = redis.Redis(**r_config)
        r_client.set("vg:system_settings", json.dumps(current))
        logger.info("Successfully synchronized system settings to Redis cache")
        return current
    except Exception as e:
        logger.warning(f"Failed to sync settings to Redis: {e}")
        return {}


# ------------------------------------------------------------------ #
# Pydantic model for the PUT body                                    #
# ------------------------------------------------------------------ #

class ResetSectionsPayload(BaseModel):
    sections: list[str]


class SettingsPayload(BaseModel):
    general: Dict[str, Any] | None = None
    cameras: Dict[str, Any] | None = None
    workers: Dict[str, Any] | None = None
    ecs: Dict[str, Any] | None = None
    cameraCapture: Dict[str, Any] | None = None
    clips: Dict[str, Any] | None = None
    systemOverrides: Dict[str, Any] | None = None
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
        return _load_default_settings()


@router.get("/defaults")
async def get_defaults(_user=Depends(admin_jwt_required)):
    """Return hard-coded default settings (useful for the Reset button)."""
    return _load_default_settings()


@router.get("/gdpr/export")
async def export_gdpr_data(_user=Depends(admin_jwt_required)):
    """
    GDPR Right to Data Portability (Article 20).
    Export all audit logs, events, alerts, contacts, settings, and camera details.
    """
    try:
        # 1. Fetch system settings
        settings_data = await _read_settings()
        
        # 2. Fetch alert contacts
        contacts_rows = await db.fetch_all("SELECT * FROM alert_contacts ORDER BY created_at DESC")
        contacts = [dict(row) for row in contacts_rows]
        
        # 3. Fetch cameras
        cameras_rows = await db.fetch_all("SELECT * FROM cameras ORDER BY created_at DESC")
        cameras = [dict(row) for row in cameras_rows]
        
        # 4. Fetch last 500 events
        events_rows = await db.fetch_all("SELECT * FROM events ORDER BY created_at DESC LIMIT 500")
        events = [dict(row) for row in events_rows]
        
        # 5. Fetch last 500 event evidence rows
        evidence_rows = await db.fetch_all("SELECT * FROM event_evidence ORDER BY created_at DESC LIMIT 500")
        evidence = [dict(row) for row in evidence_rows]
        
        # 6. Fetch last 500 alerts
        alerts_rows = await db.fetch_all("SELECT * FROM alerts ORDER BY created_at DESC LIMIT 500")
        alerts = [dict(row) for row in alerts_rows]
        
        # 7. Merge and return as a portable JSON document
        return {
            "version": "1.0",
            "exported_at": float(time.time()),
            "system_settings": settings_data,
            "cameras": cameras,
            "alert_contacts": contacts,
            "recent_events": events,
            "recent_evidence": evidence,
            "recent_alerts": alerts,
            "notice": "This document contains a portable data export of all security metrics and logs as mandated by GDPR Article 20."
        }
    except Exception as e:
        logger.error(f"GDPR Export failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compile GDPR data export")


@router.put("")
async def update_settings(
    payload: SettingsPayload,
    _user=Depends(admin_jwt_required),
):
    """Save the supplied settings to the database and sync to Redis."""
    try:
        incoming = payload.model_dump(exclude_none=True)
        # Merge partial tab updates into raw DB JSON (not into default-filled view)
        stored = await _read_stored_settings()
        stored = _deep_merge(stored, incoming)
        await _write_settings(stored)
        await sync_settings_to_redis()
        return _deep_merge(_load_default_settings(), stored)
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to save settings")


@router.post("/reset")
async def reset_settings(_user=Depends(admin_jwt_required)):
    """Reset settings to defaults in DB and sync to Redis."""
    try:
        defaults = _load_default_settings()
        await _write_settings(defaults)
        await sync_settings_to_redis()
        return defaults
    except Exception as e:
        logger.error(f"Failed to reset settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset settings")


_RESET_ALLOWED_SECTIONS = {
    "general",
    "cameras",
    "alerts",
    "storage",
    "models",
    "privacy",
    "notifications",
    "workers",
    "ecs",
    "cameraCapture",
    "clips",
    "systemOverrides",
}


@router.post("/reset-sections")
async def reset_settings_sections(
    payload: ResetSectionsPayload,
    _user=Depends(admin_jwt_required),
):
    """Reset multiple settings sections in one atomic write (e.g. Models tab)."""
    if not payload.sections:
        raise HTTPException(status_code=400, detail="No sections provided")

    try:
        defaults = _load_default_settings()
        stored = await _read_stored_settings()
        for section in payload.sections:
            if section not in _RESET_ALLOWED_SECTIONS:
                raise HTTPException(status_code=400, detail=f"Unknown section: {section}")
            stored[section] = copy.deepcopy(defaults.get(section, {}))
        await _write_settings(stored)
        await sync_settings_to_redis()
        return _deep_merge(defaults, stored)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reset sections {payload.sections}: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset settings sections")


@router.post("/reset/{section}")
async def reset_settings_section(section: str, _user=Depends(admin_jwt_required)):
    """
    Reset one settings section to env-driven defaults.

    This is intentionally a REPLACE (not merge) for that section, so the
    dashboard's per-tab Reset always returns to .env defaults.
    """
    if section not in _RESET_ALLOWED_SECTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown section: {section}")

    try:
        defaults = _load_default_settings()
        stored = await _read_stored_settings()
        stored[section] = copy.deepcopy(defaults.get(section, {}))
        await _write_settings(stored)
        await sync_settings_to_redis()
        return _deep_merge(defaults, stored)
    except Exception as e:
        logger.error(f"Failed to reset section {section}: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset settings section")

