"""
VisionGuard AI - AI Worker Entry Point

Standalone entry point for Docker container.
"""

import sys
import os
import signal
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_worker import start_worker, stop_worker, WorkerConfig

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='[%(asctime)s] [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

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
    
    config = WorkerConfig(
        model_type=model_type,
        redis_input_queue=input_queue,
        onnx_model_path=model_path,
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", "6379")),
        confidence_threshold=float(os.getenv("WORKER_CONFIDENCE_THRESHOLD", "0.40")),
        iou_threshold=float(os.getenv("WORKER_IOU_THRESHOLD", "0.45")),
        agnostic_nms=os.getenv("WORKER_AGNOSTIC_NMS", "false").lower() == "true",
        allowed_class_ids=os.getenv("WORKER_ALLOWED_CLASS_IDS", ""),
        input_width=int(os.getenv("WORKER_INPUT_WIDTH", "640")),
        input_height=int(os.getenv("WORKER_INPUT_HEIGHT", "640")),
    )
    
    worker = None

    def shutdown(signum, frame):
        logger.info("Received shutdown signal, stopping worker...")
        if worker:
            stop_worker(worker)
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
