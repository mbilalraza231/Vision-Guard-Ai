# VisionGuard AI

Real-time AI surveillance system that detects fire, weapons, and fallen persons from video feeds using CPU-based ONNX inference. Events are stored in PostgreSQL and delivered via a high-performance, real-time notification pipeline.

## Architecture Diagram

Below is the definitive data flow and service architecture of the VisionGuard AI system:

```text
+----------------+      +-------------------+      +----------------+
|  Camera Stream | ---> |  Camera Capture   | ---> | Shared Memory  |
|  (RTSP/Local)  |      |  Service (Frames) |      | (/dev/shm)     |
+----------------+      +-------------------+      +----------------+
                                 |                         |
                                 v                         v
                        +-------------------+      +----------------+
                        | Redis Message Bus | <--- |   AI Workers   |
                        | (Raw AI Results)  |      | (Weapon/Fire)  |
                        +-------------------+      +----------------+
                                 |
                        +-------------------+
                        |       ECS         |  (Event Classification)
                        | (Logic Engine)    |
                        +-------------------+
                                 |
                        +-------------------+
                        | Redis Message Bus |  (Requests & Alerts)
                        | (Task Stream)     |
                        +-------------------+
                                 |
           +---------------------+---------------------+
           |                     |                     |
           v                     v                     v
+-------------------+  +-------------------+  +-------------------+
|  PostgreSQL DB    |  |   Clip Recorder   |  |   Alert Worker    |
|  (Event/Alerts)   |  |  (Local/Cloud)    |  | (Twilio/Gmail)    |
+-------------------+  +-------------------+  +-------------------+
           |                     |                     |
           v                     v                     v
+-------------------+  +-------------------+  +-------------------+
|  FastAPI Backend  |  |   Cloudinary      |  |   Supabase Auth   |
|  (Control Plane)  |  |  (Media CDN)      |  |  (User Profiles)  |
+-------------------+  +-------------------+  +-------------------+
           |                     |                     |
           +---------------------+---------------------+
                                 |
                                 v
                        +-------------------+
                        |  Web Dashboard    |
                        | (React / Vite)    |
                        +-------------------+
```

## System Features

- **Multi-Worker AI Inference**: Parallelized workers for Fire, Weapon, and Fall detection using ONNX.
- **Hierarchical Storage**: PostgreSQL for event metadata; Cloudinary for global media evidence delivery.
- **Secure Authentication**: Integrated with Supabase Auth for robust user management and profile synchronization.
- **Enterprise Notification Engine**: Premium HTML emails (Gmail SMTP) and WhatsApp/SMS integration (Twilio).
- **Latency-Aware Foreground Recording**: Uses ring-buffer technology to capture forensic clips including seconds *before* the detection.
- **Smart Dashboard**: Real-time management of camera zones, alert contacts, and forensic review.

## Quick Start

1. **Environment**: Configure `.env` with Twilio, Gmail, Cloudinary, and Supabase credentials.
2. **Launch**: Deploy the full stack with `docker-compose up -d --build`.
3. **Access**:
   - **Dashboard**: `http://localhost:5173`
   - **API Docs**: `http://localhost:8000/docs`
4. **Operation**: Add alert recipients in the "Alert Contacts" page to start receiving notifications.

## Project Structure

```
├── camera_capture/          # Video capture + motion detection
├── ai_worker/               # ONNX inference workers (fire/weapon/fall)
├── event_classification/    # Event classification service (ECS)
├── backend/                 # FastAPI control plane + REST API
├── visionguard-dashboard-29/  # React dashboard (TypeScript + Vite)
├── db/                      # PostgreSQL schema + initialization
├── alerts/                  # Alert dispatch engine (Twilio/Gmail)
├── clip_recorder/           # H.264 transcoding + Cloudinary uploader
├── docker-compose.yml       # Production-ready container orchestration
└── .env                     # System secrets and configurations
```
