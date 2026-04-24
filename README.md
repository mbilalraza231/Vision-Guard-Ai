# VisionGuard AI

Real-time AI surveillance system that detects fire, weapons, and fallen persons from video feeds using CPU-based ONNX inference. Events are stored in SQLite and displayed on a React dashboard.

## System Requirements

- Python 3.10+
- Redis 6+
- OpenCV (`opencv-python-headless`)
- ONNX Runtime (`onnxruntime`)
- Node.js 18+ (for dashboard)

## Quick Start

```bash
# Install Python dependencies
pip install -r requirements.txt

# Download ONNX models
bash scripts/setup_models.sh

# Configure cameras
# Edit cameras.json — set source URLs and enabled: true/false

# Start all services
bash scripts/start.sh

# Start the React dashboard
cd visionguard-dashboard-29
npm install
npm run dev

# Open dashboard
# http://localhost:5173

# API docs
# http://localhost:8000/docs
```

## Project Structure

```
├── camera_capture/          # Video capture + motion detection
├── ai_worker/               # ONNX inference workers (fire/weapon/fall)
├── event_classification/    # Event classification service (ECS)
├── backend/                 # FastAPI control plane + REST API
├── visionguard-dashboard-29/  # React dashboard (TypeScript + Tailwind)
├── db/                      # Database schema + initialization
├── alerts/                  # Alert dispatch (webhook/email)
├── models/                  # ONNX model files (not in git)
├── scripts/                 # Utility scripts
├── docs/                    # Documentation
├── tests/                   # Test suite
├── docker/                  # Dockerfiles + supervisor configs
├── cameras.json             # Camera configuration
├── docker-compose.yml       # Docker deployment
└── requirements.txt         # Python dependencies
```

## Scripts Reference

| Script | Description |
|--------|-------------|
| `scripts/start.sh` | Start all backend services |
| `scripts/stop.sh` | Stop all services |
| `scripts/diagnose.py` | Check system health |
| `scripts/clear_db.py` | Clear event database |
| `scripts/check_confidence.py` | Inspect model confidence scores |
| `scripts/setup_models.sh` | Download ONNX models |
| `scripts/run_tests.sh` | Run test suite |

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — system design and pipeline flow
- [API Reference](docs/API_REFERENCE.md) — all backend endpoints
- [Threshold Tuning](docs/THRESHOLD_TUNING.md) — confidence threshold adjustment
- [ECS V2 Specification](docs/ECS_V2_SPECIFICATION.md) — event classification rules
- [Docker Deployment](docs/deployment_docker.md) — container setup
