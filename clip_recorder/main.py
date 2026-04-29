"""
VisionGuard AI - Clip Recorder Entry Point

Standalone service that subscribes to the vg:clip:requests Redis stream
and processes clip recording + Cloudinary upload requests.

Usage:
    python -m clip_recorder.main
"""

import logging
import os
import signal
import sys
import time

import redis
import psutil
import json
import threading
import socket

from .config import ClipConfig, CLIP_REQUEST_STREAM
from .recorder import ClipRecorder


def setup_logging(level_str: str) -> None:
    """Configure root logging."""
    level = getattr(logging, level_str.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().handlers = [handler]

class MetricsReporter:
    def __init__(self, r, name):
        self.r, self.name = r, name
        self.pid = os.getpid()
        self.host = socket.gethostname()
        self.key = f"vg:metrics:{name}:{self.host}"
        self._stop = threading.Event()
    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
    def _run(self):
        p = psutil.Process(self.pid)
        p.cpu_percent(interval=None)
        while not self._stop.is_set():
            try:
                mem = p.memory_info().rss
                for c in p.children(recursive=True):
                    try: mem += c.memory_info().rss
                    except: pass
                cpu = p.cpu_percent(interval=0.5)
                for c in p.children(recursive=True):
                    try: cpu += c.cpu_percent(interval=0.5)
                    except: pass
                self.r.setex(self.key, 15, json.dumps({
                    "cpu_percent": round(cpu, 2),
                    "memory_gb": round(mem / (1024**3), 4),
                    "timestamp": time.time()
                }))
            except: pass
            time.sleep(5)
    def stop(self): self._stop.set()


def main() -> None:
    config = ClipConfig()
    setup_logging(config.log_level)

    log = logging.getLogger("clip_recorder.main")

    # --- Validate required configuration ---
    if not config.cloudinary_configured:
        log.warning(
            "Cloudinary credentials are not configured. "
            "Clips and snapshots will be saved locally but not uploaded."
        )

    if config.enable_background_buffer and not config.camera_source:
        log.error(
            "CAMERA_SOURCE environment variable is required when CLIP_ENABLE_BACKGROUND_BUFFER=true."
        )
        sys.exit(1)

    log.info("Clip recorder starting...")
    log.info(f"  Redis:         {config.redis_host}:{config.redis_port}")
    log.info(f"  Stream:        {CLIP_REQUEST_STREAM}")
    log.info(f"  Camera source: {config.camera_source or '(per-event)'}")
    log.info(f"  Background buf:{config.enable_background_buffer}")
    log.info(f"  Post seconds:  {config.clip_post_seconds}")
    log.info(f"  Clip dir:      {config.clip_dir}")
    log.info(f"  Snapshot dir:  {config.snapshot_dir}")

    # --- Connect to Redis ---
    redis_client: redis.Redis = None
    while True:
        try:
            redis_client = redis.Redis(
                host=config.redis_host,
                port=config.redis_port,
                db=0,
                decode_responses=True,
            )
            redis_client.ping()
            log.info("Connected to Redis")
            break
        except redis.ConnectionError as e:
            log.warning(f"Redis not available, retrying in 5s: {e}")
            time.sleep(5)

    # --- Start metrics reporter ---
    reporter = MetricsReporter(redis_client, "clip-recorder")
    reporter.start()
    log.info("Metrics heartbeat started")

    # --- Initialise recorder ---
    recorder = ClipRecorder(config)

    # --- Graceful shutdown ---
    _running = True

    def _shutdown(signum, _frame):
        nonlocal _running
        log.info(f"Received signal {signum} — shutting down")
        _running = False

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Track last-read stream ID for XREAD
    last_id = "$"  # Start from new messages only

    log.info(f"Listening on Redis stream: {CLIP_REQUEST_STREAM}")

    # --- Main loop ---
    while _running:
        try:
            messages = redis_client.xread(
                {CLIP_REQUEST_STREAM: last_id},
                block=2000,
                count=10,
            )

            if not messages:
                continue

            for _stream_name, entries in messages:
                for entry_id, fields in entries:
                    last_id = entry_id  # Advance cursor

                    try:
                        event_id    = fields.get("event_id", "")
                        event_type  = fields.get("event_type", "unknown")
                        camera_id   = fields.get("camera_id", "")
                        # Allow per-message camera_source override; default to config
                        camera_src  = fields.get("camera_source") or config.camera_source
                        timestamp   = float(fields.get("timestamp", time.time()))

                        if not event_id:
                            log.warning(f"Clip request missing event_id, skipping: {fields}")
                            continue

                        if not camera_src:
                            log.warning(
                                f"Clip request missing camera_source and no default configured, skipping: {fields}"
                            )
                            continue

                        log.info(
                            f"Processing clip request for event {event_id}",
                            extra={
                                "event_type": event_type,
                                "camera_id": camera_id,
                            },
                        )

                        result = recorder.record_and_upload(
                            event_id=event_id,
                            event_type=event_type,
                            camera_id=camera_id,
                            camera_source=camera_src,
                            detection_ts=timestamp,
                        )

                        log.info(
                            f"Clip pipeline done for event {event_id} | "
                            f"snapshot={result['snapshot_url']} | "
                            f"clip={result['clip_url']}"
                        )

                    except Exception as e:
                        log.error(f"Error processing clip request: {e}", exc_info=True)

        except redis.ConnectionError as e:
            log.warning(f"Redis connection lost: {e} — retrying in 5s")
            time.sleep(5)
            # Re-establish connection
            try:
                redis_client = redis.Redis(
                    host=config.redis_host,
                    port=config.redis_port,
                    db=0,
                    decode_responses=True,
                )
                redis_client.ping()
                log.info("Reconnected to Redis")
            except redis.ConnectionError:
                pass
        except Exception as e:
            log.error(f"Unexpected error in main loop: {e}", exc_info=True)
            time.sleep(1)

    recorder.shutdown()
    if reporter:
        reporter.stop()
    log.info("Clip recorder stopped")


if __name__ == "__main__":
    main()
