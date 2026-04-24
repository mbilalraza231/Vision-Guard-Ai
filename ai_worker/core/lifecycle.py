"""
VisionGuard AI - Worker Lifecycle Hooks

Clean startup/shutdown hooks for backend control.
"""

from typing import Dict
import logging
from ..config import WorkerConfig
from .worker import AIWorker

logger = logging.getLogger(__name__)


def start_worker(config: WorkerConfig) -> AIWorker:
    """
    Start AI worker process.
    
    This is the main entry point for backend to start a worker.
    
    Args:
        config: Worker configuration (model type, queue, ONNX path, etc.)
        
    Returns:
        AIWorker instance for controlling the worker
        
    Example:
        from ai_worker import start_worker, WorkerConfig
        
        config = WorkerConfig(
            model_type="weapon",
            redis_input_queue="vg:critical",
            onnx_model_path="/models/weapon_detector.onnx",
            confidence_threshold=0.85
        )
        worker = start_worker(config)
    """
    worker = AIWorker(config)
    worker.start()
    return worker


def stop_worker(worker: AIWorker, timeout: float = 10.0) -> None:
    """
    Stop AI worker process gracefully.
    
    Args:
        worker: AIWorker instance returned by start_worker()
        timeout: Maximum time to wait for worker to stop
        
    Example:
        stop_worker(worker)
    """
    worker.stop(timeout=timeout)


def get_worker_status(worker: AIWorker) -> Dict[str, any]:
    """
    Get worker status.
    
    Args:
        worker: AIWorker instance
        
    Returns:
        Dictionary with status info:
        {
            "is_alive": bool,
            "pid": int | None,
            "model_type": str
        }
        
    Example:
        status = get_worker_status(worker)
        if not status["is_alive"]:
            logger.warning("Worker is dead, restarting...")
    """
    return {
        "is_alive": worker.is_alive(),
        "pid": worker.process.pid if worker.process else None,
        "model_type": worker.config.model_type,
        "queue": worker.config.redis_input_queue
    }
