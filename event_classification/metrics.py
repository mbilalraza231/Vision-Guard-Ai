"""
Event Classification and DB Metrics
Port: 8005
 """
import logging
from prometheus_client import start_http_server, Counter, Histogram

logger = logging.getLogger(__name__)

# 1. REDIS READS COUNTER
REDIS_READS_TOTAL = Counter(
    'vg_ecs_redis_reads_total',
    'Total raw AI frame events read from Redis streams',
    ['status']
)

# 2. EVENT CLASSIFICATION DECISION COUNTER
EVENTS_PROCESSING_TOTAL = Counter(
    'vg_ecs_events_processed_total',
    'Total raw AI detection events evaluated by decision',
    ['event_type', 'decision']
)

# 3. POSTGRES DB WRITES COUNTER
DB_WRITES_TOTAL = Counter(
    'vg_ecs_db_writes_total',
    'Total PostgreSQL event writes executed by ECS',
    ['status']
)

# 4. ECS LATENCY HISTOGRAM
ECS_PROCESSING_LATENCY = Histogram(
    'vg_ecs_processing_duration_seconds',
    'ECS event classification and noise-filtering latency in seconds',
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5)
)

# 5. END-TO-END PIPELINE LATENCY (Frame Capture -> ECS Emission)
END_TO_END_LATENCY = Histogram(
    'vg_pipeline_end_to_end_duration_seconds',
    'Complete latency from initial camera frame capture to ECS event classification',
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

def start_metrics_server(port: int = 8005):
    try:
        start_http_server(port)
        logger.info(f"Prometheus metrics server started for ECS on port {port}")
    except Exception as e:
        logger.error(f"Failed to start ECS Prometheus server on port {port}: {e}")
