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
        min_length=3,
        description="Camera stream URL or source path"
    )
    name: Optional[str] = Field(
        default=None,
        description="Friendly name of the camera"
    )
    priority: Optional[str] = Field(
        default="medium",
        description="Camera priority (critical | high | medium | low)"
    )
    enabled: Optional[bool] = Field(
        default=True,
        description="Whether the camera is enabled"
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
    zone_id: Optional[str] = Field(
        default=None,
        description="Zone this camera belongs to"
    )

    @field_validator("rtsp_url")
    @classmethod
    def validate_rtsp_url(cls, v: str) -> str:
        import re
        from urllib.parse import urlparse, urlunparse
        
        v = v.strip()
        # 1. Correct IP address with dot-port typo, e.g., 192.168.0.101.8080 -> 192.168.0.101:8080
        v = re.sub(r'(\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\.(\d+)\b', r'\1:\2', v)
        
        # 2. If it is http/https URL and has no path, auto-append /video
        if v.startswith(('http://', 'https://')):
            try:
                parsed = urlparse(v)
                if not parsed.path or parsed.path == '/':
                    parsed = parsed._replace(path='/video')
                    v = urlunparse(parsed)
            except Exception:
                pass
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
