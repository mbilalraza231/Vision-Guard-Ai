"""
VisionGuard AI - RTSP Handler

Manages RTSP connections with automatic reconnection.
"""

import cv2
import logging
import threading
import time
from typing import Optional
from ..utils.retry import RetryContext
from ..config import RetryConfig


class RTSPHandler:
    """
    RTSP connection handler with auto-reconnect.
    
    Wraps OpenCV VideoCapture with resilient connection management.
    """
    
    def __init__(
        self,
        rtsp_url: str,
        camera_id: str,
        retry_config: Optional[RetryConfig] = None
    ):
        """
        Initialize RTSP handler.
        
        Args:
            rtsp_url: RTSP stream URL
            camera_id: Unique camera identifier
            retry_config: Retry configuration (optional)
        """
        self.rtsp_url = rtsp_url
        self.camera_id = camera_id
        self.retry_config = retry_config or RetryConfig()
        self.logger = logging.getLogger(__name__)
        
        self.capture: Optional[cv2.VideoCapture] = None
        self.is_connected = False
        self.frame_count = 0
        self.reconnect_count = 0
        
        # Non-blocking capture
        self._latest_frame: Optional[cv2.Mat] = None
        self._latest_ts: float = 0.0
        self._capture_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
    
    def connect(self) -> bool:
        """
        Connect to RTSP stream with retry logic.
        
        Returns:
            True if connected successfully, False otherwise
        """
        retry = RetryContext(
            max_retries=self.retry_config.max_retries,
            initial_backoff=self.retry_config.initial_backoff_seconds,
            max_backoff=self.retry_config.max_backoff_seconds,
            backoff_multiplier=self.retry_config.backoff_multiplier,
            logger=self.logger
        )
        
        for attempt in retry:
            try:
                self.logger.info(
                    f"Connecting to RTSP stream (attempt {attempt + 1})",
                    extra={"rtsp_url": self.rtsp_url, "attempt": attempt + 1}
                )
                
                # Create VideoCapture
                self.capture = cv2.VideoCapture(self.rtsp_url)
                
                # Set buffer size to reduce latency
                self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                
                # Test connection by reading a frame
                ret, frame = self.capture.read()
                
                if ret and frame is not None:
                    self.is_connected = True
                    self._latest_frame = frame
                    self._latest_ts = time.time()
                    
                    # Start background capture thread to drain buffer
                    self._stop_event.clear()
                    self._capture_thread = threading.Thread(
                        target=self._capture_loop,
                        name=f"CaptureThread-{self.camera_id}",
                        daemon=True
                    )
                    self._capture_thread.start()
                    
                    self.logger.info(
                        f"Successfully connected to RTSP stream with background capture",
                        extra={
                            "rtsp_url": self.rtsp_url,
                            "frame_width": frame.shape[1],
                            "frame_height": frame.shape[0]
                        }
                    )
                    return True
                else:
                    raise ConnectionError("Failed to read initial frame")
                    
            except Exception as e:
                self.logger.warning(
                    f"Connection attempt failed: {e}",
                    extra={"rtsp_url": self.rtsp_url, "error": str(e)}
                )
                
                # Cleanup failed connection
                if self.capture:
                    self.capture.release()
                    self.capture = None
                
                retry.handle_exception(e)
        
        self.is_connected = False
        return False
    
    def reconnect(self) -> bool:
        """
        Reconnect to RTSP stream.
        
        Returns:
            True if reconnected successfully, False otherwise
        """
        self.logger.info(
            f"Attempting to reconnect",
            extra={"camera_id": self.camera_id, "reconnect_count": self.reconnect_count}
        )
        
        self.disconnect()
        self.reconnect_count += 1
        
        return self.connect()
    
    def disconnect(self) -> None:
        """Disconnect from RTSP stream."""
        self._stop_event.set()
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None
            
        if self.capture:
            self.capture.release()
            self.capture = None
        
        self.is_connected = False
        self._latest_frame = None
        
        self.logger.info(
            f"Disconnected from RTSP stream",
            extra={"camera_id": self.camera_id}
        )
    
    def _capture_loop(self) -> None:
        """Background thread to drain OpenCV buffer and keep latest frame."""
        while not self._stop_event.is_set() and self.capture and self.capture.isOpened():
            try:
                ret = self.capture.grab()
                if not ret:
                    self.is_connected = False
                    break
                
                # We only retrieve when someone calls read_frame? 
                # No, better retrieve here so we have the latest ready.
                # But to save CPU, we only retrieve if we actually need it?
                # Actually retrieve is fast enough.
                ret, frame = self.capture.retrieve()
                if ret and frame is not None:
                    with self._frame_lock:
                        self._latest_frame = frame
                        self._latest_ts = time.time()
                
                # Small sleep to prevent 100% CPU if stream is faster than logic
                # But keep it very small (1ms) to ensure buffer remains empty
                time.sleep(0.001)
                
            except Exception as e:
                self.logger.error(f"Error in background capture loop: {e}")
                self.is_connected = False
                break

    def read_frame(self) -> Optional[cv2.Mat]:
        """
        Get the LATEST frame captured by the background thread.
        
        Returns:
            Frame as NumPy array, or None if read failed
        """
        if not self.is_connected:
            return None
        
        with self._frame_lock:
            if self._latest_frame is not None:
                self.frame_count += 1
                return self._latest_frame.copy()
            return None
    
    def get_stats(self) -> dict:
        """
        Get connection statistics.
        
        Returns:
            Dictionary with is_connected, frame_count, reconnect_count
        """
        return {
            "is_connected": self.is_connected,
            "frame_count": self.frame_count,
            "reconnect_count": self.reconnect_count
        }
    
    def __del__(self):
        """Cleanup on deletion."""
        self.disconnect()
