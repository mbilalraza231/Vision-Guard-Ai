# VisionGuard AI

Real-time AI surveillance system that detects fire, weapons, and fallen persons from video feeds using CPU-based ONNX inference. Events are stored in PostgreSQL and delivered via a real-time notification pipeline.

## Architecture Diagram

Below is the enterprise data flow of the VisionGuard AI system:

```text
+----------------+      +-------------------+      +----------------+
|  Camera Stream | ---> |  Camera Capture   | ---> | Shared Memory  |
|  (RTSP/Local)  |      |  Service (Frames) |      | (RAM Storage)  |
+----------------+      +-------------------+      +----------------+
                                 |                         |
                                 v                         v
                        +-------------------+      +----------------+
                        | Redis Message Bus | <--- |   AI Workers   |
                        | (Stream / Queue)  |      | (Weapon/Fire)  |
                        +-------------------+      +----------------+
                                 |
           +---------------------+---------------------+
           |                     |                     |
           v                     v                     v
+-------------------+  +-------------------+  +-------------------+
|       ECS         |  |   Clip Recorder   |  |   Alert Worker    |
| (Event Filter)    |  | (Local + Cloud)   |  | (Twilio + Gmail)  |
+-------------------+  +-------------------+  +-------------------+
           |                     |                     |
           +----------+----------+----------+----------+
                      |                    |
                      v                    v
            +-------------------+   +-------------------+
            | PostgreSQL DB     |   | Cloudinary        |
            | (Persistence)     |   | (Evidence Storage)|
            +-------------------+   +-------------------+
                      |
                      v
            +-------------------+   +-------------------+
            | FastAPI Backend   |   |  Web Dashboard    |
            | (Control Plane)   | < | (React / Vite)    |
            +-------------------+   +-------------------+
```

## System Features

- **Multi-Worker AI**: Dedicated workers for Fire, Weapon, and Fall detection.
- **Hybrid Storage**: PostgreSQL for structured data; Cloudinary for media evidence storage.
- **Real-time Notifications**: Premium HTML emails (Gmail) and WhatsApp alerts (Twilio) with working evidence links.
- **Latency-Aware Recording**: High-fidelity post-event clips captured using ring-buffer technology.
- **Enterprise Dashboard**: Modern React interface for CRUD management of alert contacts and forensic incident review.

## System Requirements

- Python 3.10+
- Redis 6+
- PostgreSQL 15+
- Node.js 18+ (for dashboard)

## Quick Start

1. **Configuration**: Set your credentials in `.env` (Twilio, Gmail, Cloudinary, PostgreSQL).
2. **Deploy**: Run `docker-compose up -d --build` to start the full containerized stack.
3. **Dashboard**: Navigate to `http://localhost:5173` to manage alert recipients.
4. **Monitor**: Watch live logs with `docker-compose logs -f alert-worker`.

## Project Structure

```
├── camera_capture/          # Video capture + motion detection
├── ai_worker/               # ONNX inference workers (fire/weapon/fall)
├── event_classification/    # Event classification service (ECS)
├── backend/                 # FastAPI control plane + REST API
├── visionguard-dashboard-29/  # React dashboard (TypeScript + Tailwind)
├── db/                      # PostgreSQL schema + initialization
├── alerts/                  # Alert dispatch engine (Twilio/Gmail)
├── clip_recorder/           # H.264 transcoding + Cloudinary uploader
├── docker-compose.yml       # Full stack deployment
└── .env                     # Environment configuration (secrets)
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — system design and pipeline flow
- [API Reference](docs/API_REFERENCE.md) — all backend endpoints
- [Threshold Tuning](docs/THRESHOLD_TUNING.md) — confidence threshold adjustment
- [Docker Deployment](docs/deployment_docker.md) — container setup
