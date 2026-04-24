#!/bin/bash
# VisionGuard AI - Quick ONNX Model Setup
# This script downloads YOLOv8 models and exports them to ONNX format

set -e  # Exit on error

echo "========================================================================"
echo "VisionGuard AI - ONNX Model Setup"
echo "========================================================================"
echo ""

# Check if virtual environment is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Virtual environment not activated!"
    echo "Activating venv..."
    source venv/bin/activate
fi

# Install ultralytics
echo "Installing ultralytics (YOLOv8)..."
pip install -q ultralytics

# Create models directory
echo "Creating models directory..."
mkdir -p models

# Download and export models
echo ""
echo "Downloading and exporting ONNX models..."
echo "This may take a few minutes..."
echo ""

python3 << 'EOF'
from ultralytics import YOLO
import os
import sys

models_config = [
    ('yolov8n.pt', 'models/weapon_detection.onnx', 'Weapon Detection'),
    ('yolov8s.pt', 'models/fire_detection.onnx', 'Fire Detection'),
    ('yolov8n-pose.pt', 'models/fall_detection.onnx', 'Fall Detection')
]

print("="*70)
for pt_model, onnx_path, description in models_config:
    print(f"\n📦 {description}")
    print(f"   Downloading {pt_model}...")
    
    try:
        model = YOLO(pt_model)
        print(f"   Exporting to ONNX format...")
        model.export(format='onnx', simplify=True)
        
        # Find and rename the exported file
        exported_file = pt_model.replace('.pt', '.onnx')
        if os.path.exists(exported_file):
            os.rename(exported_file, onnx_path)
            file_size = os.path.getsize(onnx_path) / (1024 * 1024)
            print(f"   ✅ Saved to {onnx_path} ({file_size:.1f} MB)")
        else:
            print(f"   ❌ Export failed - file not found")
            sys.exit(1)
    except Exception as e:
        print(f"   ❌ Error: {e}")
        sys.exit(1)

print("\n" + "="*70)
print("✅ All models downloaded and exported successfully!")
print("="*70)
EOF

# Verify models
echo ""
echo "Verifying models..."
python3 << 'EOF'
import onnxruntime as ort
import os

models = ['weapon_detection.onnx', 'fire_detection.onnx', 'fall_detection.onnx']
all_ok = True

for model_name in models:
    model_path = os.path.join('models', model_name)
    try:
        session = ort.InferenceSession(model_path)
        input_shape = session.get_inputs()[0].shape
        print(f"✅ {model_name:25s} - Input shape: {input_shape}")
    except Exception as e:
        print(f"❌ {model_name:25s} - ERROR: {e}")
        all_ok = False

if all_ok:
    print("\n✅ All models verified successfully!")
else:
    print("\n❌ Some models failed verification")
    exit(1)
EOF

echo ""
echo "========================================================================"
echo "Setup Complete!"
echo "========================================================================"
echo ""
echo "Model locations:"
ls -lh models/*.onnx
echo ""
echo "Next steps:"
echo "  1. Update your test configurations with these model paths"
echo "  2. Run the system tests"
echo ""
echo "Note: These are general YOLOv8 models for testing."
echo "      For production, train custom models on your specific data."
echo ""
