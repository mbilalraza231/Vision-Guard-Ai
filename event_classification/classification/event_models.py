"""
VisionGuard AI - Event Models

Event output models for ECS classification results.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Event:
    """
    Classified security event.
    
    Output of ECS deterministic classification.
    """
    
    # Event identification
    event_id: str  # Unique event ID (UUID)
    event_type: str  # "weapon_detected", "fire_detected", "fall_detected"
    severity: str  # "CRITICAL", "HIGH", "MEDIUM"
    
    # Source information
    camera_id: str
    frame_id: str
    timestamp: float
    
    # Detection details
    confidence: float
    model_type: str  # "weapon", "fire", "fall"
    
    # Optional fields (must come after non-default fields)
    bbox: Optional[list] = None  # [x1, y1, x2, y2] if applicable
    correlation_age_ms: float = 0.0  # How long frame was in buffer
    
    def to_dict(self) -> dict:
        """Convert to dictionary for output serialization."""
        result = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "camera_id": self.camera_id,
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "model_type": self.model_type,
            "correlation_age_ms": self.correlation_age_ms
        }
        
        if self.bbox is not None:
            result["bbox"] = self.bbox
        
        return result
    
    def __repr__(self) -> str:
        return f"Event({self.event_type}, {self.severity}, conf={self.confidence:.2f}, camera={self.camera_id})"
