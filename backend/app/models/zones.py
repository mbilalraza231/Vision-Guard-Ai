"""
VisionGuard AI - Pydantic Models for Zones APIs

Request/response models for /zones endpoints.
"""

from typing import Optional, List
from pydantic import BaseModel, Field

class ZoneCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    active_hours: Optional[str] = Field(default="24/7", max_length=100)
    max_cameras: Optional[int] = Field(default=0, ge=0)
    max_alert_recipients: Optional[int] = Field(default=0, ge=0)

class ZoneUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    active_hours: Optional[str] = Field(default=None, max_length=100)
    max_cameras: Optional[int] = Field(default=None, ge=0)
    max_alert_recipients: Optional[int] = Field(default=None, ge=0)

class ZoneResponse(BaseModel):
    id: str
    name: str
    active_hours: str
    max_cameras: int
    max_alert_recipients: int
    created_at: float

class ZoneListResponse(BaseModel):
    total: int
    zones: List[ZoneResponse]
