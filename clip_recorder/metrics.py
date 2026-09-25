"""
Clip Recorder Prometheus Metrics
Port: 8007
"""
import logging
from prometheus_client import start_http_server, Counter, Histogram, Gauge

logger = logging.getLogger(__name__)

# 1. CLIPS RECORDED COUNTER
CLIPS_RECORDED_TOTAL = Counter(
    'vg_clip_recordings_total',
    'Total video clips evaluated for incidents by status',
    ['camera_id', 'event_type', 'status']
)

# 2. CLOUDINARY UPLOADS COUNTER
CLOUDINARY_UPLOADS_TOTAL = Counter(
    'vg_clip_cloudinary_uploads_total',
    'Total video clip uploads to Cloudinary by status',
    ['status']
)

# 3. RECORDING DURATION HISTOGRAM
RECORDING_DURATION = Histogram(
    'vg_clip_recording_duration_seconds',
    'Duration of video clip recording in seconds',
    buckets=(1.0, 5.0, 10.0, 15.0, 30.0, 60.0)
)

# 4. CLOUDINARY UPLOAD LATENCY HISTOGRAM
UPLOAD_LATENCY = Histogram(
    'vg_clip_upload_duration_seconds',
    'Cloudinary video clip upload duration in seconds',
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
)

# 5. PENDING UPLOADS COUNT GAUGE
PENDING_CLIPS = Gauge(
    'vg_clip_pending_count',
    'Number of pending clip uploads in background buffer'
)

# 6. LAST UPLOAD TIMESTAMP GAUGE
LAST_UPLOAD_TIMESTAMP = Gauge(
    'vg_clip_last_upload_timestamp_seconds',
    'Unix timestamp of the last successful video clip upload'
)

def start_metrics_server(port: int = 8007):
    try:
        start_http_server(port)
        logger.info(f"Prometheus metrics server started for Clip Recorder on port {port}")
    except Exception as e:
        logger.error(f"Failed to start Clip Recorder Prometheus metrics server on port {port}: {e}")
