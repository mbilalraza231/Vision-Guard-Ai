"""
VisionGuard AI - Event Classification Service Configuration

Type-safe configuration for single-instance ECS.
"""

from typing import Optional
from pydantic import BaseModel, Field, validator


class ECSConfig(BaseModel):
    """
    Configuration for Event Classification Service.
    
    ECS is a single-instance, CPU-only, deterministic classification brain.
    """
    
    # Redis configuration
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, ge=1, le=65535, description="Redis port")
    redis_db: int = Field(default=0, ge=0, description="Redis database number")
    redis_password: Optional[str] = Field(default=None, description="Redis password (optional)")
    
    # Stream configuration
    input_stream: str = Field(
        default="vg:ai:results",
        description="Redis stream to consume AI results from"
    )
    read_block_ms: int = Field(
        default=1000,
        ge=100,
        description="XREAD block timeout in milliseconds"
    )
    read_count: int = Field(
        default=100,
        ge=1,
        description="Max messages to read per XREAD call"
    )
    resume_from_latest: bool = Field(
        default=True,
        description="On restart: True = start from latest, False = read from beginning"
    )

    max_source_lag_for_persistence_sec: float = Field(
        default=20.0,
        ge=0.0,
        le=600.0,
        description="If source timestamp lags beyond this, persistence windows fallback to ingest timeline"
    )
    
    # Frame buffer configuration (v2: widened for real inference latency)
    correlation_window_ms: int = Field(
        default=2000,
        ge=300,
        le=10000,
        description="Correlation window for multi-model results (v2: 2000ms for 3-6s latency)"
    )
    hard_ttl_seconds: float = Field(
        default=15.0,
        ge=1.0,
        le=60.0,
        description="Hard TTL for frames (v2: 15s to survive p95 inference)"
    )
    
    # -----------------------------------------------------------------------
    # Entry threshold — ONLY used to filter out absolute noise from the model.
    # A detection that passes this threshold is COUNTED toward the persistence
    # window. The event fires when the count reaches min_detections, NOT on a
    # single hit. Raise these only if the model generates heavy false positives.
    # -----------------------------------------------------------------------
    weapon_confidence_threshold: float = Field(
        default=0.30,
        ge=0.0, le=1.0,
        description="Min per-frame confidence for a weapon detection to COUNT toward the persistence window"
    )
    weapon_min_detections: int = Field(
        default=3,
        ge=1,
        description="How many weapon detections within the persistence window are required to fire an event"
    )
    weapon_persistence_window_sec: float = Field(
        default=5.0,
        ge=1.0, le=60.0,
        description="Sliding window (seconds) in which weapon_min_detections must accumulate"
    )

    fire_confidence_threshold: float = Field(
        default=0.30,
        ge=0.0, le=1.0,
        description="Min per-frame confidence for a fire detection to COUNT toward the persistence window"
    )
    fire_min_detections: int = Field(
        default=3,
        ge=1,
        description="How many fire detections within the persistence window are required to fire an event"
    )
    fire_persistence_window_sec: float = Field(
        default=8.0,
        ge=1.0, le=60.0,
        description="Sliding window (seconds) in which fire_min_detections must accumulate"
    )

    fall_confidence_threshold: float = Field(
        default=0.30,
        ge=0.0, le=1.0,
        description="Min per-frame confidence for a fall detection to COUNT toward the persistence window"
    )
    fall_min_detections: int = Field(
        default=3,
        ge=1,
        description="How many fall detections within the persistence window are required to fire an event"
    )
    fall_persistence_window_sec: float = Field(
        default=6.0,
        ge=1.0, le=60.0,
        description="Sliding window (seconds) in which fall_min_detections must accumulate"
    )

    # V2: Camera history
    camera_history_window_sec: float = Field(
        default=30.0,
        ge=1.0, le=120.0,
        description="How long to keep camera detection history (must be >= largest persistence window)"
    )

    # V2: Event cooldown (deduplication — suppress repeated events after one fires)
    weapon_cooldown_seconds: float = Field(
        default=30.0,
        ge=0.0, le=300.0,
        description="Suppress duplicate weapon events for this duration after one fires"
    )
    fire_cooldown_seconds: float = Field(
        default=60.0,
        ge=0.0, le=300.0,
        description="Suppress duplicate fire events for this duration after one fires"
    )
    fall_cooldown_seconds: float = Field(
        default=30.0,
        ge=0.0, le=300.0,
        description="Suppress duplicate fall events for this duration after one fires"
    )
    
    # Output configuration (all outputs are async, non-blocking)
    enable_alerts: bool = Field(default=True, description="Enable alert dispatching")
    alert_webhook_url: Optional[str] = Field(
        default=None, 
        description="Webhook URL for alerts (None = log only)"
    )
    alert_timeout_sec: float = Field(default=5.0, ge=1.0, le=30.0, description="Webhook timeout")
    
    enable_database: bool = Field(default=True, description="Enable database writing")
    database_path: str = Field(
        default=None,
        description="SQLite database path (defaults to VG_DB_PATH env or /data/visionguard/events.db)"
    )
    database_batch_size: int = Field(default=10, ge=1, le=100, description="Events per batch write")
    model_version: str = Field(default="1.0.0", description="Model version for DB records")
    
    enable_frontend: bool = Field(default=True, description="Enable frontend publishing")
    frontend_queue_size: int = Field(default=1000, ge=100, le=10000, description="Max events in frontend queue")
    
    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format (json/text)")
    
    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'log_level must be one of {valid_levels}')
        return v.upper()
    
    @validator('log_format')
    def validate_log_format(cls, v):
        if v not in ['json', 'text']:
            raise ValueError('log_format must be "json" or "text"')
        return v
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True
        extra = 'forbid'
