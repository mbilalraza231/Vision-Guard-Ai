"""
VisionGuard AI - Clip Recorder Configuration

Reads all settings from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

# --- Explicitly load .env file ---
load_dotenv()


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

    # Database (PostgreSQL)
    postgres_user: str = field(default_factory=lambda: os.getenv("VG_POSTGRES_USER", "postgres"))
    postgres_password: str = field(default_factory=lambda: os.getenv("VG_POSTGRES_PASSWORD", "postgres"))
    postgres_db: str = field(default_factory=lambda: os.getenv("VG_POSTGRES_DB", "visionguard"))
    postgres_host: str = field(default_factory=lambda: os.getenv("VG_POSTGRES_HOST", "postgres"))
    postgres_port: int = field(default_factory=lambda: int(os.getenv("VG_POSTGRES_PORT", "5432")))
    database_url: str = field(default_factory=lambda: os.getenv("VG_DATABASE_URL", ""))

    # Legacy Database (SQLite)
    db_path: str = field(
        default_factory=lambda: os.getenv("VG_DB_PATH", "/data/visionguard/events.db")
    )

    @property
    def get_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

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

    # Backend URL for local evidence serving
    backend_url: str = field(
        default_factory=lambda: os.getenv("BACKEND_URL", "http://localhost:8000")
    )

    @property
    def cloudinary_configured(self) -> bool:
        """True only if all three Cloudinary credentials are non-empty strings."""
        return bool(
            self.cloudinary_cloud_name
            and self.cloudinary_api_key
            and self.cloudinary_api_secret
        )

