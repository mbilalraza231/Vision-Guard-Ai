"""
Camera Stream Prometheus Metrics (Parent Process Only)

These gauges/counters are updated by a background thread in the MAIN process.
They read frame counts from Redis keys written by child camera processes.

Port: 8004
"""
import os
import json
import time
import logging
import threading
import redis
from prometheus_client import start_http_server, Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# 1. FRAMES COUNTER - total frames processed by all cameras
FRAMES_TOTAL = Counter(
    'vg_camera_frames_total',
    'Total camera frames evaluated by status',
    ['camera_id', 'status']
)

# 2. ACTIVE STREAMS GAUGE - how many cameras are currently running
ACTIVE_STREAMS = Gauge(
    'vg_camera_active_streams',
    'Current number of active camera streams'
)

# 3. FRAME INGESTION LATENCY
INGEST_LATENCY = Histogram(
    'vg_camera_ingest_duration_seconds',
    'Camera frame ingestion and shared-ram write latency in seconds',
    ['camera_id'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1)
)

# 4. LAST FRAME TIMESTAMP GAUGE (Stall Detection)
LAST_FRAME_TIMESTAMP = Gauge(
    'vg_camera_last_frame_timestamp_seconds',
    'Unix timestamp of the last frame received per camera',
    ['camera_id']
)


class PrometheusMetricsBridge:
    """
    Bridge between child camera processes and Prometheus metrics.
    
    Child processes write frame counts to Redis. This bridge runs in the 
    MAIN process and reads those Redis keys every 5 seconds to update 
    the Prometheus gauges/counters that the HTTP server exposes.
    """
    
    def __init__(self, redis_host="redis", redis_port=6379):
        self.redis_host = redis_host
        self.redis_port = redis_port
        self._stop = threading.Event()
        self._thread = None
        self._last_frames = {}  # camera_id -> last known frame count
        self._client = None
    
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="prom-bridge")
        self._thread.start()
        logger.info("Prometheus metrics bridge started")
    
    def _get_redis(self):
        if self._client is None:
            try:
                self._client = redis.Redis(
                    host=self.redis_host, 
                    port=self.redis_port, 
                    decode_responses=True,
                    socket_timeout=2,
                    socket_connect_timeout=2
                )
                self._client.ping()
            except Exception as e:
                logger.debug(f"Redis connection failed: {e}")
                self._client = None
        return self._client
    
    def _run(self):
        while not self._stop.is_set():
            try:
                r = self._get_redis()
                if r:
                    self._update_active_streams(r)
                    self._update_frame_counts(r)
            except Exception as e:
                logger.debug(f"Prometheus bridge error: {e}")
                self._client = None
            self._stop.wait(3.0)
    
    def _update_active_streams(self, r):
        """Count how many cameras are actively sending heartbeats."""
        try:
            keys = r.keys("vg:metrics:camera:*:fps")
            active = 0
            for key in keys:
                val = r.get(key)
                if val:
                    active += 1
            ACTIVE_STREAMS.set(active)
        except Exception:
            pass
    
    def _update_frame_counts(self, r):
        """Read per-camera frame counts from Redis and update the counter."""
        try:
            keys = r.keys("vg:metrics:camera:*:frames")
            for key in keys:
                try:
                    val = r.get(key)
                    if val:
                        data = json.loads(val)
                        cam_id = data.get("camera_id", "unknown")
                        current = data.get("frames_processed", 0)
                        last = self._last_frames.get(cam_id, 0)
                        if current > last:
                            diff = current - last
                            FRAMES_TOTAL.labels(camera_id=cam_id, status="ingested").inc(diff)
                            LAST_FRAME_TIMESTAMP.labels(camera_id=cam_id).set_to_current_time()
                            self._last_frames[cam_id] = current
                        elif current < last:
                            FRAMES_TOTAL.labels(camera_id=cam_id, status="ingested").inc(current)
                            LAST_FRAME_TIMESTAMP.labels(camera_id=cam_id).set_to_current_time()
                            self._last_frames[cam_id] = current
                        elif current < last:
                            FRAMES_TOTAL.labels(camera_id=cam_id, status="ingested").inc(current)
                            LAST_FRAME_TIMESTAMP.labels(camera_id=cam_id).set_to_current_time()
                            self._last_frames[cam_id] = current
                except Exception:
                    pass
        except Exception:
            pass
    
    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)


def start_metrics_server(port: int = 8004):
    """Start Prometheus HTTP metrics server."""
    try:
        start_http_server(port)
        logger.info(f"Prometheus metrics server started on port {port}")
    except Exception as e:
        logger.error(f"Failed to start Prometheus server on port {port}: {e}")
