"""
VisionGuard AI - RTSP Handler

Manages RTSP connections with automatic reconnection.
"""

import cv2
import logging
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
                    self.logger.info(
                        f"Successfully connected to RTSP stream",
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
        if self.capture:
            self.capture.release()
            self.capture = None
        
        self.is_connected = False
        
        self.logger.info(
            f"Disconnected from RTSP stream",
            extra={"camera_id": self.camera_id}
        )
    
    def read_frame(self) -> Optional[cv2.Mat]:
        """
        Read a frame from the RTSP stream.
        
        Returns:
            Frame as NumPy array, or None if read failed
        """
        if not self.is_connected or not self.capture:
            self.logger.warning(
                f"Cannot read frame: not connected",
                extra={"camera_id": self.camera_id}
            )
            return None
        
        try:
            ret, frame = self.capture.read()
            
            if ret and frame is not None:
                self.frame_count += 1
                return frame
            else:
                self.logger.warning(
                    f"Failed to read frame from stream",
                    extra={"camera_id": self.camera_id, "frame_count": self.frame_count}
                )
                self.is_connected = False
                return None
                
        except Exception as e:
            self.logger.error(
                f"Error reading frame: {e}",
                extra={"camera_id": self.camera_id, "error": str(e)}
            )
            self.is_connected = False
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
