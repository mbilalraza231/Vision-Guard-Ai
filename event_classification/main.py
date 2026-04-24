"""
VisionGuard AI - ECS Entry Point

Standalone entry point for Docker container.
SINGLETON - Only one instance allowed.
"""

import sys
import os
import signal
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from event_classification import start_ecs, stop_ecs, ECSConfig

logging.basicConfig(
    level=os.getenv("ECS_LOG_LEVEL", "INFO"),
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for ECS."""
    logger.info("Starting Event Classification Service (SINGLETON)...")
    
    # Load config from environment
    config_kwargs = {
        "redis_host": os.getenv("ECS_REDIS_HOST", "localhost"),
        "redis_port": int(os.getenv("ECS_REDIS_PORT", "6379")),
        "database_path": os.getenv("ECS_DATABASE_PATH", os.getenv("VG_DB_PATH", "/data/visionguard/events.db")),
    }

    weapon_threshold = os.getenv("ECS_WEAPON_THRESHOLD")
    fire_threshold = os.getenv("ECS_FIRE_THRESHOLD")
    fall_threshold = os.getenv("ECS_FALL_THRESHOLD")
    
    weapon_min_detections = os.getenv("ECS_WEAPON_MIN_DETECTIONS")
    fire_min_detections = os.getenv("ECS_FIRE_MIN_DETECTIONS")
    fall_min_detections = os.getenv("ECS_FALL_MIN_DETECTIONS")
    
    weapon_persistence_window = os.getenv("ECS_WEAPON_PERSISTENCE_WINDOW")
    fire_persistence_window = os.getenv("ECS_FIRE_PERSISTENCE_WINDOW")
    fall_persistence_window = os.getenv("ECS_FALL_PERSISTENCE_WINDOW")
    
    hard_ttl = os.getenv("ECS_HARD_TTL_SECONDS")
    correlation_window = os.getenv("ECS_CORRELATION_WINDOW_MS")
    
    weapon_cooldown = os.getenv("ECS_WEAPON_COOLDOWN_SECONDS")
    fire_cooldown = os.getenv("ECS_FIRE_COOLDOWN_SECONDS")
    fall_cooldown = os.getenv("ECS_FALL_COOLDOWN_SECONDS")
    source_lag_tolerance = os.getenv("ECS_MAX_SOURCE_LAG_SEC")
    resume_from_latest = os.getenv("ECS_RESUME_FROM_LATEST")

    if weapon_threshold is not None:
        config_kwargs["weapon_confidence_threshold"] = float(weapon_threshold)
    if fire_threshold is not None:
        config_kwargs["fire_confidence_threshold"] = float(fire_threshold)
    if fall_threshold is not None:
        config_kwargs["fall_confidence_threshold"] = float(fall_threshold)
        
    if weapon_min_detections is not None:
        config_kwargs["weapon_min_detections"] = int(weapon_min_detections)
    if fire_min_detections is not None:
        config_kwargs["fire_min_detections"] = int(fire_min_detections)
    if fall_min_detections is not None:
        config_kwargs["fall_min_detections"] = int(fall_min_detections)
        
    if weapon_persistence_window is not None:
        config_kwargs["weapon_persistence_window_sec"] = float(weapon_persistence_window)
    if fire_persistence_window is not None:
        config_kwargs["fire_persistence_window_sec"] = float(fire_persistence_window)
    if fall_persistence_window is not None:
        config_kwargs["fall_persistence_window_sec"] = float(fall_persistence_window)
        
    if hard_ttl is not None:
        config_kwargs["hard_ttl_seconds"] = float(hard_ttl)
    if correlation_window is not None:
        config_kwargs["correlation_window_ms"] = int(correlation_window)
        
    if weapon_cooldown is not None:
        config_kwargs["weapon_cooldown_seconds"] = float(weapon_cooldown)
    if fire_cooldown is not None:
        config_kwargs["fire_cooldown_seconds"] = float(fire_cooldown)
    if fall_cooldown is not None:
        config_kwargs["fall_cooldown_seconds"] = float(fall_cooldown)
    if source_lag_tolerance is not None:
        config_kwargs["max_source_lag_for_persistence_sec"] = float(source_lag_tolerance)
    if resume_from_latest is not None:
        config_kwargs["resume_from_latest"] = resume_from_latest.lower() in ("1", "true", "yes", "on")

    config = ECSConfig(**config_kwargs)

    ecs_service = None
    
    # Setup signal handlers
    def shutdown(signum, frame):
        logger.info("Received shutdown signal, stopping ECS...")
        if ecs_service:
            stop_ecs(ecs_service)
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    
    try:
        # Start ECS
        ecs_service = start_ecs(config)
        
        # Keep running
        logger.info("ECS running. Press Ctrl+C to stop.")
        signal.pause()
        
    except Exception as e:
        logger.error(f"ECS failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
