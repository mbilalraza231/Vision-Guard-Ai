# Debug UI Overhaul - Intuitive and Information-Rich

## Current State
The debug UI has 5 sections (Gallery, Pipeline, ECS, Database, Redis Keys) but is sparse and doesn't show many valuable metrics that are available in Redis/PostgreSQL. The gallery takes up prime real estate but is often empty.

## Available Data (confirmed from Redis)
- `vg:metrics:{service}:{id}` - JSON with cpu_percent, memory_gb, timestamp (8 services)
- `vg:metrics:camera:{id}:fps` - camera actual FPS (string, 15s TTL, present when active)
- `vg:system_settings` - full JSON with all runtime settings (thresholds, ECS config, etc.)
- `vg:ai:results` stream - each message has: camera_id, model, confidence, inference_latency_ms, bbox, timestamp
- `vg:events:finalized` stream - event_id, event_type, camera_id, confidence, severity, timestamp
- Redis INFO - memory usage, connected clients, key counts
- PostgreSQL - events (27), alerts (20) with type/confidence/status/timestamp

## New Layout (Pipeline Flow: Input -> Processing -> Output)

### Sidebar (keep mostly as-is)
- Connections (Redis, PostgreSQL, Detection Images)
- Configuration (Redis, PostgreSQL, version)
- Read-Only Mode badge
- Force Refresh button
- Auto-refresh selector

### Section 1: System Health Overview (NEW)
- 8 service cards in a grid (camera, weapon-worker, fire-worker, fall-worker, ECS, clip-recorder, alert-worker, backend)
- Each card shows: service name, status (healthy/stale based on timestamp age), CPU%, memory GB, last heartbeat age
- Stale = heartbeat older than 30s (shown in yellow/red)
- Data source: `vg:metrics:*` keys

### Section 2: Camera Capture (NEW)
- Camera actual FPS from `vg:metrics:camera:{id}:fps` keys (scan with pattern)
- Settings from `vg:system_settings` JSON: default FPS, motion threshold, global FPS target
- Total capture FPS (sum of all camera FPS)
- Show "No cameras active" if FPS keys expired

### Section 3: Task Queues (improved)
- Keep existing 4-column metrics (weapon/fire/fall/total)
- Add: Queue TTL from system settings
- Add: Max queue size from system settings
- Keep the backlog status message

### Section 4: AI Worker Throughput (NEW - replaces sparse Results Stream)
- Total throughput (results/s) - already implemented
- Per-model breakdown with rate + percentage - already implemented
- **NEW: Per-model average inference latency** (extracted from `inference_latency_ms` field in last 60 stream messages)
- **NEW: Confidence distribution** per model (min/max/avg from last 60 messages)
- **NEW: Results stream stats** (length, maxlen, last message age)

### Section 5: ECS Event Brain (improved)
- Keep: Processing state (Idle/Active/Backlogged), pending count
- Keep: Correlation Window, Hard TTL
- **NEW: Event generation rate** from `vg:events:finalized` stream (messages per minute over last 60)
- **NEW: ECS config panel** extracted from LIVE `vg:system_settings` Redis key (not hardcoded values):
  - Weapon: threshold, min_detections, window, cooldown
  - Fire: threshold, min_detections, window, cooldown
  - Fall: threshold, min_detections, window, cooldown
- **NEW: Recent finalized events** (last 10 from `vg:events:finalized` stream with type, confidence, severity, camera, age)

### Section 6: Database (improved)
- Keep: Total events, per-type counts, recent events table
- Keep: Event statistics (min/max/avg confidence)
- Keep: Duplicate detection
- **NEW: Alerts summary** (total, by status: pending/dispatched/resolved)
- **NEW: Event timeline** (events per hour over last 24h, as text-based bar chart)

### Section 7: Redis Resources (NEW)
- Memory used (from Redis INFO memory)
- Connected clients (from Redis INFO clients)
- Total key count (from Redis INFO keyspace)
- Key type breakdown table (streams, sorted sets, strings, hashes)
- Move "All Redis keys" expander here

### Section 8: Live Detection Gallery (moved to bottom)
- Keep existing functionality but move to bottom since it's often empty
- Keep filter controls

## Task 1: Rewrite debug_ui/app.py
Single file rewrite of `d:\Vision Guard Ai ( Anti gravity)\debug_ui\app.py` (~693 lines currently, estimated ~900 lines after changes).

Key implementation details:
- New helper: `get_service_metrics(r)` - reads all `vg:metrics:*` keys, returns dict of service -> {cpu, memory, timestamp, age_s}
- New helper: `get_camera_fps(r)` - scans `vg:metrics:camera:*:fps` keys, returns dict of camera_id -> fps
- New helper: `get_system_settings(r)` - reads `vg:system_settings` JSON key
- New helper: `get_redis_info(r)` - runs INFO command and extracts memory/clients/keys
- Modified helper: `get_worker_throughput(r)` - expanded to also return per-model avg latency and confidence stats
- New section functions: `render_system_health()`, `render_camera_capture()`, `render_worker_throughput()`, `render_ecs_state()`, `render_database()`, `render_redis_resources()`

## Task 2: Rebuild and verify
- `docker compose --profile debug up -d --build debug-ui`
- Verify all sections render correctly
- Take screenshots to confirm layout
