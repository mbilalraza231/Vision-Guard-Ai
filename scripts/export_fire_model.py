#!/usr/bin/env python3
"""
VisionGuard AI - YOLOv11n Fire Model Export & Benchmark Script

Run this ONCE on the HOST (not inside Docker) to:
  1. Load yolov11n_fire.pt (custom) or yolo11n.pt (base fallback)
  2. Export to OpenVINO INT8 with imgsz=416
  3. Run a 60-second benchmark comparing ONNX vs OpenVINO
  4. Print FPS and avg CPU% for both backends

Usage:
    pip install ultralytics openvino psutil
    python scripts/export_fire_model.py [--source 0]

Output:
    models/fire_openvino_model/   <-- mount this into worker-fire container
"""

import os
import sys
import time
import argparse
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(ROOT, "models")
CUSTOM_PT = os.path.join(MODELS_DIR, "yolov11n_fire.pt")
BASE_PT = os.path.join(MODELS_DIR, "yolo11n.pt")
OPENVINO_DIR = os.path.join(MODELS_DIR, "fire_openvino_model")


def check_deps():
    """Check required packages are installed."""
    missing = []
    for pkg in ["ultralytics", "openvino", "psutil"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[ERROR] Missing packages: {', '.join(missing)}")
        print(f"  Install: pip install {' '.join(missing)}")
        sys.exit(1)


def resolve_model_pt():
    """Return path to .pt model, downloading base if needed."""
    if os.path.exists(CUSTOM_PT):
        print(f"[OK] Found custom model: {CUSTOM_PT}")
        return CUSTOM_PT

    print(f"[WARN] yolov11n_fire.pt not found at {CUSTOM_PT}")
    print("[INFO] Falling back to base yolo11n.pt (Ultralytics will download)")
    return "yolo11n.pt"  # Ultralytics auto-downloads to ~/.ultralytics/


def export_openvino(pt_path: str):
    """Export .pt model to OpenVINO INT8 at imgsz=416."""
    if os.path.isdir(OPENVINO_DIR) and os.listdir(OPENVINO_DIR):
        print(f"[SKIP] OpenVINO model already exists: {OPENVINO_DIR}")
        return OPENVINO_DIR

    from ultralytics import YOLO

    print(f"\n[EXPORT] Exporting {pt_path} → OpenVINO INT8 (imgsz=416) ...")
    print("  This may take 3-10 minutes on first run (INT8 calibration).")

    model = YOLO(pt_path)
    export_path = model.export(
        format="openvino",
        int8=True,
        imgsz=416,
        half=False,  # INT8 takes priority
    )

    # Ultralytics exports next to .pt file — move to models/ if needed
    auto_dir = str(export_path)
    if os.path.isdir(auto_dir) and auto_dir != OPENVINO_DIR:
        import shutil
        os.makedirs(MODELS_DIR, exist_ok=True)
        if os.path.exists(OPENVINO_DIR):
            shutil.rmtree(OPENVINO_DIR)
        shutil.move(auto_dir, OPENVINO_DIR)

    print(f"[OK] OpenVINO model saved to: {OPENVINO_DIR}")
    return OPENVINO_DIR


def benchmark(pt_path: str, openvino_dir: str, source, duration_sec: int = 60):
    """Run 60-second benchmark: ONNX baseline vs OpenVINO optimized."""
    import psutil
    import numpy as np
    from ultralytics import YOLO

    results = {}

    for label, model_path, backend in [
        ("ONNX (Baseline)", pt_path, "cpu"),
        ("OpenVINO INT8 (Optimized)", openvino_dir, "openvino"),
    ]:
        print(f"\n{'='*60}")
        print(f"  Benchmarking: {label}")
        print(f"  model={model_path}  source={source}  backend={backend}")
        print(f"  Duration: {duration_sec}s")
        print(f"{'='*60}")

        model = YOLO(model_path)

        frame_count = 0
        cpu_samples = []
        start = time.time()

        # Stream inference
        for r in model.predict(
            source=source,
            conf=0.40,
            iou=0.45,
            imgsz=416,
            stream=True,
            device=backend,
            verbose=False,
            agnostic_nms=True,
        ):
            frame_count += 1
            cpu_samples.append(psutil.cpu_percent(interval=None))

            elapsed = time.time() - start
            if frame_count % 30 == 0:
                fps = frame_count / elapsed
                avg_cpu = sum(cpu_samples[-30:]) / len(cpu_samples[-30:])
                print(f"  [{elapsed:5.1f}s] FPS: {fps:.1f}  CPU: {avg_cpu:.1f}%")

            if elapsed >= duration_sec:
                break

        total_elapsed = time.time() - start
        final_fps = frame_count / total_elapsed if total_elapsed > 0 else 0
        avg_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0

        results[label] = {"fps": final_fps, "cpu": avg_cpu, "frames": frame_count}
        print(f"\n  RESULT — FPS: {final_fps:.2f}  Avg CPU: {avg_cpu:.1f}%  Frames: {frame_count}")

    print(f"\n{'='*60}")
    print("  BENCHMARK COMPARISON SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Backend':<35} {'FPS':>8} {'Avg CPU':>10} {'Frames':>8}")
    print(f"  {'-'*61}")
    for label, r in results.items():
        print(f"  {label:<35} {r['fps']:>8.2f} {r['cpu']:>9.1f}% {r['frames']:>8}")

    if len(results) == 2:
        baseline = list(results.values())[0]
        optimized = list(results.values())[1]
        speedup = optimized["fps"] / baseline["fps"] if baseline["fps"] > 0 else 0
        print(f"\n  Speedup: {speedup:.2f}x  ({optimized['fps']:.1f} vs {baseline['fps']:.1f} FPS)")
    print(f"{'='*60}\n")

    return results


def main():
    parser = argparse.ArgumentParser(description="Export YOLOv11n-Fire to OpenVINO + benchmark")
    parser.add_argument("--source", default="0", help="Video source: 0 (webcam), RTSP URL, or video file")
    parser.add_argument("--duration", type=int, default=60, help="Benchmark duration in seconds (default: 60)")
    parser.add_argument("--export-only", action="store_true", help="Export only, skip benchmark")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  VisionGuard AI — Fire Model Export (YOLOv11n → OpenVINO)")
    print("="*60 + "\n")

    check_deps()

    pt_path = resolve_model_pt()
    openvino_dir = export_openvino(pt_path)

    if args.export_only:
        print("[Done] Export complete. OpenVINO model ready.")
        return

    source = args.source
    try:
        source = int(source)
    except ValueError:
        pass  # keep as string (RTSP/file path)

    benchmark(pt_path, openvino_dir, source, duration_sec=args.duration)

    print("[INFO] OpenVINO model path to mount in Docker:")
    print(f"  Host:      {OPENVINO_DIR}")
    print(f"  Container: /app/models/fire_openvino_model")
    print("\n[DONE] Run 'docker compose build --no-cache worker-fire' next.\n")


if __name__ == "__main__":
    main()
