"""
VisionGuard AI - Structured Logging

Process-safe logging with required correlation context.
All logs include: camera_id, process_id, module_name
"""

import logging
import json
import os
from typing import Optional, Dict, Any
from logging.handlers import QueueHandler, QueueListener
from multiprocessing import Queue, current_process


class ContextFilter(logging.Filter):
    """
    Add required context fields to all log records.
    
    Required fields:
    - camera_id: Unique camera identifier
    - process_id: OS process ID
    - module_name: Module name
    """
    
    def __init__(self, camera_id: Optional[str] = None):
        super().__init__()
        self.camera_id = camera_id
        self.process_id = os.getpid()
        self.process_name = current_process().name
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add context fields to log record."""
        # Add required fields
        record.camera_id = getattr(record, 'camera_id', self.camera_id or 'unknown')
        record.process_id = getattr(record, 'process_id', self.process_id)
        record.process_name = getattr(record, 'process_name', self.process_name)
        record.module_name = record.name
        
        return True


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.
    
    Output format:
    {
        "timestamp": "2026-01-20T19:42:53+05:00",
        "level": "INFO",
        "camera_id": "cam_001",
        "process_id": 12345,
        "process_name": "CameraProcess-cam_001",
        "module_name": "camera_capture.core.camera_process",
        "message": "Frame captured",
        "extra": {...}
    }
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "camera_id": getattr(record, 'camera_id', 'unknown'),
            "process_id": getattr(record, 'process_id', os.getpid()),
            "process_name": getattr(record, 'process_name', current_process().name),
            "module_name": record.name,
            "message": record.getMessage(),
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields from 'extra' parameter
        if hasattr(record, 'extra'):
            log_data["extra"] = record.extra
        
        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """
    Human-readable text formatter with required context.
    
    Format: [timestamp] [level] [camera_id] [process_id] [module] message
    """
    
    def __init__(self):
        super().__init__(
            fmt='[%(asctime)s] [%(levelname)s] [%(camera_id)s] [%(process_id)s] [%(module_name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )


def setup_logging(
    level: str = "INFO",
    format_type: str = "json",
    camera_id: Optional[str] = None,
    log_queue: Optional[Queue] = None
) -> logging.Logger:
    """
    Setup logging for camera capture module.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Log format (json, text)
        camera_id: Camera ID for context (optional)
        log_queue: Multiprocessing queue for centralized logging (optional)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("camera_capture")
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Choose formatter
    if format_type == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()
    
    # Add context filter
    context_filter = ContextFilter(camera_id=camera_id)
    logger.addFilter(context_filter)
    
    # Setup handler
    if log_queue:
        # Use queue handler for multi-process logging
        handler = QueueHandler(log_queue)
    else:
        # Use stream handler for single-process or testing
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
    
    logger.addHandler(handler)
    logger.propagate = False
    
    return logger


def setup_queue_listener(log_queue: Queue, level: str = "INFO", format_type: str = "json") -> QueueListener:
    """
    Setup centralized log listener for multi-process logging.
    
    This should be called in the main process to collect logs from all camera processes.
    
    Args:
        log_queue: Multiprocessing queue for log records
        level: Log level
        format_type: Log format (json, text)
    
    Returns:
        QueueListener instance (must be started with .start())
    """
    # Choose formatter
    if format_type == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()
    
    # Create handler
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.setLevel(getattr(logging, level.upper()))
    
    # Create listener
    listener = QueueListener(log_queue, handler, respect_handler_level=True)
    
    return listener


def get_logger(name: str, camera_id: Optional[str] = None) -> logging.Logger:
    """
    Get logger instance with camera context.
    
    Args:
        name: Logger name (usually __name__)
        camera_id: Camera ID for context
    
    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)
    
    # Add context filter if camera_id provided
    if camera_id:
        context_filter = ContextFilter(camera_id=camera_id)
        logger.addFilter(context_filter)
    
    return logger
