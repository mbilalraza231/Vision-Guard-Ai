"""
VisionGuard AI - Frame State Models

Frame state representation for ECS frame buffer.
"""

from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class AIResult:
    """
    AI inference result for a single model.
    
    This is extracted from Redis stream messages.
    """
    # Non-default fields first
    model_type: str  # "weapon", "fire", "fall"
    confidence: float
    timestamp: float
    ingest_timestamp: Optional[float] = None
    # Default fields last
    bbox: Optional[list] = None  # [x1, y1, x2, y2] if applicable
    
    def __repr__(self) -> str:
        return f"AIResult(model={self.model_type}, conf={self.confidence:.2f})"



@dataclass
class FrameState:
    """
    Frame state in ECS buffer.
    
    Holds partial AI results for a single frame.
    Single source of truth for frame correlation.
    """
    
    # Frame identification
    frame_id: str
    camera_id: str
    shared_memory_key: str
    
    # AI results by model (partial results allowed)
    weapon_result: Optional[AIResult] = None
    fire_result: Optional[AIResult] = None
    fall_result: Optional[AIResult] = None
    
    # Timing
    first_seen_ts: float = field(default_factory=time.time)
    last_update_ts: float = field(default_factory=time.time)
    
    # V2: Classification trigger tracking
    classification_attempted: bool = False
    classification_reason: Optional[str] = None  # weapon_immediate, window_elapsed, ttl_expiry, no_detection
    
    def add_result(self, result: AIResult) -> None:
        """
        Add AI result to frame state.
        
        Args:
            result: AI inference result
        """
        if result.model_type == "weapon":
            self.weapon_result = result
        elif result.model_type == "fire":
            self.fire_result = result
        elif result.model_type == "fall":
            self.fall_result = result
        
        self.last_update_ts = time.time()
    
    def is_expired(self, hard_ttl_seconds: float) -> bool:
        """
        Check if frame has exceeded hard TTL.
        
        Args:
            hard_ttl_seconds: Hard TTL in seconds
            
        Returns:
            True if expired
        """
        age_seconds = time.time() - self.first_seen_ts
        return age_seconds >= hard_ttl_seconds
    
    def get_age_ms(self) -> float:
        """
        Get frame age in milliseconds.
        
        Returns:
            Age in milliseconds
        """
        return (time.time() - self.first_seen_ts) * 1000
    
    def has_all_models(self) -> bool:
        """
        Check if all three models have reported.
        
        Returns:
            True if weapon, fire, and fall results are present
        """
        return (
            self.weapon_result is not None and
            self.fire_result is not None and
            self.fall_result is not None
        )
    
    def has_weapon(self) -> bool:
        """Check if weapon result is present."""
        return self.weapon_result is not None
    
    def has_fire(self) -> bool:
        """Check if fire result is present."""
        return self.fire_result is not None
    
    def has_fall(self) -> bool:
        """Check if fall result is present."""
        return self.fall_result is not None
    
    def __repr__(self) -> str:
        results = []
        if self.weapon_result:
            results.append(f"weapon:{self.weapon_result.confidence:.2f}")
        if self.fire_result:
            results.append(f"fire:{self.fire_result.confidence:.2f}")
        if self.fall_result:
            results.append(f"fall:{self.fall_result.confidence:.2f}")
        reason = f", reason={self.classification_reason}" if self.classification_reason else ""
        return f"FrameState({self.frame_id}, age={self.get_age_ms():.0f}ms, {', '.join(results)}{reason})"
