"""
VisionGuard AI - Model Loader

Loads the correct inference engine based on model path type:
  - Directory path → OpenVINO engine (fire worker, INT8)
  - .onnx file     → ONNX Runtime engine (weapon / fall workers)

The worker loop uses only engine.run(tensor) and engine.get_stats().
Both engines expose the same interface — no changes needed in worker.py.
"""

import os
import logging
from typing import Union, Tuple


class ModelLoader:
    """
    Unified model loader: ONNX Runtime or OpenVINO Runtime.

    Automatically selects the backend from model path:
      - Directory  → OpenVINO (xml + bin, INT8 quantized)
      - .onnx file → ONNX Runtime CPU
    """

    def __init__(
        self,
        model_path: str,
        intra_op_num_threads: int = 4,
        inter_op_num_threads: int = 2
    ):
        """
        Load model from path.

        Args:
            model_path: Path to .onnx file OR OpenVINO model directory
            intra_op_num_threads: ONNX intra-op threads (ignored for OpenVINO)
            inter_op_num_threads: ONNX inter-op threads (ignored for OpenVINO)
        """
        self.model_path = model_path
        self.logger = logging.getLogger(__name__)
        self._engine = None
        self._backend = None

        if os.path.isdir(model_path):
            self._load_openvino(model_path)
        else:
            self._load_onnx(model_path, intra_op_num_threads, inter_op_num_threads)

    # ── Private loaders ──────────────────────────────────────────────────────

    def _load_openvino(self, model_dir: str) -> None:
        """Load OpenVINO model from directory (xml + bin)."""
        from ..inference.openvino_engine import OpenVINOEngine
        self._engine = OpenVINOEngine(model_dir=model_dir)
        self._backend = "openvino"

        # Expose attributes expected by AIWorker._initialize
        self.session = self._engine.session
        self.input_name = self._engine.input_name
        self.output_names = self._engine.output_names
        self.input_shape = (1, 3, None, None)  # dynamic shape placeholder

        self.logger.info(
            "Model loaded via OpenVINO Runtime",
            extra={"model_dir": model_dir, "backend": "OpenVINO"}
        )

    def _load_onnx(
        self,
        model_path: str,
        intra_op_num_threads: int,
        inter_op_num_threads: int
    ) -> None:
        """Load ONNX model via onnxruntime."""
        import onnxruntime as ort
        from ..inference.inference_engine import InferenceEngine

        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = intra_op_num_threads
        sess_options.inter_op_num_threads = inter_op_num_threads
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        requested_provider = os.getenv("ONNX_EXECUTION_PROVIDER", "CPUExecutionProvider")
        available_providers = ort.get_available_providers()

        if requested_provider in available_providers:
            providers = [requested_provider]
        elif "CPUExecutionProvider" in available_providers:
            providers = ["CPUExecutionProvider"]
        else:
            providers = available_providers[:1] if available_providers else []

        if providers and providers[0] != requested_provider:
            self.logger.warning(
                "Requested execution provider not available, falling back",
                extra={
                    "requested": requested_provider,
                    "selected": providers[0],
                }
            )

        session = ort.InferenceSession(
            model_path, sess_options=sess_options, providers=providers
        )

        input_name = session.get_inputs()[0].name
        output_names = [o.name for o in session.get_outputs()]
        self._engine = InferenceEngine(session, input_name, output_names)
        self._backend = "onnxruntime"

        # Expose attributes
        self.session = session
        self.input_name = input_name
        self.input_shape = tuple(session.get_inputs()[0].shape)
        self.output_names = output_names

        self.logger.info(
            "Model loaded via ONNX Runtime",
            extra={
                "model_path": model_path,
                "input_name": self.input_name,
                "input_shape": list(self.input_shape),
                "providers": session.get_providers(),
            }
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def get_engine(self):
        """Return the loaded inference engine (OpenVINOEngine or InferenceEngine)."""
        return self._engine

    def get_input_shape(self) -> Tuple:
        """Get model input shape (batch, channels, height, width)."""
        return tuple(self.input_shape)

    def get_session(self):
        """Compatibility accessor — returns underlying session / compiled model."""
        return self.session


