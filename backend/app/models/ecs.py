"""
VisionGuard AI - Pydantic Models for ECS APIs

Request/response models for /ecs/* endpoints.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class ECSStartRequest(BaseModel):
    """Request model for POST /ecs/start."""
    correlation_window_ms: Optional[int] = Field(
        default=None,
        description="Override correlation window (300-500ms)"
    )
    weapon_threshold: Optional[float] = Field(
        default=None,
        ge=0.0, le=1.0,
        description="Override weapon confidence threshold"
    )
    fire_threshold: Optional[float] = Field(
        default=None,
        ge=0.0, le=1.0,
        description="Override fire confidence threshold"
    )
    fall_threshold: Optional[float] = Field(
        default=None,
        ge=0.0, le=1.0,
        description="Override fall confidence threshold"
    )


class ECSControlResponse(BaseModel):
    """Response model for ECS control operations."""
    success: bool
    message: str
    status: Dict[str, Any]
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "ECS started successfully",
                "status": {
                    "name": "ECS",
                    "state": "running",
                    "pid": 12345,
                    "uptime_seconds": 0.5
                }
            }
        }


class ECSStatusResponse(BaseModel):
    """Response model for GET /ecs/status."""
    name: str = "ECS"
    state: str
    pid: Optional[int] = None
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    uptime_seconds: float = 0.0
    last_error: Optional[str] = None
    restart_count: int = 0
    is_alive: bool = False
    config: Optional[Dict[str, Any]] = None
