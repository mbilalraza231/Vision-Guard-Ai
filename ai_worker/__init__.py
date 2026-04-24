"""
VisionGuard AI - AI Worker Module

Public API for backend integration.

This module provides CPU-only, single-model AI inference workers:
- Consumes from ONE Redis queue
- Runs ONE ONNX model
- Publishes results to Redis stream
- READ-ONLY shared memory access (no cleanup)

NO business logic, NO alerts, NO database, NO HTTP endpoints.
"""

# Public API exports
from .config import WorkerConfig, ResultMetadata

from .core.lifecycle import (
    start_worker,
    stop_worker,
    get_worker_status
)

from .core.worker import AIWorker

__version__ = "1.0.0"

__all__ = [
    # Configuration models
    "WorkerConfig",
    "ResultMetadata",
    
    # Lifecycle functions (main API)
    "start_worker",
    "stop_worker",
    "get_worker_status",
    
    # Worker class (for advanced usage)
    "AIWorker",
]
