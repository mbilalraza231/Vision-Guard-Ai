"""
VisionGuard AI - Retry Logic with Exponential Backoff

Reusable retry decorator and utilities.
"""

import time
import logging
from typing import Callable, TypeVar, Optional, Type, Tuple
from functools import wraps


T = TypeVar('T')


class RetryExhausted(Exception):
    """Raised when all retry attempts are exhausted."""
    pass


def exponential_backoff(
    max_retries: int = 5,
    initial_backoff: float = 1.0,
    max_backoff: float = 60.0,
    backoff_multiplier: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    logger: Optional[logging.Logger] = None
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_backoff: Initial backoff duration in seconds
        max_backoff: Maximum backoff duration in seconds
        backoff_multiplier: Multiplier for exponential backoff
        exceptions: Tuple of exception types to catch and retry
        logger: Logger instance for logging retry attempts
    
    Example:
        @exponential_backoff(max_retries=3, initial_backoff=1.0)
        def connect_to_camera(url):
            # Connection logic
            pass
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            backoff = initial_backoff
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        if logger:
                            logger.error(
                                f"Retry exhausted for {func.__name__} after {max_retries} attempts",
                                extra={
                                    "function": func.__name__,
                                    "attempts": max_retries + 1,
                                    "error": str(e)
                                }
                            )
                        raise RetryExhausted(
                            f"Failed after {max_retries} retries: {e}"
                        ) from e
                    
                    if logger:
                        logger.warning(
                            f"Retry attempt {attempt + 1}/{max_retries} for {func.__name__}",
                            extra={
                                "function": func.__name__,
                                "attempt": attempt + 1,
                                "max_retries": max_retries,
                                "backoff_seconds": backoff,
                                "error": str(e)
                            }
                        )
                    
                    time.sleep(backoff)
                    backoff = min(backoff * backoff_multiplier, max_backoff)
            
            # Should never reach here
            raise last_exception
        
        return wrapper
    return decorator


class RetryContext:
    """
    Context manager for retry logic with exponential backoff.
    
    Useful for non-decorator scenarios.
    
    Example:
        retry = RetryContext(max_retries=3)
        for attempt in retry:
            try:
                # Operation
                break
            except Exception as e:
                retry.handle_exception(e)
    """
    
    def __init__(
        self,
        max_retries: int = 5,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
        backoff_multiplier: float = 2.0,
        logger: Optional[logging.Logger] = None
    ):
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier
        self.logger = logger
        
        self.attempt = 0
        self.backoff = initial_backoff
        self.last_exception: Optional[Exception] = None
    
    def __iter__(self):
        """Iterator for retry attempts."""
        self.attempt = 0
        self.backoff = self.initial_backoff
        return self
    
    def __next__(self):
        """Get next retry attempt."""
        if self.attempt > self.max_retries:
            raise StopIteration
        
        current_attempt = self.attempt
        self.attempt += 1
        return current_attempt
    
    def handle_exception(self, exception: Exception) -> None:
        """
        Handle exception during retry attempt.
        
        Args:
            exception: Exception that occurred
            
        Raises:
            RetryExhausted: If max retries exceeded
        """
        self.last_exception = exception
        
        if self.attempt > self.max_retries:
            if self.logger:
                self.logger.error(
                    f"Retry exhausted after {self.max_retries} attempts",
                    extra={
                        "attempts": self.max_retries + 1,
                        "error": str(exception)
                    }
                )
            raise RetryExhausted(
                f"Failed after {self.max_retries} retries: {exception}"
            ) from exception
        
        if self.logger:
            self.logger.warning(
                f"Retry attempt {self.attempt}/{self.max_retries}",
                extra={
                    "attempt": self.attempt,
                    "max_retries": self.max_retries,
                    "backoff_seconds": self.backoff,
                    "error": str(exception)
                }
            )
        
        time.sleep(self.backoff)
        self.backoff = min(self.backoff * self.backoff_multiplier, self.max_backoff)
