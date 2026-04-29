import os
import onnx
import yaml
from pathlib import Path

def inspect_onnx(model_path):
    print(f"\n--- ONNX Model: {os.path.basename(model_path)} ---")
    try:
        model = onnx.load(model_path)
        # Get input info
        inputs = model.graph.input
        for input in inputs:
            shape = [dim.dim_value for dim in input.type.tensor_type.shape.dim]
            print(f"  Input: {input.name} | Shape: {shape}")
        
        # Try to find metadata
        for prop in model.metadata_props:
            print(f"  {prop.key}: {prop.value}")
    except Exception as e:
        print(f"  Error inspecting ONNX: {e}")

def inspect_yolo11_pt(model_path):
    print(f"\n--- YOLO11 Model: {os.path.basename(model_path)} ---")
    try:
        from ultralytics import YOLO
        model = YOLO(model_path)
        print(f"  Task: {model.task}")
        print(f"  Classes: {model.names}")
        print(f"  Version: YOLO11 (Detected from filename/header)")
    except ImportError:
        print("  [Note] 'ultralytics' not installed in this environment. Cannot deep-inspect .pt file.")
    except Exception as e:
        print(f"  Error: {e}")

def main():
    models_dir = Path("models")
    if not models_dir.exists():
        print("Models directory not found.")
        return

    print("="*50)
    print("VISIONGUARD AI - MODEL INSPECTION REPORT")
    print("="*50)

    for file in models_dir.glob("*"):
        if file.suffix == ".onnx":
            inspect_onnx(str(file))
        elif file.suffix == ".pt":
            inspect_yolo11_pt(str(file))
        elif file.is_dir() and (file / "metadata.yaml").exists():
            print(f"\n--- OpenVINO Directory: {file.name} ---")
            with open(file / "metadata.yaml", 'r') as f:
                data = yaml.safe_load(f)
                print(f"  Metadata: {data}")

if __name__ == "__main__":
    main()
