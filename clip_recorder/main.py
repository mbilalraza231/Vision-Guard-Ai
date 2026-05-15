"""
VisionGuard AI - Clip Recorder Entry Point

Standalone service that subscribes to the vg:events:finalized Redis stream
and processes clip recording + Cloudinary upload requests.

Usage:
    python -m clip_recorder.main
"""

import asyncio
import logging
import os
import signal
import sys
import time
import json
import socket

import redis.asyncio as redis
import psutil

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
    # Ensure stdout handler is set correctly
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(level)

class MetricsReporter:
    def __init__(self, r, name):
        self.r, self.name = r, name
        self.pid = os.getpid()
        self.host = socket.gethostname()
        self.key = f"vg:metrics:{name}:{self.host}"
        self._stop = asyncio.Event()

    async def start(self):
        asyncio.create_task(self._run())

    async def _run(self):
        p = psutil.Process(self.pid)
        p.cpu_percent(interval=None)
        while not self._stop.is_set():
            try:
                mem = p.memory_info().rss
                for c in p.children(recursive=True):
                    try: mem += c.memory_info().rss
                    except: pass
                cpu = p.cpu_percent(interval=None) # Interval None for non-blocking
                for c in p.children(recursive=True):
                    try: cpu += c.cpu_percent(interval=None)
                    except: pass
                
                await self.r.setex(self.key, 15, json.dumps({
                    "cpu_percent": round(cpu, 2),
                    "memory_gb": round(mem / (1024**3), 4),
                    "timestamp": time.time()
                }))
            except Exception as e:
                logging.getLogger("clip_recorder.metrics").debug(f"Metrics error: {e}")
            
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    def stop(self): 
        self._stop.set()


async def main() -> None:
    config = ClipConfig()
    setup_logging(config.log_level)

    log = logging.getLogger("clip_recorder.main")

    # --- Validate required configuration ---
    if not config.cloudinary_configured:
        log.warning(
            "Cloudinary credentials are not configured. "
            "Clips and snapshots will be saved locally but not uploaded."
        )


    log.info("Clip recorder starting (Async Mode)...")
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
            await redis_client.ping()
            log.info("Connected to Redis")
            break
        except Exception as e:
            log.warning(f"Redis not available, retrying in 5s: {e}")
            await asyncio.sleep(5)

    # --- Start metrics reporter ---
    reporter = MetricsReporter(redis_client, "clip-recorder")
    await reporter.start()
    log.info("Metrics heartbeat started")

    # --- Initialise recorder ---
    recorder = ClipRecorder(config)

    # --- Dashcam Mode: Pre-start buffers for all known cameras ---
    if config.enable_background_buffer:
        try:
            # Fetch all cameras from the registry
            camera_sources = await redis_client.hvals("vg:camera:sources")
            if camera_sources:
                recorder.start_dashcam_buffers(camera_sources)
            else:
                log.warning("No camera sources found in Redis registry (vg:camera:sources)")
        except Exception as e:
            log.warning(f"Failed to auto-start dashcam buffers: {e}")

    # --- Graceful shutdown ---
    stop_event = asyncio.Event()

    def _signal_handler():
        log.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    # --- Track last-read stream ID for XREAD (with persistence) ---
    LAST_ID_KEY = "vg:clip:last_id"
    saved_id = await redis_client.get(LAST_ID_KEY)
    
    if saved_id:
        last_id = saved_id
        log.info(f"Resuming from saved clip request ID: {last_id}")
    else:
        # Fallback to config or latest
        last_id = "$" 
        log.info("No saved clip request ID found, starting from latest message ($)")

    log.info(f"Listening on Redis stream: {CLIP_REQUEST_STREAM}")

    # --- Main loop ---
    try:
        while not stop_event.is_set():
            try:
                messages = await redis_client.xread(
                    {CLIP_REQUEST_STREAM: last_id},
                    block=2000,
                    count=10,
                )

                if not messages:
                    continue

                for _stream_name, entries in messages:
                    for entry_id, fields in entries:
                        last_id = entry_id  # Advance cursor
                        # Persist progress
                        try:
                            await redis_client.set(LAST_ID_KEY, last_id)
                        except Exception as e:
                            log.warning(f"Failed to persist clip progress ID: {e}")

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

                            log.info(f"Processing clip request for event {event_id}")

                            # Await the async record_and_upload
                            result = await recorder.record_and_upload(
                                event_id=event_id,
                                event_type=event_type,
                                camera_id=camera_id,
                                camera_source=camera_src,
                                detection_ts=timestamp,
                            )

                            log.info(
                                f"Clip pipeline done for event {event_id} | "
                                f"snapshot={result.get('snapshot_url')} | "
                                f"clip={result.get('clip_url')}"
                            )

                        except Exception as e:
                            log.error(f"Error processing clip request: {e}", exc_info=True)

            except Exception as e:
                if not stop_event.is_set():
                    log.error(f"Unexpected error in main loop: {e}", exc_info=True)
                    await asyncio.sleep(2)

    finally:
        recorder.shutdown()
        reporter.stop()
        await redis_client.close()
        log.info("Clip recorder stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
