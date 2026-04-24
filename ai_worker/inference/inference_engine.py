"""
VisionGuard AI - ONNX Inference Engine

Executes ONNX inference on CPU.
One frame per inference (no batching).
"""

import onnxruntime as ort
import numpy as np
import logging
import time


class InferenceEngine:
    """
    ONNX inference engine.
    
    Executes CPU-only inference with timing and error handling.
    """
    
    def __init__(self, session: ort.InferenceSession, input_name: str, output_names: list):
        """
        Initialize inference engine.
        
        Args:
            session: ONNX Runtime inference session
            input_name: Model input name
            output_names: Model output names
        """
        self.session = session
        self.input_name = input_name
        self.output_names = output_names
        self.logger = logging.getLogger(__name__)
        
        # Statistics
        self.inferences_run = 0
        self.total_inference_time_ms = 0.0
        self.inference_failures = 0
    
    def run(self, input_tensor: np.ndarray) -> np.ndarray:
        """
        Run ONNX inference.
        
        Args:
            input_tensor: Preprocessed input tensor (1, C, H, W)
            
        Returns:
            Model output (raw)
            
        Raises:
            Exception if inference fails
        """
        try:
            start_time = time.time()
            
            # Run inference
            outputs = self.session.run(
                self.output_names,
                {self.input_name: input_tensor}
            )
            
            inference_time_ms = (time.time() - start_time) * 1000
            
            # Update statistics
            self.inferences_run += 1
            self.total_inference_time_ms += inference_time_ms
            
            self.logger.debug(
                f"Inference completed",
                extra={
                    "inference_time_ms": round(inference_time_ms, 2),
                    "input_shape": input_tensor.shape,
                    "output_shape": outputs[0].shape if outputs else None
                }
            )
            
            # Return first output (most models have single output)
            return outputs[0]
            
        except Exception as e:
            self.inference_failures += 1
            
            self.logger.error(
                f"Inference failed: {e}",
                extra={"error": str(e), "input_shape": input_tensor.shape}
            )
            raise
    
    def get_stats(self) -> dict:
        """
        Get inference statistics.
        
        Returns:
            Dictionary with inference counts and timing
        """
        avg_inference_time_ms = (
            self.total_inference_time_ms / self.inferences_run
            if self.inferences_run > 0
            else 0.0
        )
        
        return {
            "inferences_run": self.inferences_run,
            "inference_failures": self.inference_failures,
            "avg_inference_time_ms": round(avg_inference_time_ms, 2),
            "total_inference_time_ms": round(self.total_inference_time_ms, 2)
        }
