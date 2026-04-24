"""
VisionGuard AI - Simple System Check

Verifies that all modules can be imported and basic functionality works.
No camera or Redis required.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_imports():
    """Test that all modules can be imported."""
    print("\n" + "=" * 80)
    print("VisionGuard AI - System Check")
    print("=" * 80)
    print("\nTesting module imports...")
    
    try:
        # Test camera_capture
        print("\n1. Testing camera_capture module...")
        from camera_capture import CaptureConfig, CameraConfig
        print("   ✅ camera_capture imports successfully")
        
        # Test ai_worker
        print("\n2. Testing ai_worker module...")
        from ai_worker import WorkerConfig
        print("   ✅ ai_worker imports successfully")
        
        # Test event_classification
        print("\n3. Testing event_classification module...")
        from event_classification import ECSConfig
        print("   ✅ event_classification imports successfully")
        
        # Test dependencies
        print("\n4. Testing dependencies...")
        import pydantic
        print(f"   ✅ pydantic {pydantic.__version__}")
        
        import redis
        print(f"   ✅ redis {redis.__version__}")
        
        import numpy
        print(f"   ✅ numpy {numpy.__version__}")
        
        import cv2
        print(f"   ✅ opencv {cv2.__version__}")
        
        import onnxruntime
        print(f"   ✅ onnxruntime {onnxruntime.__version__}")
        
        print("\n" + "=" * 80)
        print("✅ ALL CHECKS PASSED!")
        print("=" * 80)
        print("\nYour VisionGuard AI environment is properly configured.")
        print("\nNext steps:")
        print("  1. Ensure Redis is running: redis-cli ping")
        print("  2. Set up RTSP camera stream (for camera tests)")
        print("  3. Run full test suite: python tests/run_test_suite.py")
        
        return True
        
    except ImportError as e:
        print(f"\n❌ Import failed: {e}")
        print("\nMake sure you activated the virtual environment:")
        print("  source venv/bin/activate")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False


if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
