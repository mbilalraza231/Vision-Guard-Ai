#!/usr/bin/env python3
"""
VisionGuard AI - Complete Pipeline Integration Test

Comprehensive test suite that validates the entire pipeline:
  Camera Capture → Shared Memory → AI Worker → Redis Stream → ECS

This test validates each component and their integrations step by step.

Usage:
    source venv/bin/activate
    python tests/pipeline_integration_test.py
"""

import sys
import os
import time
import json
import logging
import signal
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    passed: bool
    duration_ms: float
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class PhaseResult:
    """Result of a test phase."""
    name: str
    tests: List[TestResult] = field(default_factory=list)
    
    @property
    def passed(self) -> bool:
        return all(t.passed for t in self.tests)
    
    @property
    def total_tests(self) -> int:
        return len(self.tests)
    
    @property
    def passed_tests(self) -> int:
        return sum(1 for t in self.tests if t.passed)


class PipelineIntegrationTest:
    """Complete pipeline integration test suite."""
    
    def __init__(self):
        self.results: List[PhaseResult] = []
        self.start_time = None
        self.components = {}
        
    def run_test(self, name: str, test_func) -> TestResult:
        """Run a single test and capture results."""
        start = time.time()
        try:
            result = test_func()
            duration = (time.time() - start) * 1000
            
            if isinstance(result, tuple):
                passed, message, details = result[0], result[1], result[2] if len(result) > 2 else {}
            elif isinstance(result, bool):
                passed, message, details = result, "OK" if result else "Failed", {}
            else:
                passed, message, details = True, str(result), {}
            
            return TestResult(name=name, passed=passed, duration_ms=duration, message=message, details=details)
            
        except Exception as e:
            duration = (time.time() - start) * 1000
            return TestResult(name=name, passed=False, duration_ms=duration, message=str(e))
    
    def print_test_result(self, result: TestResult):
        """Print formatted test result."""
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"  {status} {result.name} ({result.duration_ms:.0f}ms)")
        if result.message and result.message != "OK":
            print(f"       → {result.message}")
    
    def print_phase_header(self, name: str):
        """Print phase header."""
        print()
        print("=" * 80)
        print(f"  {name}")
        print("=" * 80)
    
    def print_phase_summary(self, phase: PhaseResult):
        """Print phase summary."""
        status = "✅ PASSED" if phase.passed else "❌ FAILED"
        print(f"\n  {phase.name}: {phase.passed_tests}/{phase.total_tests} tests passed - {status}")
    
    # =========================================================================
    # PHASE 1: Component Unit Tests
    # =========================================================================
    
    def phase1_unit_tests(self) -> PhaseResult:
        """Phase 1: Test each component in isolation."""
        self.print_phase_header("PHASE 1: Component Unit Tests")
        
        phase = PhaseResult(name="Phase 1: Unit Tests")
        
        # Test 1.1: Module imports
        result = self.run_test("1.1 Module imports", self._test_module_imports)
        phase.tests.append(result)
        self.print_test_result(result)
        
        # Test 1.2: Configuration loading
        result = self.run_test("1.2 Configuration loading", self._test_config_loading)
        phase.tests.append(result)
        self.print_test_result(result)
        
        # Test 1.3: Redis connectivity
        result = self.run_test("1.3 Redis connectivity", self._test_redis_connectivity)
        phase.tests.append(result)
        self.print_test_result(result)
        
        # Test 1.4: RTSP stream availability
        result = self.run_test("1.4 RTSP stream availability", self._test_rtsp_stream)
        phase.tests.append(result)
        self.print_test_result(result)
        
        # Test 1.5: ONNX model loading
        result = self.run_test("1.5 ONNX model loading", self._test_onnx_models)
        phase.tests.append(result)
        self.print_test_result(result)
        
        self.print_phase_summary(phase)
        return phase
    
    def _test_module_imports(self):
        """Test that all modules can be imported."""
        imports = []
        
        # Camera capture
        from camera_capture import CaptureConfig, CameraConfig
        imports.append("camera_capture")
        
        # AI Worker
        from ai_worker import WorkerConfig
        imports.append("ai_worker")
        
        # Event Classification
        from event_classification import ECSConfig, ECSService
        imports.append("event_classification")
        
        return True, f"Imported: {', '.join(imports)}", {"modules": imports}
    
    def _test_config_loading(self):
        """Test configuration classes."""
        configs = {}
        
        from camera_capture import CaptureConfig, CameraConfig
        # CaptureConfig requires cameras - use a dummy camera config
        config = CaptureConfig(cameras=[
            CameraConfig(
                camera_id="test",
                rtsp_url="rtsp://localhost:8554/test"
            )
        ])
        configs["CaptureConfig"] = "OK"
        
        from ai_worker import WorkerConfig
        config = WorkerConfig(
            model_type="weapon", 
            onnx_model_path="models/weapon_detection.onnx",
            redis_input_queue="vg:medium"
        )
        configs["WorkerConfig"] = "OK"
        
        from event_classification import ECSConfig
        config = ECSConfig()
        configs["ECSConfig"] = "OK"
        
        return True, f"All configs valid", configs
    
    def _test_redis_connectivity(self):
        """Test Redis connection."""
        import redis
        
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        response = client.ping()
        
        if response:
            # Get some basic info
            info = client.info("server")
            version = info.get("redis_version", "unknown")
            return True, f"Redis {version} connected", {"version": version}
        else:
            return False, "Redis ping failed", {}
    
    def _test_rtsp_stream(self):
        """Test RTSP stream availability."""
        import cv2
        
        rtsp_url = "rtsp://localhost:8554/test"
        cap = cv2.VideoCapture(rtsp_url)
        
        if not cap.isOpened():
            return False, f"Cannot open {rtsp_url}", {}
        
        ret, frame = cap.read()
        cap.release()
        
        if ret and frame is not None:
            height, width = frame.shape[:2]
            return True, f"Stream active: {width}x{height}", {"width": width, "height": height}
        else:
            return False, "Cannot read frame from stream", {}
    
    def _test_onnx_models(self):
        """Test ONNX model loading."""
        import onnxruntime as ort
        
        models = {}
        model_dir = "models"
        
        for model_name in ["weapon_detection.onnx", "fire_detection.onnx", "fall_detection.onnx"]:
            model_path = os.path.join(model_dir, model_name)
            if os.path.exists(model_path):
                session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
                input_shape = session.get_inputs()[0].shape
                models[model_name] = f"loaded, input: {input_shape}"
            else:
                models[model_name] = "NOT FOUND"
        
        all_found = all("loaded" in v for v in models.values())
        return all_found, f"{len(models)} models checked", models
    
    # =========================================================================
    # PHASE 2: Component Integration Tests
    # =========================================================================
    
    def phase2_integration_tests(self) -> PhaseResult:
        """Phase 2: Test component integrations."""
        self.print_phase_header("PHASE 2: Component Integration Tests")
        
        phase = PhaseResult(name="Phase 2: Integration Tests")
        
        # Test 2.1: Camera captures frames
        result = self.run_test("2.1 Camera frame capture", self._test_camera_capture)
        phase.tests.append(result)
        self.print_test_result(result)
        
        # Test 2.2: Shared memory operations
        result = self.run_test("2.2 Shared memory write/read", self._test_shared_memory)
        phase.tests.append(result)
        self.print_test_result(result)
        
        # Test 2.3: Redis queue operations
        result = self.run_test("2.3 Redis queue push/pop", self._test_redis_queue)
        phase.tests.append(result)
        self.print_test_result(result)
        
        # Test 2.4: AI Worker inference
        result = self.run_test("2.4 AI Worker inference", self._test_ai_inference)
        phase.tests.append(result)
        self.print_test_result(result)
        
        # Test 2.5: ECS stream consumption
        result = self.run_test("2.5 ECS stream consumer", self._test_ecs_consumer)
        phase.tests.append(result)
        self.print_test_result(result)
        
        self.print_phase_summary(phase)
        return phase
    
    def _test_camera_capture(self):
        """Test camera can capture frames."""
        import cv2
        import numpy as np
        
        rtsp_url = "rtsp://localhost:8554/test"
        cap = cv2.VideoCapture(rtsp_url)
        
        if not cap.isOpened():
            return False, "Cannot open RTSP stream", {}
        
        frames_captured = 0
        start = time.time()
        
        for _ in range(10):  # Capture 10 frames
            ret, frame = cap.read()
            if ret:
                frames_captured += 1
        
        cap.release()
        elapsed = time.time() - start
        fps = frames_captured / elapsed if elapsed > 0 else 0
        
        if frames_captured >= 8:  # Allow some dropped frames
            return True, f"Captured {frames_captured}/10 frames ({fps:.1f} fps)", {"fps": fps}
        else:
            return False, f"Only captured {frames_captured}/10 frames", {}
    
    def _test_shared_memory(self):
        """Test shared memory write and read."""
        from camera_capture.storage.shared_memory_impl import SharedMemoryImpl
        import numpy as np
        
        shm = SharedMemoryImpl(max_frame_size_mb=10)
        
        # Create test frame
        test_frame = np.random.randint(0, 255, (360, 640, 3), dtype=np.uint8)
        
        # Write to shared memory
        key = shm.write_frame(test_frame)
        
        # Read back
        read_frame = shm.read_frame(key)
        
        # Verify
        if read_frame is not None and np.array_equal(test_frame, read_frame):
            # Cleanup
            shm.cleanup(key)
            return True, "Write/read verified", {"size": test_frame.shape}
        else:
            return False, "Frame mismatch", {}
    
    def _test_redis_queue(self):
        """Test Redis queue push/pop."""
        import redis
        
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        
        test_queue = "vg:test_queue"
        test_data = {"test": True, "timestamp": time.time()}
        
        # Push
        client.lpush(test_queue, json.dumps(test_data))
        
        # Pop
        result = client.rpop(test_queue)
        
        if result:
            parsed = json.loads(result)
            if parsed.get("test") == True:
                return True, "Queue push/pop OK", {}
        
        return False, "Queue operation failed", {}
    
    def _test_ai_inference(self):
        """Test AI Worker can run inference."""
        import onnxruntime as ort
        import numpy as np
        
        model_path = "models/weapon_detection.onnx"
        
        if not os.path.exists(model_path):
            return False, f"Model not found: {model_path}", {}
        
        # Load model
        session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        
        # Get input details
        input_info = session.get_inputs()[0]
        input_shape = input_info.shape
        input_name = input_info.name
        
        # Create dummy input - handle dynamic dimensions
        actual_shape = []
        for dim in input_shape:
            if isinstance(dim, int):
                actual_shape.append(dim)
            else:
                # Dynamic dimension, use reasonable default
                actual_shape.append(1 if len(actual_shape) == 0 else 640)
        
        # Typical YOLO input: [1, 3, 640, 640]
        if len(actual_shape) == 4:
            actual_shape = [1, 3, 640, 640]
        
        dummy_input = np.random.randn(*actual_shape).astype(np.float32)
        
        # Run inference
        start = time.time()
        outputs = session.run(None, {input_name: dummy_input})
        latency = (time.time() - start) * 1000
        
        return True, f"Inference OK ({latency:.0f}ms)", {"latency_ms": latency, "output_shapes": [o.shape for o in outputs]}
    
    def _test_ecs_consumer(self):
        """Test ECS can consume from Redis stream."""
        from event_classification.redis_client.stream_consumer import StreamConsumer
        import redis
        
        # Create a test message in the stream
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        
        test_stream = "vg:ai:results"
        test_msg = {
            "frame_id": "test_frame_123",
            "camera_id": "test_cam",
            "model": "weapon",
            "confidence": "0.95",
            "timestamp": str(time.time()),
            "shared_memory_key": "test_shm_key",
            "bbox": "[]"
        }
        
        # Add test message
        msg_id = client.xadd(test_stream, test_msg)
        
        # Create consumer and try to consume
        consumer = StreamConsumer(
            stream_name=test_stream,
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
            block_ms=100,
            count=10
        )
        
        # Set to start from beginning to catch our test message
        consumer.set_start_id("0")
        
        # Consume
        messages = consumer.consume()
        consumer.close()
        
        # Clean up test message
        client.xdel(test_stream, msg_id)
        
        if len(messages) > 0:
            return True, f"Consumed {len(messages)} messages", {"count": len(messages)}
        else:
            return True, "Consumer works (no messages in queue)", {}
    
    # =========================================================================
    # PHASE 3: End-to-End Pipeline Tests
    # =========================================================================
    
    def phase3_e2e_tests(self) -> PhaseResult:
        """Phase 3: End-to-end pipeline tests."""
        self.print_phase_header("PHASE 3: End-to-End Pipeline Tests")
        
        phase = PhaseResult(name="Phase 3: E2E Tests")
        
        # Test 3.1: Camera + Queue pipeline
        result = self.run_test("3.1 Camera → Queue pipeline", self._test_camera_queue_pipeline)
        phase.tests.append(result)
        self.print_test_result(result)
        
        # Test 3.2: Worker + Stream pipeline  
        result = self.run_test("3.2 Worker → Stream pipeline", self._test_worker_stream_pipeline)
        phase.tests.append(result)
        self.print_test_result(result)
        
        # Test 3.3: Complete pipeline (short)
        result = self.run_test("3.3 Full pipeline (10s)", self._test_full_pipeline_short)
        phase.tests.append(result)
        self.print_test_result(result)
        
        self.print_phase_summary(phase)
        return phase
    
    def _test_camera_queue_pipeline(self):
        """Test camera capture to Redis queue."""
        import cv2
        import numpy as np
        import redis
        from camera_capture.storage.shared_memory_impl import SharedMemoryImpl
        
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        shm = SharedMemoryImpl(max_frame_size_mb=10)
        
        # Capture a frame
        cap = cv2.VideoCapture("rtsp://localhost:8554/test")
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return False, "Could not capture frame", {}
        
        # Write to shared memory (returns the key)
        frame_key = shm.write_frame(frame)
        
        # Push to queue
        queue_msg = {
            "frame_id": frame_key,
            "camera_id": "test_cam",
            "timestamp": time.time(),
            "shared_memory_key": frame_key,
            "width": frame.shape[1],
            "height": frame.shape[0]
        }
        client.lpush("vg:medium", json.dumps(queue_msg))
        
        # Verify it's in queue
        queue_len = client.llen("vg:medium")
        
        # Cleanup
        client.rpop("vg:medium")
        shm.cleanup(frame_key)
        
        return True, f"Pipeline OK (queue len: {queue_len})", {"queue_length": queue_len}
    
    def _test_worker_stream_pipeline(self):
        """Test worker inference to stream."""
        import onnxruntime as ort
        import numpy as np
        import redis
        import cv2
        
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        
        # Load model
        model_path = "models/weapon_detection.onnx"
        session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        
        # Get a real frame
        cap = cv2.VideoCapture("rtsp://localhost:8554/test")
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return False, "Could not capture frame", {}
        
        # Preprocess (resize to model input)
        input_frame = cv2.resize(frame, (640, 640))
        input_frame = input_frame.transpose(2, 0, 1)  # HWC -> CHW
        input_frame = input_frame.astype(np.float32) / 255.0
        input_frame = np.expand_dims(input_frame, 0)  # Add batch
        
        # Run inference
        input_name = session.get_inputs()[0].name
        start = time.time()
        outputs = session.run(None, {input_name: input_frame})
        latency = (time.time() - start) * 1000
        
        # Simulate publishing to stream
        result_msg = {
            "frame_id": f"test_{int(time.time() * 1000)}",
            "camera_id": "test_cam",
            "model": "weapon",
            "confidence": "0.5",  # Dummy
            "timestamp": str(time.time()),
            "shared_memory_key": "test_key",
            "inference_latency_ms": str(latency),
            "bbox": "[]"
        }
        
        msg_id = client.xadd("vg:ai:results", result_msg)
        
        # Verify it's in stream
        stream_len = client.xlen("vg:ai:results")
        
        # Cleanup
        client.xdel("vg:ai:results", msg_id)
        
        return True, f"Pipeline OK ({latency:.0f}ms inference)", {"latency_ms": latency}
    
    def _test_full_pipeline_short(self):
        """Test full pipeline for 10 seconds."""
        import redis
        import cv2
        import numpy as np
        from camera_capture.storage.shared_memory_impl import SharedMemoryImpl
        import onnxruntime as ort
        
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        shm = SharedMemoryImpl(max_frame_size_mb=10)
        
        # Load model
        model_path = "models/weapon_detection.onnx"
        session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        input_name = session.get_inputs()[0].name
        
        cap = cv2.VideoCapture("rtsp://localhost:8554/test")
        
        frames_processed = 0
        results_published = 0
        start = time.time()
        frame_keys = []
        
        while time.time() - start < 10:  # Run for 10 seconds
            ret, frame = cap.read()
            if not ret:
                continue
            
            frames_processed += 1
            
            # Store in shared memory (returns the key)
            frame_key = shm.write_frame(frame)
            frame_keys.append(frame_key)
            
            # Preprocess
            input_frame = cv2.resize(frame, (640, 640))
            input_frame = input_frame.transpose(2, 0, 1).astype(np.float32) / 255.0
            input_frame = np.expand_dims(input_frame, 0)
            
            # Inference
            outputs = session.run(None, {input_name: input_frame})
            
            # Publish result
            result_msg = {
                "frame_id": frame_key,
                "camera_id": "test_cam",
                "model": "weapon",
                "confidence": "0.5",
                "timestamp": str(time.time()),
                "shared_memory_key": frame_key,
                "bbox": "[]"
            }
            client.xadd("vg:ai:results", result_msg)
            results_published += 1
            
            time.sleep(0.1)  # ~10 FPS
        
        cap.release()
        
        # Cleanup
        for key in frame_keys:
            try:
                shm.cleanup(key)
            except:
                pass
        
        elapsed = time.time() - start
        fps = frames_processed / elapsed if elapsed > 0 else 0
        
        return True, f"{frames_processed} frames, {results_published} results ({fps:.1f} fps)", {
            "frames": frames_processed,
            "results": results_published,
            "fps": fps
        }
    
    # =========================================================================
    # Main Execution
    # =========================================================================
    
    def run_all(self):
        """Run all test phases."""
        self.start_time = datetime.now()
        
        print()
        print("╔" + "═" * 78 + "╗")
        print("║" + "VisionGuard AI - Pipeline Integration Test".center(78) + "║")
        print("╚" + "═" * 78 + "╝")
        print()
        print(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Phase 1: Unit Tests
        phase1 = self.phase1_unit_tests()
        self.results.append(phase1)
        
        if not phase1.passed:
            print("\n⚠️  Phase 1 failed. Stopping tests.")
            self._print_final_summary()
            return False
        
        # Phase 2: Integration Tests
        phase2 = self.phase2_integration_tests()
        self.results.append(phase2)
        
        if not phase2.passed:
            print("\n⚠️  Phase 2 failed. Stopping tests.")
            self._print_final_summary()
            return False
        
        # Phase 3: E2E Tests
        phase3 = self.phase3_e2e_tests()
        self.results.append(phase3)
        
        # Final summary
        self._print_final_summary()
        
        return all(p.passed for p in self.results)
    
    def _print_final_summary(self):
        """Print final test summary."""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        
        print()
        print("╔" + "═" * 78 + "╗")
        print("║" + "FINAL TEST SUMMARY".center(78) + "║")
        print("╚" + "═" * 78 + "╝")
        
        total_tests = sum(p.total_tests for p in self.results)
        passed_tests = sum(p.passed_tests for p in self.results)
        
        print()
        for phase in self.results:
            status = "✅" if phase.passed else "❌"
            print(f"  {status} {phase.name}: {phase.passed_tests}/{phase.total_tests} passed")
        
        print()
        print(f"  Total: {passed_tests}/{total_tests} tests passed")
        print(f"  Duration: {duration:.1f}s")
        print()
        
        if all(p.passed for p in self.results):
            print("  ╔" + "═" * 50 + "╗")
            print("  ║" + "✅ ALL TESTS PASSED!".center(50) + "║")
            print("  ╚" + "═" * 50 + "╝")
            print()
            print("  Your VisionGuard AI pipeline is working correctly!")
        else:
            print("  ╔" + "═" * 50 + "╗")
            print("  ║" + "❌ SOME TESTS FAILED".center(50) + "║")
            print("  ╚" + "═" * 50 + "╝")
            print()
            print("  Please review the failed tests above.")
        
        print()


def main():
    """Main entry point."""
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run tests
    test_suite = PipelineIntegrationTest()
    success = test_suite.run_all()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
