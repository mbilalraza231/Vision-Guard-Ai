"""
VisionGuard AI - Backend Configuration

Centralized configuration management for the FastAPI Backend Supervisor.
Environment-aware with dev/prod modes.
"""

import os
from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Provides centralized configuration for all backend components.
    Read-only at runtime - changes require restart.
    """
    
    # Application
    app_name: str = "VisionGuard AI Backend"
    app_version: str = "1.0.0"
    environment: str = Field(default="development", description="dev/production")
    debug: bool = Field(default=True, description="Enable debug mode")
    runtime_mode: str = Field(
        default="docker",
        description="Runtime mode: docker or local"
    )
    
    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    
    # Redis
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    
    # ECS Configuration
    ecs_correlation_window_ms: int = Field(default=400, description="ECS correlation window")
    ecs_hard_ttl_seconds: float = Field(default=2.0, description="ECS frame TTL")
    ecs_weapon_threshold: Optional[float] = Field(
        default=None,
        description="Weapon confidence threshold (None = ECS default)"
    )
    ecs_fire_threshold: Optional[float] = Field(
        default=None,
        description="Fire confidence threshold (None = ECS default)"
    )
    ecs_fall_threshold: Optional[float] = Field(
        default=None,
        description="Fall confidence threshold (None = ECS default)"
    )
    ecs_fire_min_frames: int = Field(default=2, description="Fire persistence frames")
    
    # Camera Configuration
    default_camera_fps: int = Field(default=5, description="Default camera FPS")
    default_motion_threshold: float = Field(default=0.02, description="Motion threshold")
    
    # Timeouts
    ecs_start_timeout: float = Field(default=10.0, description="ECS start timeout")
    ecs_stop_timeout: float = Field(default=5.0, description="ECS stop timeout")
    camera_stop_timeout: float = Field(default=10.0, description="Camera stop timeout")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: json or text")
    
    class Config:
        env_prefix = "VG_"
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        return self.environment.lower() in ("development", "dev")

    @property
    def is_docker_runtime(self) -> bool:
        return self.runtime_mode.lower() == "docker"

    @property
    def allow_local_process_control(self) -> bool:
        return not self.is_docker_runtime


# Global settings instance (singleton)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get application settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def get_redis_config() -> dict:
    """Get Redis configuration as dictionary for clients."""
    settings = get_settings()
    config = {
        "host": settings.redis_host,
        "port": settings.redis_port,
        "db": settings.redis_db,
    }
    if settings.redis_password:
        config["password"] = settings.redis_password
    return config


def get_ecs_config() -> dict:
    """Get ECS configuration for starting the service."""
    settings = get_settings()
    config = {
        "redis_host": settings.redis_host,
        "redis_port": settings.redis_port,
        "correlation_window_ms": settings.ecs_correlation_window_ms,
        "hard_ttl_seconds": settings.ecs_hard_ttl_seconds,
        "fire_min_frames": settings.ecs_fire_min_frames,
    }

    if settings.ecs_weapon_threshold is not None:
        config["weapon_confidence_threshold"] = settings.ecs_weapon_threshold
    if settings.ecs_fire_threshold is not None:
        config["fire_confidence_threshold"] = settings.ecs_fire_threshold
    if settings.ecs_fall_threshold is not None:
        config["fall_confidence_threshold"] = settings.ecs_fall_threshold

    return config
