"""
VisionGuard AI - Pydantic Models for Events/Alerts APIs

Request/response models for /events and /alerts endpoints.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class EventType(str, Enum):
    """Types of classified events."""
    WEAPON_DETECTED = "weapon_detected"
    FIRE_DETECTED = "fire_detected"
    FALL_DETECTED = "fall_detected"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    """Event severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Event(BaseModel):
    """Classified event model."""
    event_id: str
    event_type: EventType
    severity: Severity
    camera_id: str
    frame_id: str
    timestamp: str
    confidence: float
    bbox: Optional[List[int]] = None
    model_type: str
    correlation_age_ms: Optional[float] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "cam_001_1737385973123456",
                "event_type": "weapon_detected",
                "severity": "critical",
                "camera_id": "cam_001",
                "frame_id": "cam_001_1737385973123456",
                "timestamp": "2026-01-30T12:00:00Z",
                "confidence": 0.91,
                "bbox": [100, 200, 300, 400],
                "model_type": "weapon"
            }
        }


class Alert(BaseModel):
    """Alert notification model."""
    alert_id: str
    event_id: str
    event_type: EventType
    severity: Severity
    camera_id: str
    timestamp: str
    message: str
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[str] = None


class EventListResponse(BaseModel):
    """Response model for GET /events."""
    total: int
    limit: int
    offset: int
    events: List[Event]


class AlertListResponse(BaseModel):
    """Response model for GET /alerts."""
    total: int
    unacknowledged: int
    alerts: List[Alert]


class EventQueryParams(BaseModel):
    """Query parameters for event listing."""
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    camera_id: Optional[str] = None
    event_type: Optional[EventType] = None
    severity: Optional[Severity] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


# =============================================================
# Database-backed models (new schema)
# =============================================================

class DBEvent(BaseModel):
    """Event from database with temporal fields."""
    id: str = Field(..., description="UUID v4")
    camera_id: str
    event_type: str
    severity: str
    start_ts: float = Field(..., description="Event start (epoch seconds)")
    end_ts: float = Field(..., description="Event end (epoch seconds)")
    confidence: float = Field(..., ge=0.0, le=1.0)
    model_version: str
    created_at: float
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "camera_id": "cam_001",
                "event_type": "weapon",
                "severity": "critical",
                "start_ts": 1738400000.0,
                "end_ts": 1738400000.42,
                "confidence": 0.91,
                "model_version": "1.0.0",
                "created_at": 1738400001.0
            }
        }


class DBEventListResponse(BaseModel):
    """Response model for GET /events (database)."""
    total: int
    limit: int
    offset: int
    events: List[DBEvent]


class DBAlert(BaseModel):
    """Alert from database."""
    id: str
    event_id: str
    channel: str
    status: str
    attempts: int
    last_attempt_ts: Optional[float] = None
    created_at: float
    camera_id: Optional[str] = None
    event_type: Optional[str] = None
    severity: Optional[str] = None
    confidence: Optional[float] = None
    start_ts: Optional[float] = None
    end_ts: Optional[float] = None


class DBAlertListResponse(BaseModel):
    """Response model for GET /alerts (database)."""
    total: int
    limit: int
    offset: int
    alerts: List[DBAlert]
