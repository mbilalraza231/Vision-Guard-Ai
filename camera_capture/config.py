"""
VisionGuard AI - Camera Capture Module Configuration

This module defines Pydantic models for type-safe configuration.
Configuration is injected by FastAPI, not read from files.
"""

from typing import Optional, List
from pydantic import BaseModel, Field, validator


class CameraConfig(BaseModel):
    """Configuration for a single camera."""
    
    camera_id: str = Field(..., description="Unique camera identifier")
    rtsp_url: str = Field(..., description="RTSP stream URL")
    fps: int = Field(default=5, ge=1, le=30, description="Frames per second to capture")
    motion_threshold: float = Field(
        default=0.02,
        ge=0.0,
        le=1.0,
        description="Motion detection threshold (0.0-1.0, percentage of frame with motion)"
    )
    motion_enabled: bool = Field(
        default=True,
        description="Enable/disable motion detection for this camera"
    )
    
    @validator('rtsp_url')
    def validate_rtsp_url(cls, v):
        # Allow RTSP/RTMP/HTTP/HTTPS URLs or local file paths
        if not v.startswith(('rtsp://', 'rtmp://', 'http://', 'https://', '/', './')):
            raise ValueError('URL must start with rtsp://, rtmp://, http://, https://, or be a valid file path')
        return v


class RedisConfig(BaseModel):
    """Redis connection configuration."""
    
    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, ge=1, le=65535, description="Redis port")
    db: int = Field(default=0, ge=0, description="Redis database number")
    password: Optional[str] = Field(default=None, description="Redis password (if required)")
    socket_timeout: int = Field(default=5, ge=1, description="Socket timeout in seconds")
    retry_on_timeout: bool = Field(default=True, description="Retry on timeout")


class SharedMemoryConfig(BaseModel):
    """Shared memory configuration."""
    
    max_frame_size_mb: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum frame size in MB"
    )
    cleanup_interval_seconds: int = Field(
        default=300,
        ge=60,
        description="Interval for cleaning up stale shared memory blocks"
    )


class RetryConfig(BaseModel):
    """Retry and backoff configuration."""
    
    max_retries: int = Field(default=5, ge=1, description="Maximum retry attempts")
    initial_backoff_seconds: float = Field(
        default=1.0,
        ge=0.1,
        description="Initial backoff duration"
    )
    max_backoff_seconds: float = Field(
        default=60.0,
        ge=1.0,
        description="Maximum backoff duration"
    )
    backoff_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        description="Backoff multiplier for exponential backoff"
    )


class BufferConfig(BaseModel):
    """Buffer configuration for Redis unavailability."""
    
    max_buffer_size: int = Field(
        default=100,
        ge=10,
        description="Maximum number of tasks to buffer when Redis is unavailable"
    )
    drop_policy: str = Field(
        default="oldest",
        description="Policy for dropping tasks when buffer is full (oldest/newest)"
    )
    
    @validator('drop_policy')
    def validate_drop_policy(cls, v):
        if v not in ['oldest', 'newest']:
            raise ValueError('drop_policy must be "oldest" or "newest"')
        return v


class LoggingConfig(BaseModel):
    """Logging configuration."""
    
    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="json", description="Log format (json/text)")
    
    @validator('level')
    def validate_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'level must be one of {valid_levels}')
        return v.upper()
    
    @validator('format')
    def validate_format(cls, v):
        if v not in ['json', 'text']:
            raise ValueError('format must be "json" or "text"')
        return v


class CaptureConfig(BaseModel):
    """Top-level configuration for the camera capture module."""
    
    cameras: List[CameraConfig] = Field(..., description="List of camera configurations")
    redis: RedisConfig = Field(default_factory=RedisConfig, description="Redis configuration")
    shared_memory: SharedMemoryConfig = Field(
        default_factory=SharedMemoryConfig,
        description="Shared memory configuration"
    )
    retry: RetryConfig = Field(default_factory=RetryConfig, description="Retry configuration")
    buffer: BufferConfig = Field(default_factory=BufferConfig, description="Buffer configuration")
    logging: LoggingConfig = Field(default_factory=LoggingConfig, description="Logging configuration")
    
    @validator('cameras')
    def validate_cameras(cls, v):
        if not v:
            raise ValueError('At least one camera must be configured')
        
        # Check for duplicate camera IDs
        camera_ids = [cam.camera_id for cam in v]
        if len(camera_ids) != len(set(camera_ids)):
            raise ValueError('Duplicate camera IDs found')
        
        return v
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True
        extra = 'forbid'  # Prevent unknown fields
