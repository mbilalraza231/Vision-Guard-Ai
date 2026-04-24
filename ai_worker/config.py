"""
VisionGuard AI - AI Worker Configuration

Type-safe configuration for single-model AI workers.
Config-driven worker specialization (one worker = one model = one queue).
"""

from typing import Optional
from pydantic import BaseModel, Field, validator
import os


class WorkerConfig(BaseModel):
    """
    Configuration for a single-model AI worker.
    
    Each worker instance is specialized for ONE model type and ONE Redis queue.
    """
    
    # Worker specialization
    model_type: str = Field(..., description="Model type: 'weapon', 'fire', 'fall'")
    redis_input_queue: str = Field(
        ...,
        description="Redis queue to consume from: 'vg:critical', 'vg:high', 'vg:medium'"
    )
    onnx_model_path: str = Field(..., description="Path to ONNX model file")
    confidence_threshold: float = Field(
        default=0.40,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold for results (0-1 normalized scale)"
    )
    iou_threshold: float = Field(
        default=0.45,
        ge=0.0,
        le=1.0,
        description="IoU NMS threshold (lower = merge overlapping smoke/flame boxes)"
    )
    agnostic_nms: bool = Field(
        default=False,
        description="Class-agnostic NMS — treats all classes as one (useful for fire+smoke)"
    )
    allowed_class_ids: str = Field(
        default="",
        description="Comma-separated list of allowed class IDs, e.g. '0' for fire. If empty, allows all."
    )
    
    # Redis configuration
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, ge=1, le=65535, description="Redis port")
    redis_db: int = Field(default=0, ge=0, description="Redis database number")
    redis_password: Optional[str] = Field(default=None, description="Redis password (optional)")
    redis_timeout: int = Field(default=1, ge=1, description="Redis blocking timeout in seconds")
    
    # ONNX Runtime configuration (CPU-only)
    intra_op_num_threads: int = Field(
        default=4,
        ge=1,
        description="ONNX intra-op threads (must not exceed CPU cores / worker_count)"
    )
    inter_op_num_threads: int = Field(
        default=2,
        ge=1,
        description="ONNX inter-op threads"
    )
    
    # Model input size
    input_width: int = Field(default=640, ge=32, description="Model input width")
    input_height: int = Field(default=640, ge=32, description="Model input height")
    
    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format (json/text)")
    
    # Shared memory (reuses camera module's implementation)
    shared_memory_max_size_mb: int = Field(
        default=10,
        ge=1,
        description="Max frame size in shared memory (MB)"
    )
    
    @validator('model_type')
    def validate_model_type(cls, v):
        valid_types = ['weapon', 'fire', 'fall']
        if v not in valid_types:
            raise ValueError(f'model_type must be one of {valid_types}')
        return v
    
    @validator('redis_input_queue')
    def validate_redis_queue(cls, v):
        valid_queues = ['vg:critical', 'vg:high', 'vg:medium']
        if v not in valid_queues:
            raise ValueError(f'redis_input_queue must be one of {valid_queues}')
        return v
    
    @validator('onnx_model_path')
    def validate_model_path(cls, v):
        # Accept .onnx file OR a directory (OpenVINO model format: xml + bin)
        if os.path.isdir(v):
            xml_files = [f for f in os.listdir(v) if f.endswith('.xml')]
            if not xml_files:
                raise ValueError(
                    f'OpenVINO model directory {v} contains no .xml file'
                )
            return v
        if not v.endswith('.onnx'):
            raise ValueError(
                'onnx_model_path must be a .onnx file or an OpenVINO model directory'
            )
        if not os.path.exists(v):
            raise ValueError(f'ONNX model file not found: {v}')
        return v
    
    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'log_level must be one of {valid_levels}')
        return v.upper()
    
    @validator('log_format')
    def validate_log_format(cls, v):
        if v not in ['json', 'text']:
            raise ValueError('log_format must be "json" or "text"')
        return v
    
    class Config:
        """Pydantic configuration."""
        validate_assignment = True
        extra = 'forbid'


class ResultMetadata(BaseModel):
    """
    Inference result metadata structure.
    
    This is published to Redis stream for Event Classification Service.
    CRITICAL: Includes shared_memory_key for frame cleanup by Event Classification.
    """
    
    camera_id: str
    frame_id: str
    shared_memory_key: str  # REQUIRED for Event Classification cleanup
    model: str
    confidence: float
    bbox: Optional[list] = None  # [x1, y1, x2, y2] for object detection
    timestamp: float
    inference_latency_ms: float  # REQUIRED for capacity planning
    detection_image: Optional[str] = None  # Path to annotated frame image
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Redis serialization."""
        result = {
            "camera_id": self.camera_id,
            "frame_id": self.frame_id,
            "shared_memory_key": self.shared_memory_key,
            "model": self.model,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "inference_latency_ms": self.inference_latency_ms
        }
        
        if self.bbox is not None:
            # Redis XADD requires scalar types - serialize list to JSON string
            import json
            result["bbox"] = json.dumps(self.bbox)
        
        if self.detection_image:
            result["detection_image"] = self.detection_image
        
        return result

