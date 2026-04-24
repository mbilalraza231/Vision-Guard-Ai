"""
VisionGuard AI - Process Supervisor

Utilities for managing background processes (ECS, cameras).
Provides clean lifecycle control without blocking.
"""

import asyncio
import multiprocessing
import os
import signal
import time
from enum import Enum
from typing import Optional, Callable, Any, Dict
from dataclasses import dataclass, field
from datetime import datetime

from ..utils.logging import get_logger

logger = get_logger(__name__)


class ProcessState(str, Enum):
    """Process lifecycle states."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"
    CRASHED = "crashed"


@dataclass
class ProcessInfo:
    """Information about a supervised process."""
    name: str
    state: ProcessState = ProcessState.STOPPED
    pid: Optional[int] = None
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    last_error: Optional[str] = None
    restart_count: int = 0
    
    @property
    def uptime_seconds(self) -> float:
        """Get process uptime in seconds."""
        if self.state == ProcessState.RUNNING and self.started_at:
            return (datetime.now() - self.started_at).total_seconds()
        return 0.0
    
    @property
    def is_alive(self) -> bool:
        """Check if process is running."""
        return self.state == ProcessState.RUNNING
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "name": self.name,
            "state": self.state.value,
            "pid": self.pid,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "last_error": self.last_error,
            "restart_count": self.restart_count,
            "is_alive": self.is_alive,
        }


class ProcessSupervisor:
    """
    Generic process supervisor for background tasks.
    
    Manages lifecycle of multiprocessing.Process instances.
    Does NOT auto-restart - that's the caller's decision.
    """
    
    def __init__(self, name: str):
        """
        Initialize supervisor.
        
        Args:
            name: Human-readable name for the process
        """
        self.name = name
        self.process: Optional[multiprocessing.Process] = None
        self.info = ProcessInfo(name=name)
        self._lock = asyncio.Lock()
        self.logger = get_logger(f"{__name__}.{name}")
    
    async def start(
        self,
        target: Callable,
        args: tuple = (),
        kwargs: dict = None,
        timeout: float = 10.0
    ) -> bool:
        """
        Start the supervised process.
        
        Args:
            target: Function to run in subprocess
            args: Positional arguments for target
            kwargs: Keyword arguments for target
            timeout: Max seconds to wait for startup
            
        Returns:
            True if process started successfully
        """
        async with self._lock:
            if self.info.state == ProcessState.RUNNING:
                self.logger.warning("Process already running")
                return True
            
            self.info.state = ProcessState.STARTING
            self.info.last_error = None
            
            try:
                # Create new process
                self.process = multiprocessing.Process(
                    target=target,
                    args=args,
                    kwargs=kwargs or {},
                    name=self.name,
                    daemon=False  # Allow cleanup
                )
                
                # Start process
                self.process.start()
                
                # Wait for process to be alive (with timeout)
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if self.process.is_alive():
                        self.info.state = ProcessState.RUNNING
                        self.info.pid = self.process.pid
                        self.info.started_at = datetime.now()
                        self.info.stopped_at = None
                        
                        self.logger.info(
                            f"Process started successfully",
                            extra={"pid": self.process.pid}
                        )
                        return True
                    
                    # Check if process died during startup
                    if self.process.exitcode is not None:
                        raise RuntimeError(
                            f"Process died during startup with code {self.process.exitcode}"
                        )
                    
                    await asyncio.sleep(0.1)
                
                # Timeout
                raise TimeoutError(f"Process did not start within {timeout}s")
                
            except Exception as e:
                self.info.state = ProcessState.FAILED
                self.info.last_error = str(e)
                self.logger.error(f"Failed to start process: {e}")
                
                # Cleanup if process was created
                if self.process and self.process.is_alive():
                    self.process.terminate()
                    self.process.join(timeout=1)
                
                return False
    
    async def stop(self, timeout: float = 5.0) -> bool:
        """
        Stop the supervised process gracefully.
        
        Args:
            timeout: Max seconds to wait for graceful shutdown
            
        Returns:
            True if process stopped successfully
        """
        async with self._lock:
            if self.info.state not in (ProcessState.RUNNING, ProcessState.STARTING):
                self.logger.info("Process not running, nothing to stop")
                return True
            
            self.info.state = ProcessState.STOPPING
            
            if not self.process:
                self.info.state = ProcessState.STOPPED
                return True
            
            try:
                # Try graceful termination first (SIGTERM)
                self.process.terminate()
                
                # Wait for graceful shutdown
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if not self.process.is_alive():
                        self.info.state = ProcessState.STOPPED
                        self.info.stopped_at = datetime.now()
                        self.info.pid = None
                        
                        self.logger.info("Process stopped gracefully")
                        return True
                    
                    await asyncio.sleep(0.1)
                
                # Force kill if still alive (SIGKILL)
                self.logger.warning("Graceful shutdown timeout, forcing kill")
                self.process.kill()
                self.process.join(timeout=1)
                
                self.info.state = ProcessState.STOPPED
                self.info.stopped_at = datetime.now()
                self.info.pid = None
                
                return True
                
            except Exception as e:
                self.info.state = ProcessState.FAILED
                self.info.last_error = str(e)
                self.logger.error(f"Failed to stop process: {e}")
                return False
    
    def check_health(self) -> bool:
        """
        Check if process is still healthy.
        
        Updates state if process has crashed.
        
        Returns:
            True if process is running
        """
        if self.info.state != ProcessState.RUNNING:
            return False
        
        if not self.process or not self.process.is_alive():
            # Process crashed
            self.info.state = ProcessState.CRASHED
            self.info.stopped_at = datetime.now()
            self.info.pid = None
            
            if self.process:
                self.info.last_error = f"Process exited with code {self.process.exitcode}"
            
            self.logger.error(
                "Process crashed",
                extra={"exit_code": self.process.exitcode if self.process else None}
            )
            return False
        
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """Get current process status."""
        self.check_health()  # Update state if crashed
        return self.info.to_dict()
