"""
VisionGuard AI - Pydantic Models for Camera APIs

Request/response models for /cameras/* endpoints.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator


class CameraRegisterRequest(BaseModel):
    """Request model for POST /cameras/register."""
    camera_id: str = Field(
        min_length=1,
        max_length=50,
        description="Unique camera identifier"
    )
    rtsp_url: str = Field(
        min_length=10,
        description="RTSP stream URL"
    )
    fps: Optional[int] = Field(
        default=5,
        ge=1, le=30,
        description="Frames per second"
    )
    motion_threshold: Optional[float] = Field(
        default=0.02,
        ge=0.0, le=1.0,
        description="Motion detection threshold"
    )
    
    @field_validator('rtsp_url')
    @classmethod
    def validate_rtsp_url(cls, v: str) -> str:
        if not v.startswith(('rtsp://', 'rtsps://')):
            raise ValueError('URL must start with rtsp:// or rtsps://')
        return v


class CameraResponse(BaseModel):
    """Response model for camera operations."""
    success: bool
    message: str
    camera: Optional[Dict[str, Any]] = None


class CameraStatusResponse(BaseModel):
    """Response model for single camera status."""
    camera_id: str
    rtsp_url: str
    fps: int
    motion_threshold: float
    enabled: bool
    is_running: bool
    registered_at: str
    started_at: Optional[str] = None
    stopped_at: Optional[str] = None
    frames_captured: int = 0
    frames_with_motion: int = 0
    last_error: Optional[str] = None


class AllCamerasStatusResponse(BaseModel):
    """Response model for all cameras status."""
    total: int
    running: int
    stopped: int
    cameras: Dict[str, CameraStatusResponse]
