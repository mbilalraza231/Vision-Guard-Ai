"""
VisionGuard AI - Structured Logging

Provides consistent JSON and text logging for the backend.
"""

import logging
import sys
import json
from datetime import datetime
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """Human-readable text formatter."""
    
    def __init__(self):
        super().__init__(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )


def setup_logging(level: str = "INFO", format_type: str = "json") -> None:
    """
    Configure application logging.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        format_type: 'json' or 'text'
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    
    # Set formatter based on type
    if format_type.lower() == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(TextFormatter())
    
    root_logger.addHandler(console_handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger instance."""
    return logging.getLogger(name)
