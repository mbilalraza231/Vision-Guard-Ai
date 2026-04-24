"""
VisionGuard AI - Clip Recorder Configuration

Reads all settings from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field

# Redis stream name for clip recording requests
CLIP_REQUEST_STREAM = "vg:clip:requests"


@dataclass
class ClipConfig:
    """Configuration for the clip recorder service."""

    # Redis
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "redis"))
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))

    # Cloudinary credentials
    cloudinary_cloud_name: str = field(
        default_factory=lambda: os.getenv("CLOUDINARY_CLOUD_NAME", "")
    )
    cloudinary_api_key: str = field(
        default_factory=lambda: os.getenv("CLOUDINARY_API_KEY", "")
    )
    cloudinary_api_secret: str = field(
        default_factory=lambda: os.getenv("CLOUDINARY_API_SECRET", "")
    )

    # Clip recording settings
    clip_pre_seconds: int = field(
        default_factory=lambda: int(os.getenv("CLIP_PRE_SECONDS", "0"))
    )
    clip_post_seconds: int = field(
        default_factory=lambda: int(os.getenv("CLIP_POST_SECONDS", "10"))
    )
    camera_fps: int = field(
        default_factory=lambda: int(os.getenv("CAMERA_FPS", "5"))
    )

    # Directories
    clip_dir: str = field(
        default_factory=lambda: os.getenv("CLIP_DIR", "/data/visionguard/clips")
    )
    snapshot_dir: str = field(
        default_factory=lambda: os.getenv("SNAPSHOT_DIR", "/data/visionguard/detections")
    )

    # Database
    db_path: str = field(
        default_factory=lambda: os.getenv("VG_DB_PATH", "/data/visionguard/events.db")
    )

    # Camera source (required, no default)
    camera_source: str = field(
        default_factory=lambda: os.getenv("CAMERA_SOURCE", "")
    )

    # Connection strategy
    enable_background_buffer: bool = field(
        default_factory=lambda: os.getenv("CLIP_ENABLE_BACKGROUND_BUFFER", "false").lower() == "true"
    )

    # Log level
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )

    @property
    def cloudinary_configured(self) -> bool:
        """True only if all three Cloudinary credentials are non-empty strings."""
        return bool(
            self.cloudinary_cloud_name
            and self.cloudinary_api_key
            and self.cloudinary_api_secret
        )
