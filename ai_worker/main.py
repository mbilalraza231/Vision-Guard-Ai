"""
VisionGuard AI - AI Worker Entry Point

Standalone entry point for Docker container.
"""

import sys
import os
import signal
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import json
import psutil
import threading
import socket
import redis

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_worker import start_worker, stop_worker, WorkerConfig
from ai_worker.settings_runtime import load_worker_runtime_settings

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
                # Use a small interval to get a real-time sample without blocking the loop too much
                # Total usage = self + all children
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
                # 15 second TTL is safe for a 5 second heartbeat
                self.redis.setex(self.key, 15, json.dumps(metrics))
            except Exception:
                pass
            time.sleep(5)

    def stop(self):
        if self._thread:
            self._stop.set()
            self._thread.join(timeout=1.0)

MODEL_QUEUE_MAP = {
    "weapon": "vg:critical",
    "fire": "vg:high",
    "fall": "vg:medium"
}


def find_model_path(model_type: str) -> str:
    """Find model path — checks WORKER_MODEL_PATH env first, then filename convention."""
    # Priority 1: Explicit env var (used by fire worker for OpenVINO directory)
    explicit_path = os.getenv("WORKER_MODEL_PATH", "").strip()
    if explicit_path and (os.path.exists(explicit_path) or os.path.isdir(explicit_path)):
        return explicit_path

    # Priority 2: Filename convention (.onnx)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    model_name = f"{model_type}_detection.onnx"
    
    search_paths = [
        os.path.join(project_root, "models", model_name),
        os.path.join("/app/models", model_name),
        os.path.join(project_root, model_name),
    ]
    
    for path in search_paths:
        if os.path.exists(path):
            return path
    
    logger.error(f"Model not found: {model_name}")
    logger.error(f"Searched: {search_paths}")
    return search_paths[0]


def main():
    """Main entry point for AI worker."""
    model_type = os.getenv("WORKER_MODEL_TYPE", "weapon")
    
    logger.info(f"Starting AI Worker ({model_type})...")
    
    model_path = find_model_path(model_type)
    input_queue = MODEL_QUEUE_MAP.get(model_type, "vg:critical")
    
    logger.info(f"Model path: {model_path}")
    logger.info(f"Input queue: {input_queue}")
    
    runtime = load_worker_runtime_settings(model_type)
    fire_model = runtime.get("fire_model", {})
    config = WorkerConfig(
        model_type=model_type,
        redis_input_queue=input_queue,
        onnx_model_path=model_path,
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", "6379")),
        confidence_threshold=runtime["confidence_threshold"],
        iou_threshold=float(fire_model.get("iouThreshold", os.getenv("WORKER_IOU_THRESHOLD", "0.45"))),
        agnostic_nms=bool(fire_model.get("agnosticNms", os.getenv("WORKER_AGNOSTIC_NMS", "false").lower() == "true")),
        allowed_class_ids=str(fire_model.get("allowedClassIds", os.getenv("WORKER_ALLOWED_CLASS_IDS", ""))),
        input_width=int(fire_model.get("inputWidth", os.getenv("WORKER_INPUT_WIDTH", "640"))),
        input_height=int(fire_model.get("inputHeight", os.getenv("WORKER_INPUT_HEIGHT", "640"))),
    )
    
    worker = None
    reporter = None
    
    # Start metrics reporter
    try:
        r_host = os.getenv("REDIS_HOST", "localhost")
        r_port = int(os.getenv("REDIS_PORT", "6379"))
        r_client = redis.Redis(host=r_host, port=r_port)
        reporter = MetricsReporter(r_client, f"worker-{model_type}")
        reporter.start()
        logger.info(f"Metrics heartbeat started for worker-{model_type}")
    except Exception as e:
        logger.warning(f"Failed to start metrics reporter: {e}")

    def shutdown(signum, frame):
        logger.info("Received shutdown signal, stopping worker...")
        if worker:
            stop_worker(worker)
        if reporter:
            reporter.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    
    try:
        worker = start_worker(config)
        
        logger.info(f"AI Worker ({config.model_type}) running. Press Ctrl+C to stop.")
        signal.pause()
        
    except Exception as e:
        logger.error(f"AI Worker failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
