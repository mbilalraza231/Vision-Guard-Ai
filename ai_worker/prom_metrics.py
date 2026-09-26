"""
AI Worker Prometheus Metrics (Parent Process Only)

These metrics are updated via a bridge that reads detection stats from Redis.
Port: varies per worker (8001-weapon, 8002-fire, 8003-fall)
"""
import os
import json
import time
import logging
import threading
import redis
from prometheus_client import start_http_server, Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

INFERS_TOTAL = Counter(
    'vg_ai_inferences_total',
    'Total AI inferences by model and status',
    ['model_type', 'status']
)

INFERENCE_LATENCY = Histogram(
    'vg_ai_inference_duration_seconds',
    'AI inference latency in seconds',
    ['model_type'],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

DETECTIONS_TOTAL = Counter(
    'vg_ai_detections_total',
    'Total confirmed detections by model type and label',
    ['model_type', 'label']
)

QUEUE_DEPTH = Gauge(
    'vg_ai_queue_depth',
    'Frame task queue backlog depth in Redis',
    ['queue_name']
)

LAST_DETECTION_TIMESTAMP = Gauge(
    'vg_ai_last_detection_timestamp_seconds',
    'Unix timestamp of the last threat detection by model type',
    ['model_type']
)


class AIWorkerMetricsBridge:
    """
    Bridge that reads AI worker inference stats & queue lengths from Redis
    and updates Prometheus counters/gauges.
    """
    
    def __init__(self, model_type, redis_host="redis", redis_port=6379):
        self.model_type = model_type
        self.redis_host = redis_host
        self.redis_port = redis_port
        self._stop = threading.Event()
        self._thread = None
        self._client = None
        self._last_publish_count = 0
        self._last_detection_count = 0
    
    def start(self):
        # Pre-initialize counters and histogram buckets on startup
        try:
            INFERS_TOTAL.labels(model_type=self.model_type, status="completed").inc(0)
            DETECTIONS_TOTAL.labels(model_type=self.model_type, label=self.model_type).inc(0)
            INFERENCE_LATENCY.labels(model_type=self.model_type).observe(0.001)
        except Exception as e:
            logger.warning(f"Error pre-initializing metrics: {e}")
            
        self._thread = threading.Thread(target=self._run, daemon=True, name="ai-prom-bridge")
        self._thread.start()
        logger.info(f"AI worker Prometheus bridge started for {self.model_type}")
    
    def _get_redis(self):
        if self._client is None:
            try:
                self._client = redis.Redis(
                    host=self.redis_host, port=self.redis_port,
                    decode_responses=True, socket_timeout=2, socket_connect_timeout=2
                )
                self._client.ping()
            except Exception:
                self._client = None
        return self._client
    
    def _run(self):
        import random
        while not self._stop.is_set():

            try:
                r = self._get_redis()
                if r:
                    self._update_from_redis(r)
                    self._update_queue_depths(r)
            except Exception:
                self._client = None
            self._stop.wait(3.0)
    
    def _update_from_redis(self, r):
        """Read worker stats from Redis and update Prometheus."""
        try:
            det_key = f"vg:metrics:worker:{self.model_type}:detections"
            val = r.get(det_key)
            if val:
                current_detections = int(val)
                if current_detections > self._last_detection_count:
                    det_diff = current_detections - self._last_detection_count
                    DETECTIONS_TOTAL.labels(model_type=self.model_type, label=self.model_type).inc(det_diff)
                    LAST_DETECTION_TIMESTAMP.labels(model_type=self.model_type).set_to_current_time()
                    self._last_detection_count = current_detections
        except Exception as e:
            logger.warning(f"Error in metrics bridge update: {e}")
    def _update_queue_depths(self, r):
        """Monitor input queue depths."""
        try:
            for q_name in ["vg:critical", "vg:high", "vg:medium"]:
                q_len = r.zcard(q_name) or 0
                QUEUE_DEPTH.labels(queue_name=q_name).set(q_len)
        except Exception:
            pass
    
    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)


def start_metrics_server(port: int):
    try:
        start_http_server(port)
        logger.info(f"AI Worker Prometheus metrics server started on port {port}")
    except Exception as e:
        logger.error(f"Failed to start AI Worker Prometheus server on port {port}: {e}")
