"""
VisionGuard AI - OpenVINO Inference Engine

Wraps OpenVINO Runtime compiled model with the same interface as InferenceEngine,
so existing worker code needs no changes — just route based on model path type.

Requires: openvino>=2023.0
"""

import numpy as np
import logging
import time
from typing import Optional


class OpenVINOEngine:
    """
    OpenVINO inference engine (drop-in for InferenceEngine).

    Exposes `run(input_tensor) -> np.ndarray` matching the ONNX engine interface.
    Loads the model once at startup and keeps it resident in memory.
    """

    def __init__(self, model_dir: str, num_threads: Optional[int] = None):
        """
        Initialize OpenVINO engine.

        Args:
            model_dir: Path to OpenVINO model directory (containing *.xml + *.bin)
            num_threads: Number of inference threads (None = use OV default)
        """
        self.model_dir = model_dir
        self.logger = logging.getLogger(__name__)

        try:
            import openvino as ov

            # Find the .xml model file
            import os
            xml_files = [f for f in os.listdir(model_dir) if f.endswith(".xml")]
            if not xml_files:
                raise FileNotFoundError(f"No .xml model file found in {model_dir}")

            model_xml = os.path.join(model_dir, xml_files[0])
            self.logger.info(
                "Loading OpenVINO model",
                extra={"model_xml": model_xml}
            )

            # Configure thread count if specified
            config = {}
            if num_threads is not None:
                config["CPU_THREADS_NUM"] = str(num_threads)

            # Compile model for CPU
            core = ov.Core()
            model = core.read_model(model_xml)
            self._compiled = core.compile_model(model, "CPU", config)
            self._infer_request = self._compiled.create_infer_request()

            # Grab input/output metadata
            self.input_node = self._compiled.input(0)
            self.output_node = self._compiled.output(0)

            self.logger.info(
                "OpenVINO engine loaded successfully",
                extra={
                    "model_dir": model_dir,
                }
            )

        except ImportError:
            raise ImportError(
                "openvino package not installed. "
                "Run: pip install openvino>=2023.0"
            )
        except Exception as e:
            self.logger.error(
                f"Failed to load OpenVINO model: {e}",
                extra={"model_dir": model_dir, "error": str(e)}
            )
            raise

        # Statistics
        self.inferences_run = 0
        self.total_inference_time_ms = 0.0
        self.inference_failures = 0

    def run(self, input_tensor: np.ndarray) -> np.ndarray:
        """
        Run OpenVINO inference.

        Args:
            input_tensor: Preprocessed input (1, C, H, W) float32

        Returns:
            Raw model output numpy array — same shape as ONNX output
        """
        try:
            start_time = time.time()

            # Set input tensor and run inference
            self._infer_request.infer({0: input_tensor})

            # Read output using numpy
            output = self._infer_request.get_output_tensor(0).data.copy()

            # Wrap in batch dim if missing (OV sometimes strips it)
            if output.ndim == 2:
                output = output[np.newaxis, ...]

            inference_time_ms = (time.time() - start_time) * 1000
            self.inferences_run += 1
            self.total_inference_time_ms += inference_time_ms

            self.logger.debug(
                "OpenVINO inference completed",
                extra={
                    "inference_time_ms": round(inference_time_ms, 2),
                    "input_shape": str(input_tensor.shape),
                    "output_shape": str(output.shape),
                }
            )

            return output

        except Exception as e:
            self.inference_failures += 1
            self.logger.error(
                f"OpenVINO inference failed: {e}",
                extra={"error": str(e), "input_shape": str(input_tensor.shape)}
            )
            raise

    def get_stats(self) -> dict:
        """Get inference statistics (matches InferenceEngine interface)."""
        avg_ms = (
            self.total_inference_time_ms / self.inferences_run
            if self.inferences_run > 0
            else 0.0
        )
        return {
            "engine": "OpenVINO",
            "inferences_run": self.inferences_run,
            "inference_failures": self.inference_failures,
            "avg_inference_time_ms": round(avg_ms, 2),
            "total_inference_time_ms": round(self.total_inference_time_ms, 2),
        }

    # ── Compatibility properties to mirror InferenceEngine ──────────────────

    @property
    def session(self):
        """Compatibility stub — returns the compiled model."""
        return self._compiled

    @property
    def input_name(self) -> str:
        try:
            return self.input_node.get_any_name()
        except RuntimeError:
            return "input0"

    @property
    def output_names(self) -> list:
        try:
            return [self.output_node.get_any_name()]
        except RuntimeError:
            return ["output0"]
