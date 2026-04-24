#!/usr/bin/env python3
"""
VisionGuard AI - Confidence Threshold Inspector

Grabs a live frame from an enabled camera, runs a real ONNX model,
and prints raw confidence scores to help tune thresholds.

Usage: python scripts/check_confidence.py --model weapon
       python scripts/check_confidence.py --model fire
       python scripts/check_confidence.py --model fall
"""

import argparse
import json
import os
import sys

import cv2
import numpy as np
import onnxruntime as ort

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODEL_PATHS = {
    "fire": os.path.join(PROJECT_ROOT, "models", "fire_detection.onnx"),
    "weapon": os.path.join(PROJECT_ROOT, "models", "weapon_detection.onnx"),
    "fall": os.path.join(PROJECT_ROOT, "models", "fall_detection.onnx"),
}

# Current thresholds from docker-compose.yml and ECS config
THRESHOLDS = {
    "fire": {"worker": 0.25, "ecs": 0.40},
    "weapon": {"worker": 0.25, "ecs": 0.50},
    "fall": {"worker": 0.25, "ecs": 0.45},
}


def get_camera_source() -> str:
    """Read cameras.json, return source of first enabled camera."""
    cameras_path = os.path.join(PROJECT_ROOT, "cameras.json")
    if not os.path.exists(cameras_path):
        print(f"ERROR: cameras.json not found at {cameras_path}")
        sys.exit(1)

    with open(cameras_path) as f:
        data = json.load(f)

    for cam in data.get("cameras", []):
        if cam.get("enabled", False):
            return cam["source"]

    print("ERROR: No enabled camera found in cameras.json")
    sys.exit(1)


def grab_frame(source: str) -> np.ndarray:
    """Grab a single frame from the camera source."""
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera source: {source}")
        sys.exit(1)

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        print("ERROR: Failed to grab frame")
        sys.exit(1)

    return frame


def preprocess(frame: np.ndarray) -> np.ndarray:
    """Preprocess exactly like the real worker pipeline."""
    # Resize to 640x640
    resized = cv2.resize(frame, (640, 640))
    # BGR → RGB
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    # Normalize to [0, 1]
    normalized = rgb.astype(np.float32) / 255.0
    # HWC → NCHW
    transposed = np.transpose(normalized, (2, 0, 1))
    batched = np.expand_dims(transposed, axis=0)
    return batched


def parse_yolo_output(output: np.ndarray, model_type: str):
    """
    Parse YOLOv8 output tensor.

    Output shape: (1, C, 8400) where C is:
      - 84 for fire/weapon (80 COCO classes + 4 bbox coords)
      - 56 for fall/pose (4 bbox + 1 class + 51 keypoints)

    Returns list of (confidence, bbox) tuples sorted by confidence desc.
    """
    # Squeeze batch dim: (C, 8400)
    out = output[0]
    # Transpose to (8400, C)
    detections = out.T

    results = []
    num_cols = detections.shape[1]

    for det in detections:
        # Bounding box
        cx, cy, w, h = det[0], det[1], det[2], det[3]
        x1 = int(cx - w / 2)
        y1 = int(cy - h / 2)
        x2 = int(cx + w / 2)
        y2 = int(cy + h / 2)
        bbox = [x1, y1, x2, y2]

        if model_type == "fall" and num_cols == 56:
            # Pose model: column 4 is class score (raw logit → sigmoid)
            raw = det[4]
            confidence = float(1.0 / (1.0 + np.exp(-raw)))
        else:
            # Object detection: columns 4+ are class scores
            class_scores = det[4:]
            confidence = float(np.max(class_scores))

        results.append((confidence, bbox))

    # Sort by confidence descending
    results.sort(key=lambda x: x[0], reverse=True)
    return results


def main():
    parser = argparse.ArgumentParser(
        description="VisionGuard AI - Confidence Threshold Inspector"
    )
    parser.add_argument(
        "--model",
        required=True,
        choices=["fire", "weapon", "fall"],
        help="Model to test: fire, weapon, or fall",
    )
    args = parser.parse_args()

    model_path = MODEL_PATHS[args.model]
    if not os.path.exists(model_path):
        print(f"ERROR: Model not found: {model_path}")
        print("Run: bash scripts/setup_models.sh")
        sys.exit(1)

    # Get camera source
    source = get_camera_source()
    model_name = os.path.basename(model_path)

    print(f"\n  Model: {model_name}")
    print(f"  Camera source: {source}")

    # Load model
    session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name

    # Grab frame
    frame = grab_frame(source)
    h, w = frame.shape[:2]
    print(f"  Frame: {w}x{h} grabbed")

    # Preprocess
    blob = preprocess(frame)

    # Run inference
    outputs = session.run(None, {input_name: blob})
    output = outputs[0]

    # Parse results
    results = parse_yolo_output(output, args.model)
    top5 = results[:5]

    # Print
    print(f"\n  Top 5 raw detections:")
    for i, (conf, bbox) in enumerate(top5, 1):
        print(f"    {i}. confidence={conf:.4f}  bbox={bbox}")

    # Print current thresholds
    th = THRESHOLDS[args.model]
    print(f"\n  Current thresholds (from docker-compose.yml / ECS config):")
    print(f"    Worker pre-filter:  {th['worker']}")
    print(f"    ECS {args.model} gate:    {th['ecs']}")
    print()


if __name__ == "__main__":
    main()
