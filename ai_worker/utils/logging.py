"""
VisionGuard AI - AI Worker Logging

Structured JSON logging with required context fields.
All logs include: model_type, camera_id, frame_id, process_id, module_name, inference_latency_ms
"""

import logging
import json
import os
from typing import Optional
from logging.handlers import QueueHandler
from multiprocessing import current_process


class WorkerContextFilter(logging.Filter):
    """
    Add required context fields to all log records.
    
    Required fields for AI workers:
    - model_type: Worker model type
    - camera_id: Camera identifier (from task)
    - frame_id: Frame identifier (from task)
    - process_id: OS process ID
    - module_name: Module name
    """
    
    def __init__(self, model_type: str):
        super().__init__()
        self.model_type = model_type
        self.process_id = os.getpid()
        self.process_name = current_process().name
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add context fields to log record."""
        # Add required fields
        record.model_type = getattr(record, 'model_type', self.model_type)
        record.camera_id = getattr(record, 'camera_id', 'unknown')
        record.frame_id = getattr(record, 'frame_id', 'unknown')
        record.process_id = getattr(record, 'process_id', self.process_id)
        record.process_name = getattr(record, 'process_name', self.process_name)
        record.module_name = record.name
        
        return True


class WorkerJSONFormatter(logging.Formatter):
    """
    JSON log formatter for AI workers.
    
    Output format:
    {
        "timestamp": "2026-01-21T16:41:39+05:00",
        "level": "INFO",
        "model_type": "weapon",
        "camera_id": "cam_001",
        "frame_id": "cam_001_1737385973123456",
        "process_id": 12345,
        "process_name": "AIWorker-weapon",
        "module_name": "ai_worker.core.worker",
        "message": "Inference completed",
        "inference_latency_ms": 45.2,
        "extra": {...}
    }
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "model_type": getattr(record, 'model_type', 'unknown'),
            "camera_id": getattr(record, 'camera_id', 'unknown'),
            "frame_id": getattr(record, 'frame_id', 'unknown'),
            "process_id": getattr(record, 'process_id', os.getpid()),
            "process_name": getattr(record, 'process_name', current_process().name),
            "module_name": record.name,
            "message": record.getMessage(),
        }
        
        # Add inference latency if present (MANDATORY for performance monitoring)
        if hasattr(record, 'inference_latency_ms'):
            log_data["inference_latency_ms"] = record.inference_latency_ms
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, 'extra'):
            log_data["extra"] = record.extra
        
        return json.dumps(log_data)


class WorkerTextFormatter(logging.Formatter):
    """
    Human-readable text formatter for AI workers.
    
    Format: [timestamp] [level] [model_type] [camera_id] [frame_id] [process_id] [module] message
    """
    
    def __init__(self):
        super().__init__(
            fmt='[%(asctime)s] [%(levelname)s] [%(model_type)s] [%(camera_id)s] [%(frame_id)s] [%(process_id)s] [%(module_name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )


def setup_worker_logging(
    model_type: str,
    level: str = "INFO",
    format_type: str = "json"
) -> logging.Logger:
    """
    Setup logging for AI worker.
    
    Args:
        model_type: Worker model type (weapon, fire, fall)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Log format (json, text)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("ai_worker")
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Choose formatter
    if format_type == "json":
        formatter = WorkerJSONFormatter()
    else:
        formatter = WorkerTextFormatter()
    
    # Add context filter
    context_filter = WorkerContextFilter(model_type=model_type)
    logger.addFilter(context_filter)
    
    # Setup handler
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    logger.propagate = False
    
    return logger


def get_worker_logger(name: str) -> logging.Logger:
    """
    Get logger instance for AI worker module.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)
