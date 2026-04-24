"""
VisionGuard AI - Event Classification Service

Public API for backend integration.

This module provides single-instance, CPU-only, deterministic event classification:
- Consumes AI results from Redis stream
- Correlates multi-model results
- Applies deterministic classification rules
- Dispatches outputs (alerts, DB, frontend)
- OWNS shared memory cleanup

NO horizontal scaling, NO replicas, NO AI inference, NO HTTP endpoints.
"""

# Public API exports
from .config import ECSConfig

from .core.lifecycle import (
    start_ecs,
    stop_ecs,
    get_ecs_status
)

from .core.service import ECSService

__version__ = "1.0.0"

__all__ = [
    # Configuration
    "ECSConfig",
    
    # Lifecycle functions (main API)
    "start_ecs",
    "stop_ecs",
    "get_ecs_status",
    
    # Service class (for advanced usage)
    "ECSService",
]
