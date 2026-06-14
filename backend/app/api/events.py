"""
VisionGuard AI - Events & Alerts API Routes

Read-only endpoints for classified events and alerts.
GET /events - Query events from database
GET /events/{id} - Get single event by UUID
GET /alerts - List alerts from database
GET /alerts/{id} - Get single alert with event metadata
"""

from alerts.config import AlertConfig
from alerts.repository import AlertRepository
from ..utils.logging import get_logger
from ..services.db_reader import get_db_reader
from ..core.database import db
from ..models.events import (
    DBEvent, DBEventListResponse,
    DBAlert, DBAlertListResponse,
    DBIncidentNote, IncidentNoteCreate,
    IncidentAcknowledgeRequest, IncidentResolveRequest
)
import os
import sys
import time
import uuid
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, Path

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


router = APIRouter(tags=["Events & Alerts"])
logger = get_logger(__name__)

_ACTION_SOURCE_LABELS = {
    "dashboard": "Dashboard",
    "email": "Email",
    "whatsapp": "WhatsApp",
}


def _normalize_action_source(source: Optional[str]) -> str:
    key = (source or "dashboard").lower().strip()
    return key if key in _ACTION_SOURCE_LABELS else "dashboard"


def _action_channel_label(source: Optional[str]) -> str:
    return _ACTION_SOURCE_LABELS[_normalize_action_source(source)]


def _actor_display_name(user_name: str, source: Optional[str]) -> str:
    return f"{user_name} via {_action_channel_label(source)}"


def _system_note_user_name(user_name: str, source: Optional[str]) -> str:
    return f"[System:{_normalize_action_source(source)}] {user_name}"


_alert_repo = None


def get_alert_repo() -> AlertRepository:
    global _alert_repo
    if _alert_repo is None:
        _alert_repo = AlertRepository(AlertConfig())
    return _alert_repo


@router.get("/events", response_model=DBEventListResponse)
async def list_events(
    limit: int = Query(default=50, ge=1, le=100,
                       description="Max events to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    camera_id: Optional[str] = Query(
        default=None, description="Filter by camera"),
    event_type: Optional[str] = Query(
        default=None, description="Filter by event type"),
    severity: Optional[str] = Query(
        default=None, description="Filter by severity"),
    status: Optional[str] = Query(
        default=None, description="Filter by status: active, acknowledged, resolved"),
    time_period: Optional[str] = Query(
        default=None, description="Time period: 24h, 7days, 30days")
) -> DBEventListResponse:
    reader = get_db_reader()

    start_ts_gte = None
    if time_period:
        now = time.time()
        if time_period == "24h":
            start_ts_gte = now - (24 * 3600)
        elif time_period == "7days":
            start_ts_gte = now - (7 * 24 * 3600)
        elif time_period == "30days":
            start_ts_gte = now - (30 * 24 * 3600)

    result = await reader.list_events(
        limit=limit,
        offset=offset,
        camera_id=camera_id,
        event_type=event_type,
        severity=severity,
        status=status,
        start_ts_gte=start_ts_gte
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
    return await reader.get_stats()


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
    empty = {
        "event_id": event_id,
        "evidence": [],
        "snapshot_url": None,
        "clip_url": None,
        "clip_status": "pending",
        "clip_error": None,
    }

    try:
        from ..core.database import db

        rows = await db.fetch_all(
            """
            SELECT id, event_id, evidence_type, storage_provider, public_url, created_at
            FROM event_evidence
            WHERE event_id = $1
            ORDER BY created_at ASC
            """,
            event_id,
        )

        event_row = await db.fetch_one(
            """
            SELECT clip_status, clip_error
            FROM events
            WHERE id = $1
            """,
            event_id,
        )

        evidence = [dict(r) for r in rows]

        snapshot_url = next(
            (r["public_url"]
             for r in evidence if r["evidence_type"] == "snapshot"),
            None,
        )
        clip_url = next(
            (r["public_url"]
             for r in evidence if r["evidence_type"] == "clip"),
            None,
        )

        # Translate local paths to API URLs
        if snapshot_url and snapshot_url.startswith("/data/visionguard/detections/"):
            if os.path.exists(snapshot_url):
                filename = os.path.basename(snapshot_url)
                snapshot_url = f"/detections/images/{filename}"
            else:
                logger.warning(
                    f"Local snapshot file missing from disk: {snapshot_url}")
                snapshot_url = None

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

    event = await reader.get_event(event_id)

    if event is None:
        raise HTTPException(
            status_code=404,
            detail=f"Event {event_id} not found"
        )

    return DBEvent(**event)


@router.get("/alerts", response_model=DBAlertListResponse)
async def list_alerts(
    limit: int = Query(default=50, ge=1, le=100,
                       description="Max alerts to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    status: Optional[str] = Query(
        default=None, description="Filter by status"),
    severity: Optional[str] = Query(
        default=None, description="Filter by severity"),
    camera_id: Optional[str] = Query(
        default=None, description="Filter by camera"),
    time_period: Optional[str] = Query(
        default=None, description="Time period: 24h, 7days, 30days")
) -> DBAlertListResponse:
    repo = get_alert_repo()

    start_ts_gte = None
    if time_period:
        now = time.time()
        if time_period == "24h":
            start_ts_gte = now - (24 * 3600)
        elif time_period == "7days":
            start_ts_gte = now - (7 * 24 * 3600)
        elif time_period == "30days":
            start_ts_gte = now - (30 * 24 * 3600)

    result = await repo.list_alerts(
        limit=limit,
        offset=offset,
        status=status,
        severity=severity,
        camera_id=camera_id,
        start_ts_gte=start_ts_gte
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

    alert = await repo.get_alert_with_event(alert_id)

    if alert is None:
        raise HTTPException(
            status_code=404,
            detail=f"Alert {alert_id} not found"
        )

    return DBAlert(**alert)


@router.get("/events/{event_id}/notes", response_model=List[DBIncidentNote])
async def list_incident_notes(
    event_id: str = Path(..., description="Event UUID")
) -> List[DBIncidentNote]:
    """Get all investigation notes for a specific incident."""
    # Verify event exists first
    reader = get_db_reader()
    event = await reader.get_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=404,
            detail=f"Incident {event_id} not found"
        )

    rows = await db.fetch_all(
        """
        SELECT id, event_id, content, created_at, user_name
        FROM incident_notes
        WHERE event_id = $1
        ORDER BY created_at DESC
        """,
        event_id,
    )
    return [DBIncidentNote(**r) for r in rows]


@router.post("/events/{event_id}/notes", response_model=DBIncidentNote)
async def create_incident_note(
    payload: IncidentNoteCreate,
    event_id: str = Path(..., description="Event UUID")
) -> DBIncidentNote:
    """Add a post-resolution follow-up note to an incident."""
    # Verify event exists first
    reader = get_db_reader()
    event = await reader.get_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=404,
            detail=f"Incident {event_id} not found"
        )

    if event.get("status") != "resolved":
        raise HTTPException(
            status_code=400,
            detail="Post-resolution notes can only be added after the incident is resolved.",
        )

    note_id = str(uuid.uuid4())
    created_at = time.time()

    await db.execute(
        """
        INSERT INTO incident_notes (id, event_id, content, created_at, user_name)
        VALUES ($1, $2, $3, $4, $5)
        """,
        note_id,
        event_id,
        payload.content,
        created_at,
        payload.user_name,
    )

    return DBIncidentNote(
        id=note_id,
        event_id=event_id,
        content=payload.content,
        created_at=created_at,
        user_name=payload.user_name or "Security Operator"
    )


@router.put("/events/{event_id}/acknowledge", response_model=DBEvent)
async def acknowledge_incident(
    payload: IncidentAcknowledgeRequest,
    event_id: str = Path(..., description="Event UUID")
) -> DBEvent:
    """Acknowledge an active event."""
    reader = get_db_reader()
    event = await reader.get_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=404, detail=f"Incident {event_id} not found")

    # Race condition check
    if event.get("status") == "acknowledged":
        raise HTTPException(
            status_code=400,
            detail=f"This incident was already acknowledged by {event.get('acknowledged_by')}"
        )
    elif event.get("status") == "resolved":
        raise HTTPException(
            status_code=400,
            detail=f"This incident was already resolved by {event.get('resolved_by')}"
        )

    now_ts = time.time()
    actor = _actor_display_name(payload.user_name, payload.source)
    await db.execute(
        """
        UPDATE events
        SET status = 'acknowledged',
            acknowledged_by = $1,
            acknowledged_at = $2
        WHERE id = $3
        """,
        actor,
        now_ts,
        event_id,
    )

    # Automatically post a system note
    note_id = str(uuid.uuid4())
    channel = _action_channel_label(payload.source)
    system_content = f"Acknowledged"
    await db.execute(
        """
        INSERT INTO incident_notes (id, event_id, content, created_at, user_name)
        VALUES ($1, $2, $3, $4, $5)
        """,
        note_id,
        event_id,
        system_content,
        now_ts,
        _system_note_user_name(payload.user_name, payload.source),
    )

    updated_event = await reader.get_event(event_id)
    return DBEvent(**updated_event)


@router.put("/events/{event_id}/resolve", response_model=DBEvent)
async def resolve_incident(
    payload: IncidentResolveRequest,
    event_id: str = Path(..., description="Event UUID")
) -> DBEvent:
    """Resolve an event."""
    reader = get_db_reader()
    event = await reader.get_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=404, detail=f"Incident {event_id} not found")

    if event.get("status") == "resolved":
        raise HTTPException(
            status_code=400,
            detail=f"This incident was already resolved by {event.get('resolved_by')}"
        )

    now_ts = time.time()
    actor = _actor_display_name(payload.user_name, payload.source)
    await db.execute(
        """
        UPDATE events
        SET status = 'resolved',
            resolved_by = $1,
            resolved_at = $2,
            resolution = $3
        WHERE id = $4
        """,
        actor,
        now_ts,
        payload.resolution,
        event_id,
    )

    # Automatically post a system note
    note_id = str(uuid.uuid4())
    channel = _action_channel_label(payload.source)
    system_content = f"Resolved ({payload.resolution})"
    if payload.content and payload.content.strip():
        system_content += f"\n\"{payload.content.strip()}\""

    await db.execute(
        """
        INSERT INTO incident_notes (id, event_id, content, created_at, user_name)
        VALUES ($1, $2, $3, $4, $5)
        """,
        note_id,
        event_id,
        system_content,
        now_ts,
        _system_note_user_name(payload.user_name, payload.source),
    )

    updated_event = await reader.get_event(event_id)
    return DBEvent(**updated_event)


@router.get("/events/{event_id}/public")
async def get_public_event(
    event_id: str = Path(..., description="Event UUID"),
    token: str = Query(..., description="Access token for public view")
) -> dict:
    """Get event data for public view with token validation."""
    reader = get_db_reader()
    
    # Validate token - check if it exists in alert_contacts or generate a simple validation
    # For now, we'll use a simple token validation that checks if the token is not empty
    # In production, this should validate against a stored token in the database
    if not token or len(token) < 10:
        raise HTTPException(status_code=401, detail="Invalid access token")
    
    event = await reader.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Incident {event_id} not found")
    
    return event


@router.put("/events/{event_id}/public/acknowledge")
async def public_acknowledge_incident(
    payload: IncidentAcknowledgeRequest,
    event_id: str = Path(..., description="Event UUID"),
    token: str = Query(..., description="Access token for public view")
) -> DBEvent:
    """Acknowledge an event via public link with token validation."""
    # Validate token
    if not token or len(token) < 10:
        raise HTTPException(status_code=401, detail="Invalid access token")
    
    reader = get_db_reader()
    event = await reader.get_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=404, detail=f"Incident {event_id} not found")

    # Race condition check
    if event.get("status") == "acknowledged":
        raise HTTPException(
            status_code=400,
            detail=f"This incident was already acknowledged by {event.get('acknowledged_by')}"
        )
    elif event.get("status") == "resolved":
        raise HTTPException(
            status_code=400,
            detail=f"This incident was already resolved by {event.get('resolved_by')}"
        )

    now_ts = time.time()
    actor = _actor_display_name(payload.user_name, payload.source)
    await db.execute(
        """
        UPDATE events
        SET status = 'acknowledged',
            acknowledged_by = $1,
            acknowledged_at = $2
        WHERE id = $3
        """,
        actor,
        now_ts,
        event_id,
    )

    # Automatically post a system note
    note_id = str(uuid.uuid4())
    channel = _action_channel_label(payload.source)
    system_content = f"Acknowledged"
    await db.execute(
        """
        INSERT INTO incident_notes (id, event_id, content, created_at, user_name)
        VALUES ($1, $2, $3, $4, $5)
        """,
        note_id,
        event_id,
        system_content,
        now_ts,
        _system_note_user_name(payload.user_name, payload.source),
    )

    updated_event = await reader.get_event(event_id)
    return DBEvent(**updated_event)


@router.put("/events/{event_id}/public/resolve")
async def public_resolve_incident(
    payload: IncidentResolveRequest,
    event_id: str = Path(..., description="Event UUID"),
    token: str = Query(..., description="Access token for public view")
) -> DBEvent:
    """Resolve an event via public link with token validation."""
    # Validate token
    if not token or len(token) < 10:
        raise HTTPException(status_code=401, detail="Invalid access token")
    
    reader = get_db_reader()
    event = await reader.get_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=404, detail=f"Incident {event_id} not found")

    if event.get("status") == "resolved":
        raise HTTPException(
            status_code=400,
            detail=f"This incident was already resolved by {event.get('resolved_by')}"
        )

    now_ts = time.time()
    actor = _actor_display_name(payload.user_name, payload.source)
    await db.execute(
        """
        UPDATE events
        SET status = 'resolved',
            resolved_by = $1,
            resolved_at = $2,
            resolution = $3
        WHERE id = $4
        """,
        actor,
        now_ts,
        payload.resolution,
        event_id,
    )

    # Automatically post a system note
    note_id = str(uuid.uuid4())
    channel = _action_channel_label(payload.source)
    system_content = f"Resolved ({payload.resolution})"
    if payload.content and payload.content.strip():
        system_content += f"\n\"{payload.content.strip()}\""

    await db.execute(
        """
        INSERT INTO incident_notes (id, event_id, content, created_at, user_name)
        VALUES ($1, $2, $3, $4, $5)
        """,
        note_id,
        event_id,
        system_content,
        now_ts,
        _system_note_user_name(payload.user_name, payload.source),
    )

    updated_event = await reader.get_event(event_id)
    return DBEvent(**updated_event)


@router.post("/events/{event_id}/public/notes")
async def public_create_incident_note(
    payload: IncidentNoteCreate,
    event_id: str = Path(..., description="Event UUID"),
    token: str = Query(..., description="Access token for public view")
) -> DBIncidentNote:
    """Add a note via public link with token validation."""
    # Validate token
    if not token or len(token) < 10:
        raise HTTPException(status_code=401, detail="Invalid access token")
    
    # Verify event exists first
    reader = get_db_reader()
    event = await reader.get_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=404,
            detail=f"Incident {event_id} not found"
        )

    if event.get("status") != "resolved":
        raise HTTPException(
            status_code=400,
            detail="Post-resolution notes can only be added after the incident is resolved.",
        )

    note_id = str(uuid.uuid4())
    created_at = time.time()

    await db.execute(
        """
        INSERT INTO incident_notes (id, event_id, content, created_at, user_name)
        VALUES ($1, $2, $3, $4, $5)
        """,
        note_id,
        event_id,
        payload.content,
        created_at,
        payload.user_name,
    )

    return DBIncidentNote(
        id=note_id,
        event_id=event_id,
        content=payload.content,
        created_at=created_at,
        user_name=payload.user_name or "Alert Contact"
    )
