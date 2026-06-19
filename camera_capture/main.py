"""
VisionGuard AI - Camera Capture Entry Point

Standalone entry point for Docker container.
"""

from camera_capture.settings_runtime import load_camera_runtime_settings
from camera_capture import start_cameras, stop_cameras, CaptureConfig, CameraConfig
import sys
import os
import signal
import logging
import json
import time
import psutil
import threading
import socket
import redis

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


class MetricsReporter:
    def __init__(self, redis_client, service_name: str):
        self.redis = redis_client
        self.service_name = service_name
        self.instance_id = socket.gethostname()
        self.key = f"vg:metrics:{service_name}:{self.instance_id}"
        self.process = psutil.Process(os.getpid())
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        # Initial call to initialize cpu_percent
        self.process.cpu_percent(interval=None)
        while not self._stop.is_set():
            try:
                # Use a small interval to get a real-time sample
                mem_bytes = self.process.memory_info().rss
                cpu_total = self.process.cpu_percent(interval=0.1)

                try:
                    children = self.process.children(recursive=True)
                    for child in children:
                        try:
                            mem_bytes += child.memory_info().rss
                            cpu_total += child.cpu_percent(interval=0.1)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

                metrics = {
                    "cpu_percent": round(cpu_total, 2),
                    "memory_gb": round(mem_bytes / (1024**3), 4),
                    "timestamp": time.time()
                }
                self.redis.setex(self.key, 15, json.dumps(metrics))
            except Exception:
                pass
            time.sleep(5)

    def stop(self):
        if self._thread:
            self._stop.set()
            self._thread.join(timeout=1.0)


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
    # Default to True for backward compatibility
    motion_enabled = global_config.get('motion_detection', True)

    cameras = []
    for cam_data in data.get('cameras', []):  # Use .get() for robustness
        if not cam_data.get('enabled', True):
            continue

        # Add motion_enabled from global config
        cameras.append(CameraConfig(
            camera_id=cam_data.get('id', cam_data.get(
                'camera_id')),  # Keep original robustness
            rtsp_url=cam_data.get('source', cam_data.get(
                'rtsp_url')),  # Keep original robustness
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

    # Load live settings from Redis (Dashboard > Camera Rules) and apply them.
    # This ensures the user's settings survive container restarts.
    queue_settings = {}
    try:
        cam_runtime = load_camera_runtime_settings()
        default_fps = cam_runtime["default_fps"]
        motion_threshold = cam_runtime["motion_threshold"]
        global_fps_target = cam_runtime["global_fps_target"]
        queue_settings = {
            "max_queue_size": cam_runtime["max_queue_size"],
            "task_ttl_seconds": cam_runtime["task_ttl_seconds"]
        }
        logger.info(
            f"Camera runtime settings (from Redis): "
            f"default_fps={default_fps}, motion_threshold={motion_threshold}, "
            f"global_fps_target={global_fps_target}, "
            f"max_queue_size={queue_settings['max_queue_size']}, "
            f"task_ttl_seconds={queue_settings['task_ttl_seconds']}"
        )
        # Apply to any camera that is using the generic cameras.json default (fps=5)
        # Per-camera overrides in cameras.json are respected and NOT changed.
        json_default_fps = global_config.get("default_fps", 5)
        for cam in cameras:
            if cam.fps == json_default_fps:
                cam.fps = default_fps
            if cam.motion_threshold == 0.02:  # Only override if still at factory default
                cam.motion_threshold = motion_threshold
    except Exception as e:
        logger.warning(
            f"Could not apply Redis camera settings, using cameras.json values: {e}")

    if not cameras:
        logger.warning("No enabled cameras configured initially.")

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
               "port": int(os.getenv("REDIS_PORT", "6379"))},
        buffer={
            "max_buffer_size": 100,
            "drop_policy": "oldest",
            "max_queue_size": queue_settings.get("max_queue_size", 1000),
            "task_ttl_seconds": queue_settings.get("task_ttl_seconds", 300)
        }
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
        # Clear the old hash to prevent stale/deleted cameras from persisting across restarts!
        _r.delete("vg:camera:sources")
        for cam in cameras:
            _r.hset("vg:camera:sources", cam.camera_id, cam.rtsp_url)
        logger.info(
            f"Registered {len(cameras)} camera source(s) in Redis vg:camera:sources"
        )
    except Exception as _e:
        logger.warning(f"Could not register camera sources in Redis: {_e}")

    # Store manager globally for shutdown handler
    manager = None
    reporter = None

    # Start metrics reporter
    try:
        r_host = os.getenv("REDIS_HOST", "localhost")
        r_port = int(os.getenv("REDIS_PORT", "6379"))
        r_client = redis.Redis(host=r_host, port=r_port)
        reporter = MetricsReporter(r_client, "camera")
        reporter.start()
        logger.info("Metrics heartbeat started for camera service")
    except Exception as e:
        logger.warning(f"Failed to start metrics reporter: {e}")

    # Shared event: Pub/Sub listener sets this to trigger instant config reload
    reload_event = threading.Event()

    # Start Pub/Sub Listener thread to instantly apply dashboard settings
    try:
        r_client_pubsub = redis.Redis(host=os.getenv(
            "REDIS_HOST", "localhost"), port=int(os.getenv("REDIS_PORT", "6379")))

        def _settings_listener():
            pubsub = r_client_pubsub.pubsub()
            try:
                pubsub.subscribe("vg:settings:updates")
                for message in pubsub.listen():
                    if message["type"] == "message":
                        # Signal the main loop to reload immediately
                        reload_event.set()
                        # Also touch file as fallback (manual edits still work)
                        if os.path.exists(config_path):
                            os.utime(config_path, None)
            except Exception as e:
                logger.warning(f"Settings Pub/Sub thread died: {e}")

        t = threading.Thread(target=_settings_listener, daemon=True)
        t.start()
        logger.info("Settings Pub/Sub listener started")
    except Exception as e:
        logger.warning(f"Failed to start Pub/Sub listener: {e}")

    def shutdown(signum, frame):
        logger.info("Received shutdown signal, stopping cameras...")
        if manager:
            stop_cameras(manager)
        if reporter:
            reporter.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        manager = start_cameras(config)
        logger.info(
            "Camera Capture Service running. Watching config file for changes...")

        last_mtime = 0.0
        if os.path.exists(config_path):
            last_mtime = os.path.getmtime(config_path)

        while True:
            # Wait up to 2s for Pub/Sub signal, or timeout for file polling fallback
            pubsub_triggered = reload_event.wait(timeout=2)
            reload_event.clear()
            if os.path.exists(config_path):
                try:
                    mtime = os.path.getmtime(config_path)
                except OSError:
                    continue

                if mtime > last_mtime or pubsub_triggered:
                    source = "Pub/Sub (instant)" if pubsub_triggered else "file poll"
                    logger.info(
                        f"Config change detected via {source}. Reloading cameras...")
                    last_mtime = mtime

                    try:
                        # Load new camera list from cameras.json
                        new_cameras, new_global_config = load_cameras_from_json(
                            config_path)

                        # Apply live Redis settings again (so dashboard changes take effect on reload)
                        try:
                            cam_runtime = load_camera_runtime_settings()
                            new_default_fps = cam_runtime["default_fps"]
                            new_motion_thresh = cam_runtime["motion_threshold"]
                            new_json_default = new_global_config.get(
                                "default_fps", 5)
                            for cam in new_cameras:
                                if cam.fps == new_json_default:
                                    cam.fps = new_default_fps
                                if cam.motion_threshold == 0.02:
                                    cam.motion_threshold = new_motion_thresh
                            logger.info(
                                f"Applied live Redis settings during hot-reload: fps={new_default_fps}, motion={new_motion_thresh}")
                        except Exception as e:
                            logger.warning(
                                f"Could not apply Redis settings during hot-reload: {e}")

                        should_run_ids = {cam.camera_id for cam in new_cameras}

                        # 1. Stop any running cameras that are no longer enabled or removed
                        active_ids = list(manager.processes.keys())
                        for cam_id in active_ids:
                            if cam_id not in should_run_ids:
                                logger.info(
                                    f"Camera '{cam_id}' has been disabled or removed. Stopping stream...")
                                try:
                                    manager.processes[cam_id].stop(timeout=5.0)
                                    manager.status[cam_id] = "stopped"

                                    # Deregister from Redis sources hash
                                    try:
                                        _r = _redis.Redis(
                                            host=os.getenv(
                                                "REDIS_HOST", "localhost"),
                                            port=int(
                                                os.getenv("REDIS_PORT", "6379")),
                                            decode_responses=True,
                                        )
                                        _r.hdel("vg:camera:sources", cam_id)
                                        _r.close()
                                    except Exception as redis_err:
                                        logger.warning(
                                            f"Could not remove camera '{cam_id}' from Redis sources: {redis_err}")
                                except Exception as err:
                                    logger.error(
                                        f"Failed to stop camera '{cam_id}': {err}")
                                manager.processes.pop(cam_id, None)

                        # 2. Update config object in manager.config.cameras
                        manager.config.cameras = new_cameras

                        # 3. Start or update any enabled cameras
                        for camera_config in new_cameras:
                            cam_id = camera_config.camera_id

                            # Check if the camera is already running
                            existing_process = manager.processes.get(cam_id)
                            if existing_process and existing_process.is_alive():
                                # Check if config actually changed (RTSP URL, FPS, etc.)
                                curr_config = existing_process.camera_config
                                if (curr_config.rtsp_url != camera_config.rtsp_url or
                                    curr_config.fps != camera_config.fps or
                                    curr_config.motion_threshold != camera_config.motion_threshold or
                                        curr_config.motion_enabled != camera_config.motion_enabled):

                                    logger.info(
                                        f"Camera '{cam_id}' configuration updated. Restarting process...")
                                    manager.restart_camera(cam_id)

                                    # Update Redis source URL
                                    try:
                                        _r = _redis.Redis(
                                            host=os.getenv(
                                                "REDIS_HOST", "localhost"),
                                            port=int(
                                                os.getenv("REDIS_PORT", "6379")),
                                            decode_responses=True,
                                        )
                                        _r.hset("vg:camera:sources",
                                                cam_id, camera_config.rtsp_url)
                                        _r.close()
                                    except Exception as redis_err:
                                        logger.warning(
                                            f"Could not update Redis source URL: {redis_err}")
                            else:
                                # Not running, start it
                                logger.info(
                                    f"Camera '{cam_id}' is enabled but not running. Starting process...")
                                try:
                                    # Create camera process
                                    from camera_capture.core.camera_process import CameraProcess
                                    process = CameraProcess(
                                        camera_config=camera_config,
                                        redis_config=manager.config.redis,
                                        buffer_config=manager.config.buffer,
                                        retry_config=manager.config.retry,
                                        shared_memory_config=manager.config.shared_memory,
                                        log_level=manager.config.logging.level,
                                        log_format=manager.config.logging.format
                                    )
                                    if process.start():
                                        manager.processes[cam_id] = process
                                        manager.status[cam_id] = "alive"

                                        # Register in Redis sources
                                        try:
                                            _r = _redis.Redis(
                                                host=os.getenv(
                                                    "REDIS_HOST", "localhost"),
                                                port=int(
                                                    os.getenv("REDIS_PORT", "6379")),
                                                decode_responses=True,
                                            )
                                            _r.hset("vg:camera:sources",
                                                    cam_id, camera_config.rtsp_url)
                                            _r.close()
                                        except Exception as redis_err:
                                            logger.warning(
                                                f"Could not register Redis source URL: {redis_err}")
                                    else:
                                        manager.status[cam_id] = "failed_to_start"
                                except Exception as err:
                                    manager.status[cam_id] = "error"
                                    logger.error(
                                        f"Error starting camera process '{cam_id}': {err}")

                    except Exception as reload_err:
                        logger.error(
                            f"Failed to reload cameras config: {reload_err}")

    except Exception as e:
        logger.error(f"Camera Capture failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
