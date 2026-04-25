"""
VisionGuard AI - Events & Alerts API Routes

Read-only endpoints for classified events and alerts.
GET /events - Query events from database
GET /events/{id} - Get single event by UUID
GET /alerts - List alerts from database
GET /alerts/{id} - Get single alert with event metadata
"""

import sys
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from ..models.events import (
    DBEvent, DBEventListResponse,
    DBAlert, DBAlertListResponse
)
from ..services.db_reader import get_db_reader
from ..utils.logging import get_logger
from alerts.repository import AlertRepository
from alerts.config import AlertConfig

router = APIRouter(tags=["Events & Alerts"])
logger = get_logger(__name__)

_alert_repo = None

def get_alert_repo() -> AlertRepository:
    global _alert_repo
    if _alert_repo is None:
        _alert_repo = AlertRepository(AlertConfig())
    return _alert_repo


@router.get("/events", response_model=DBEventListResponse)
async def list_events(
    limit: int = Query(default=50, ge=1, le=100, description="Max events to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    camera_id: Optional[str] = Query(default=None, description="Filter by camera"),
    event_type: Optional[str] = Query(default=None, description="Filter by event type"),
    severity: Optional[str] = Query(default=None, description="Filter by severity")
) -> DBEventListResponse:
    reader = get_db_reader()
    
    result = reader.list_events(
        limit=limit,
        offset=offset,
        camera_id=camera_id,
        event_type=event_type,
        severity=severity
    )
    
    events = [DBEvent(**e) for e in result["events"]]
    
    return DBEventListResponse(
        total=result["total"],
        limit=result["limit"],
        offset=result["offset"],
        events=events
    )


@router.get("/events/stats", response_model=dict)
async def get_event_stats() -> dict:
    reader = get_db_reader()
    return reader.get_stats()


@router.get("/events/{event_id}/evidence", response_model=dict)
async def get_event_evidence(
    event_id: str = Path(..., description="Event UUID")
) -> dict:
    """
    Return snapshot and clip evidence for an event.

    Queries event_evidence table for all rows matching event_id.
    Returns snapshot_url, clip_url (first match each), and full evidence list.
    Never raises 500 — returns error key on exception.
    """
    import sqlite3 as _sqlite3

    db_path = os.getenv("VG_DB_PATH", "/data/visionguard/events.db")
    empty = {
        "event_id": event_id,
        "evidence": [],
        "snapshot_url": None,
        "clip_url": None,
        "clip_status": "pending",
        "clip_error": None,
    }

    try:
        if not os.path.exists(db_path):
            return empty

        conn = _sqlite3.connect(db_path)
        conn.row_factory = _sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, event_id, evidence_type, storage_provider, public_url, created_at
            FROM event_evidence
            WHERE event_id = ?
            ORDER BY created_at ASC
            """,
            (event_id,),
        )
        rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT clip_status, clip_error
            FROM events
            WHERE id = ?
            """,
            (event_id,),
        )
        event_row = cursor.fetchone()
        conn.close()

        evidence = [dict(r) for r in rows]

        snapshot_url = next(
            (r["public_url"] for r in evidence if r["evidence_type"] == "snapshot"),
            None,
        )
        clip_url = next(
            (r["public_url"] for r in evidence if r["evidence_type"] == "clip"),
            None,
        )

        # Translate local paths to API URLs
        if snapshot_url and snapshot_url.startswith("/data/visionguard/detections/"):
            filename = os.path.basename(snapshot_url)
            snapshot_url = f"/detections/images/{filename}"
            
        if clip_url and clip_url.startswith("/data/visionguard/clips/"):
            filename = os.path.basename(clip_url)
            clip_url = f"/detections/clips/{filename}"

        clip_status = "pending"
        clip_error = None
        if event_row:
            clip_status = event_row["clip_status"] or "pending"
            clip_error = event_row["clip_error"]

        return {
            "event_id": event_id,
            "evidence": evidence,
            "snapshot_url": snapshot_url,
            "clip_url": clip_url,
            "clip_status": clip_status,
            "clip_error": clip_error,
        }

    except Exception as e:
        logger.error(f"Error fetching evidence for event {event_id}: {e}")
        return {**empty, "error": str(e)}


@router.get("/events/{event_id}", response_model=DBEvent)
async def get_event(
    event_id: str = Path(..., description="Event UUID")
) -> DBEvent:
    reader = get_db_reader()
    
    event = reader.get_event(event_id)
    
    if event is None:
        raise HTTPException(
            status_code=404,
            detail=f"Event {event_id} not found"
        )
    
    return DBEvent(**event)


@router.get("/alerts", response_model=DBAlertListResponse)
async def list_alerts(
    limit: int = Query(default=50, ge=1, le=100, description="Max alerts to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    severity: Optional[str] = Query(default=None, description="Filter by severity"),
    camera_id: Optional[str] = Query(default=None, description="Filter by camera")
) -> DBAlertListResponse:
    repo = get_alert_repo()
    
    result = repo.list_alerts(
        limit=limit,
        offset=offset,
        status=status,
        severity=severity,
        camera_id=camera_id
    )
    
    alerts = [DBAlert(**a) for a in result["alerts"]]
    
    return DBAlertListResponse(
        total=result["total"],
        limit=result["limit"],
        offset=result["offset"],
        alerts=alerts
    )


@router.get("/alerts/{alert_id}", response_model=DBAlert)
async def get_alert(
    alert_id: str = Path(..., description="Alert UUID")
) -> DBAlert:
    repo = get_alert_repo()
    
    alert = repo.get_alert_with_event(alert_id)
    
    if alert is None:
        raise HTTPException(
            status_code=404,
            detail=f"Alert {alert_id} not found"
        )
    
    return DBAlert(**alert)
