#!/usr/bin/env python3
"""
VisionGuard AI - System Diagnostics

Checks all system components and prints a status report.
Usage: python scripts/diagnose.py
"""

import os
import sys
import sqlite3

# Resolve project root (parent of scripts/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(label: str, ok: bool, msg: str) -> bool:
    tag = "[  OK  ]" if ok else "[ FAIL ]"
    print(f"  {tag}  {label}: {msg}")
    return ok


def check_warn(label: str, msg: str) -> bool:
    print(f"  [ WARN ]  {label}: {msg}")
    return False


def check_miss(label: str, msg: str) -> bool:
    print(f"  [ MISS ]  {label}: {msg}")
    return False


def diagnose_redis() -> bool:
    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    try:
        import redis
        r = redis.Redis(host=host, port=port, socket_timeout=3)
        r.ping()
        info = r.info("server")
        version = info.get("redis_version", "unknown")
        return check("Redis", True, f"{version} connected ({host}:{port})")
    except ImportError:
        return check("Redis", False, "redis package not installed")
    except Exception as e:
        return check("Redis", False, f"connection failed ({e})")


def diagnose_backend() -> bool:
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:8000/health", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                return check("Backend API", True, "healthy")
            else:
                return check("Backend API", False, f"HTTP {resp.status}")
    except Exception as e:
        return check("Backend API", False, f"unreachable ({e})")


def diagnose_ecs() -> bool:
    try:
        import urllib.request
        import json
        req = urllib.request.Request("http://localhost:8000/ecs/status", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            state = data.get("state", "unknown")
            if state == "running":
                return check("ECS", True, f"state: {state}")
            else:
                return check_warn("ECS", f"state: {state}")
    except Exception as e:
        return check("ECS", False, f"unreachable ({e})")


def diagnose_cameras() -> bool:
    try:
        import urllib.request
        import json
        req = urllib.request.Request("http://localhost:8000/cameras/status", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            total = data.get("total", 0)
            running = data.get("running", 0)
            return check("Cameras", True, f"{total} registered, {running} running")
    except Exception as e:
        return check("Cameras", False, f"unreachable ({e})")


def diagnose_database() -> bool:
    db_path = os.environ.get("VG_DB_PATH", "/tmp/visionguard/events.db")
    if not os.path.exists(db_path):
        return check("Database", False, f"file not found ({db_path})")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM events")
        count = cursor.fetchone()[0]
        conn.close()
        return check("Database", True, f"{count} events (path: {db_path})")
    except Exception as e:
        return check("Database", False, f"query failed ({e})")


def diagnose_models() -> int:
    passed = 0
    models = [
        "models/fire_detection.onnx",
        "models/weapon_detection.onnx",
        "models/fall_detection.onnx",
    ]
    for model in models:
        full_path = os.path.join(PROJECT_ROOT, model)
        if os.path.exists(full_path):
            size_mb = os.path.getsize(full_path) / (1024 * 1024)
            check("Model", True, f"{model} ({size_mb:.1f} MB)")
            passed += 1
        else:
            check_miss("Model", model)
    return passed


def main():
    print()
    print("  VisionGuard AI — System Diagnostics")
    print("  " + "─" * 40)
    print()

    total = 0
    passed = 0

    # Redis
    total += 1
    if diagnose_redis():
        passed += 1

    # Backend API
    total += 1
    if diagnose_backend():
        passed += 1

    # ECS
    total += 1
    if diagnose_ecs():
        passed += 1

    # Cameras
    total += 1
    if diagnose_cameras():
        passed += 1

    # Database
    total += 1
    if diagnose_database():
        passed += 1

    # Models (3 checks)
    model_passed = diagnose_models()
    total += 3
    passed += model_passed

    print()
    print("  " + "─" * 40)
    print(f"  System status: {passed}/{total} checks passed")
    print()

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
