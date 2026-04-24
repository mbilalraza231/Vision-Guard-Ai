"""
VisionGuard AI - Pydantic Models for System APIs

Response models for /health, /status, /metrics endpoints.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response model for /health endpoint."""
    status: str = Field(description="Health status: healthy, degraded, unhealthy")
    timestamp: str = Field(description="ISO timestamp")
    version: str = Field(description="Application version")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2026-01-30T12:00:00Z",
                "version": "1.0.0"
            }
        }


class ComponentStatus(BaseModel):
    """Status of a system component."""
    name: str
    status: str  # running, stopped, degraded, error
    details: Optional[Dict[str, Any]] = None


class StatusResponse(BaseModel):
    """Response model for /status endpoint."""
    status: str = Field(description="Overall system status")
    timestamp: str
    uptime_seconds: float
    components: Dict[str, ComponentStatus]
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2026-01-30T12:00:00Z",
                "uptime_seconds": 3600.5,
                "components": {
                    "ecs": {"name": "ECS", "status": "running"},
                    "redis": {"name": "Redis", "status": "connected"},
                    "cameras": {"name": "Cameras", "status": "2/3 running"}
                }
            }
        }


class MetricsResponse(BaseModel):
    """Response model for /metrics endpoint."""
    timestamp: str
    system: Dict[str, Any]
    ecs: Optional[Dict[str, Any]] = None
    cameras: Optional[Dict[str, Any]] = None
    redis: Optional[Dict[str, Any]] = None
