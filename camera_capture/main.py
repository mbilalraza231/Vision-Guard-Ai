"""
VisionGuard AI - Camera Capture Entry Point

Standalone entry point for Docker container.
"""

import sys
import os
import signal
import logging
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from camera_capture import start_cameras, stop_cameras, CaptureConfig, CameraConfig

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def load_cameras_from_json(config_path: str) -> tuple[list, dict]:
    """Load enabled camera configurations and global settings from JSON file."""
    logger.info(f"Loading camera config from: {config_path}")
    
    if not os.path.exists(config_path):
        logger.error(f"Camera config not found: {config_path}")
        return [], {}

    with open(config_path, 'r') as f:
        data = json.load(f)
    
    # Get global settings
    global_config = data.get('global', {})
    motion_enabled = global_config.get('motion_detection', True)  # Default to True for backward compatibility
    
    cameras = []
    for cam_data in data.get('cameras', []): # Use .get() for robustness
        if not cam_data.get('enabled', True):
            continue
        
        # Add motion_enabled from global config
        cameras.append(CameraConfig(
            camera_id=cam_data.get('id', cam_data.get('camera_id')), # Keep original robustness
            rtsp_url=cam_data.get('source', cam_data.get('rtsp_url')), # Keep original robustness
            fps=cam_data.get('fps', 5),
            motion_threshold=cam_data.get('motion_threshold', 0.02),
            motion_enabled=motion_enabled  # Add global motion detection setting
        ))
    
    logger.info(f"Loaded {len(cameras)} cameras")
    return cameras, global_config


def main():
    """Main entry point for camera capture service."""
    logger.info("Starting Camera Capture Service...")
    
    config_path = os.getenv("CAMERA_CONFIG_PATH", "cameras.json")
    if not os.path.isabs(config_path):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            config_path
        )
    
    logger.info(f"Loading camera config from: {config_path}")
    cameras, global_config = load_cameras_from_json(config_path)
    
    if not cameras:
        logger.error("No cameras configured!")
        sys.exit(1)
    
    logger.info(f"Loaded {len(cameras)} cameras")
    
    config = CaptureConfig(
        cameras=cameras,
        retry={
            "max_retries": int(os.getenv("CAMERA_RECONNECT_RETRIES", "5")),
            "initial_backoff_seconds": float(
                os.getenv(
                    "CAMERA_RECONNECT_DELAY_SEC",
                    str(global_config.get("reconnect_delay_sec", 5)),
                )
            ),
            "max_backoff_seconds": float(os.getenv("CAMERA_RECONNECT_MAX_DELAY_SEC", "60")),
            "backoff_multiplier": float(os.getenv("CAMERA_RECONNECT_BACKOFF_MULTIPLIER", "2.0")),
        },
        redis={"host": os.getenv("REDIS_HOST", "localhost"), 
               "port": int(os.getenv("REDIS_PORT", "6379"))}
    )

    # Register camera source URLs in Redis so other services (ECS, clip-recorder)
    # can look them up by camera_id without needing hardcoded env vars.
    try:
        import redis as _redis
        _r = _redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            decode_responses=True,
        )
        for cam in cameras:
            _r.hset("vg:camera:sources", cam.camera_id, cam.rtsp_url)
        logger.info(
            f"Registered {len(cameras)} camera source(s) in Redis vg:camera:sources"
        )
    except Exception as _e:
        logger.warning(f"Could not register camera sources in Redis: {_e}")
    
    # Store manager globally for shutdown handler
    manager = None
    
    def shutdown(signum, frame):
        logger.info("Received shutdown signal, stopping cameras...")
        if manager:
            stop_cameras(manager)
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    
    try:
        manager = start_cameras(config)
        
        logger.info("Camera Capture Service running. Press Ctrl+C to stop.")
        signal.pause()
        
    except Exception as e:
        logger.error(f"Camera Capture failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
