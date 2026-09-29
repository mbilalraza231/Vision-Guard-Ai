"""
Camera Stream Prometheus Metrics

Business metrics (frames, streams, latency) are bridged from the child camera
processes through Redis and updated by a background thread in the MAIN process.

Because the camera service forks one OS process per camera, the standard
`process_*` metrics exported by prometheus_client only describe the PARENT and
therefore under-report CPU/RAM by a large margin. The container-wide gauges below
sum /proc data for every process inside the container so Grafana shows the truth.

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

# 5. CONTAINER-WIDE RESOURCE GAUGES (parent + every forked camera process)
CONTAINER_CPU_SECONDS = Gauge(
    'vg_container_cpu_seconds_total',
    'Cumulative CPU seconds used by ALL processes inside this container'
)
CONTAINER_MEMORY_BYTES = Gauge(
    'vg_container_memory_bytes',
    'Proportional set size (PSS) in bytes across ALL processes inside this container'
)
CONTAINER_PROCESS_COUNT = Gauge(
    'vg_container_process_count',
    'Number of processes running inside this container'
)

_TICK_HZ = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
_PAGE_BYTES = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


def _process_memory_bytes(pid: str) -> int:
    """Proportional memory for one process, in bytes.

    PSS (proportional set size) is used instead of RSS because the camera parent
    and its forked children share the same interpreter, OpenCV libraries and
    shared-frame buffers — summing RSS would count those pages once per process
    and overshoot the real usage. Falls back to RSS if smaps_rollup is missing.
    """
    try:
        with open(f"/proc/{pid}/smaps_rollup", "rb") as fh:
            for line in fh:
                if line.startswith(b"Pss:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    try:
        with open(f"/proc/{pid}/statm", "rb") as fh:
            return int(fh.read().split()[1]) * _PAGE_BYTES
    except (OSError, IndexError, ValueError):
        return 0


def sample_container_resources():
    """Sum CPU time and memory across every process visible in this container's /proc.

    The camera service forks one process per camera, so prometheus_client's own
    process_* metrics only cover the supervisor. Returns
    (cpu_seconds, mem_bytes, process_count); zeros if /proc is unavailable.
    """
    cpu_seconds = 0.0
    mem_bytes = 0
    count = 0
    try:
        pids = [name for name in os.listdir("/proc") if name.isdigit()]
    except OSError:
        return 0.0, 0, 0

    for pid in pids:
        try:
            with open(f"/proc/{pid}/stat", "rb") as fh:
                raw = fh.read().decode("utf-8", "ignore")
            # comm may contain spaces/parentheses — take everything after the last ')'
            fields = raw[raw.rfind(")") + 1:].split()
            utime = int(fields[11])   # field 14 in the full stat line
            stime = int(fields[12])   # field 15
            cpu_seconds += (utime + stime) / _TICK_HZ

            mem_bytes += _process_memory_bytes(pid)
            count += 1
        except (OSError, IndexError, ValueError):
            # Process vanished between listing and reading — normal for short-lived children
            continue

    return cpu_seconds, mem_bytes, count


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
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="prom-bridge")
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
                # Container-wide CPU/RAM first: independent of Redis, so it keeps
                # reporting even if the broker is briefly unreachable.
                cpu_seconds, rss_bytes, proc_count = sample_container_resources()
                if proc_count:
                    CONTAINER_CPU_SECONDS.set(cpu_seconds)
                    CONTAINER_MEMORY_BYTES.set(rss_bytes)
                    CONTAINER_PROCESS_COUNT.set(proc_count)
            except Exception as e:
                logger.debug(f"Container resource sampling error: {e}")

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
                            FRAMES_TOTAL.labels(
                                camera_id=cam_id, status="ingested").inc(diff)
                            LAST_FRAME_TIMESTAMP.labels(
                                camera_id=cam_id).set_to_current_time()
                            self._last_frames[cam_id] = current
                        elif current < last:
                            # Child restarted and reset its counter — rebase on the new value
                            FRAMES_TOTAL.labels(
                                camera_id=cam_id, status="ingested").inc(current)
                            LAST_FRAME_TIMESTAMP.labels(
                                camera_id=cam_id).set_to_current_time()
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
