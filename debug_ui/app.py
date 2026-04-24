"""
VisionGuard AI — Pipeline Debug Dashboard (Streamlit)

Real-time monitoring of the complete detection pipeline:
  Camera → Redis Queues → Workers → Results Stream → ECS → Database

Features:
  - Live detection gallery with bounding box images
  - Task queue monitoring
  - Results stream inspection
  - ECS v2 state overview
  - Database events with statistics

Run with: streamlit run debug_ui/app.py
"""

import streamlit as st
import redis
import sqlite3
import os
import time
import json
import glob
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# ───────── Configuration ─────────
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6380"))  # Docker maps 6379→6380 on host
DB_PATH = os.getenv("VG_DB_PATH", "/data/visionguard/events.db")

# Detection images directory — try Docker volume first, then host path
DETECTION_DIRS = [
    "/data/visionguard/detections",
    "/var/lib/docker/volumes/vg-app-data/_data/visionguard/detections",
    os.path.expanduser("~/data/visionguard/detections"),
]

# Redis queue names used by the pipeline
TASK_QUEUES = ["vg:critical", "vg:high", "vg:medium"]
RESULT_STREAM = "vg:ai:results"

# ───────── Page Config ─────────
st.set_page_config(
    page_title="VisionGuard Debug",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ───────── CSS ─────────
st.markdown("""
<style>
    /* Global dark theme override */
    .stApp {
        background-color: #0a0e17;
    }
    
    /* Metric cards */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 14px;
    }
    
    /* Detection card */
    .detection-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460;
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
        transition: transform 0.2s;
    }
    .detection-card:hover {
        transform: translateY(-2px);
        border-color: #e94560;
    }
    
    /* Status indicators */
    .status-healthy { color: #48bb78; font-weight: 600; }
    .status-warning { color: #ecc94b; font-weight: 600; }
    .status-error   { color: #fc8181; font-weight: 600; }
    
    /* Queue indicators */
    .queue-empty    { color: #48bb78; }
    .queue-low      { color: #ecc94b; }
    .queue-high     { color: #fc8181; }
    
    /* Badge styles */
    .badge-weapon {
        background: #e53e3e; color: white; padding: 2px 8px;
        border-radius: 4px; font-size: 0.75rem; font-weight: 700;
    }
    .badge-fire {
        background: #dd6b20; color: white; padding: 2px 8px;
        border-radius: 4px; font-size: 0.75rem; font-weight: 700;
    }
    .badge-fall {
        background: #3182ce; color: white; padding: 2px 8px;
        border-radius: 4px; font-size: 0.75rem; font-weight: 700;
    }
    
    /* Section headers */
    .section-header {
        border-bottom: 2px solid #0f3460;
        padding-bottom: 8px;
        margin-bottom: 16px;
    }
    
    /* Image gallery */
    .stImage > img {
        border-radius: 8px;
        border: 2px solid #0f3460;
    }
</style>
""", unsafe_allow_html=True)


# ───────── Helpers ─────────
@st.cache_resource
def get_redis():
    """Create Redis connection (cached)."""
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        r.ping()
        return r
    except Exception as e:
        return None


def get_db_connection():
    """Get SQLite connection — try multiple paths."""
    candidates = [
        DB_PATH,
        os.path.expanduser("~/data/visionguard/events.db"),
        "/var/lib/docker/volumes/vg-app-data/_data/visionguard/events.db",
    ]
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "volume", "inspect", "--format", "{{.Mountpoint}}",
             "vg-app-data"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            vol_path = result.stdout.strip()
            candidates.append(os.path.join(vol_path, "visionguard/events.db"))
    except Exception:
        pass
    
    for path in candidates:
        if os.path.exists(path):
            return sqlite3.connect(path)
    return None


def get_detection_dir():
    """Find detection images directory — tries local paths, then Docker volume."""
    # Try local paths first (works if mounted as bind mount)
    for d in DETECTION_DIRS:
        if os.path.isdir(d):
            return d
    
    # Try local cache directory (synced from Docker)
    local_cache = os.path.join(os.path.dirname(__file__), ".detection_cache")
    if os.path.isdir(local_cache):
        return local_cache
    
    # Try Docker volume inspect for direct access
    try:
        import subprocess
        result = subprocess.run(
            ["docker", "volume", "inspect", "--format", "{{.Mountpoint}}",
             "vg-app-data"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            vol_path = result.stdout.strip()
            det_path = os.path.join(vol_path, "visionguard/detections")
            if os.path.isdir(det_path):
                return det_path
    except Exception:
        pass
    return None


def sync_detection_images():
    """
    Sync detection images from Docker container to local cache.
    Uses docker cp to copy from worker container to host-readable path.
    Returns the local cache path if images were found.
    """
    import subprocess
    
    local_cache = os.path.join(os.path.dirname(__file__), ".detection_cache")
    os.makedirs(local_cache, exist_ok=True)
    
    # Try each worker container
    containers = ["vg-worker-weapon", "vg-worker-fire", "vg-worker-fall"]
    
    for container in containers:
        try:
            # Check if detections directory exists in container
            check = subprocess.run(
                ["docker", "exec", container, "ls", "/data/visionguard/detections/"],
                capture_output=True, text=True, timeout=5
            )
            if check.returncode != 0:
                continue
            
            # Get list of images in container
            files = check.stdout.strip().split("\n")
            jpg_files = [f for f in files if f.endswith('.jpg')]
            
            if not jpg_files:
                continue
            
            # Copy new images that don't exist locally
            existing = set(os.listdir(local_cache))
            for jpg in jpg_files:
                if jpg not in existing:
                    try:
                        subprocess.run(
                            ["docker", "cp",
                             f"{container}:/data/visionguard/detections/{jpg}",
                             os.path.join(local_cache, jpg)],
                            capture_output=True, timeout=5
                        )
                    except Exception:
                        pass
            
            # Cleanup old local files (keep last 60)
            all_local = sorted(
                [f for f in os.listdir(local_cache) if f.endswith('.jpg')],
                key=lambda f: os.path.getmtime(os.path.join(local_cache, f)),
                reverse=True
            )
            for old in all_local[60:]:
                try:
                    os.remove(os.path.join(local_cache, old))
                except Exception:
                    pass
                    
        except Exception:
            continue
    
    if os.listdir(local_cache):
        return local_cache
    return None


def get_detection_images(detection_dir, model_filter=None, limit=12):
    """Get most recent detection images."""
    if not detection_dir or not os.path.isdir(detection_dir):
        return []
    
    pattern = "*.jpg"
    if model_filter:
        pattern = f"{model_filter}_*.jpg"
    
    images = glob.glob(os.path.join(detection_dir, pattern))
    # Sort by modification time (newest first)
    images.sort(key=os.path.getmtime, reverse=True)
    return images[:limit]


def parse_detection_filename(filepath):
    """Parse model type, camera ID, and timestamp from filename."""
    name = os.path.basename(filepath)
    parts = name.replace('.jpg', '').split('_')
    if len(parts) >= 3:
        model = parts[0]
        camera = parts[1]
        try:
            ts_ms = int(parts[-1])
            ts = datetime.fromtimestamp(ts_ms / 1000)
            return model, camera, ts
        except (ValueError, OSError):
            pass
    return "unknown", "unknown", None


def format_ts(ts: float) -> str:
    """Format unix timestamp to readable string."""
    try:
        return datetime.fromtimestamp(ts).strftime("%H:%M:%S")
    except Exception:
        return "N/A"


def model_emoji(model_type: str) -> str:
    """Get emoji for model type."""
    return {"weapon": "🔫", "fire": "🔥", "fall": "🤸"}.get(model_type, "❓")


def clear_database() -> tuple[bool, str]:
    """Delete all rows from DB tables used during development/testing."""
    conn = get_db_connection()
    if not conn:
        return False, "Database not found"

    try:
        cursor = conn.cursor()
        tables = ["alerts", "event_evidence", "events"]
        deleted_total = 0

        for table in tables:
            try:
                cursor.execute(f"DELETE FROM {table}")
                deleted_total += max(cursor.rowcount, 0)
            except sqlite3.OperationalError:
                continue

        conn.commit()
        cursor.execute("VACUUM")
        conn.commit()
        return True, f"Database cleared (deleted {deleted_total} rows)"
    except Exception as e:
        return False, f"Failed to clear database: {e}"
    finally:
        conn.close()


def clear_detection_images() -> tuple[bool, str]:
    """Delete detection jpg files from host-visible paths and worker containers."""
    deleted_total = 0
    checked_locations = 0

    # Host-visible directories
    local_cache = os.path.join(os.path.dirname(__file__), ".detection_cache")
    candidate_dirs = set(DETECTION_DIRS + [local_cache])

    current_dir = get_detection_dir()
    if current_dir:
        candidate_dirs.add(current_dir)

    for d in sorted(candidate_dirs):
        if not d or not os.path.isdir(d):
            continue
        checked_locations += 1
        for img in glob.glob(os.path.join(d, "*.jpg")):
            try:
                os.remove(img)
                deleted_total += 1
            except Exception:
                pass

    # Container-side cleanup (for Docker volume paths not directly visible)
    for container in ["vg-worker-weapon", "vg-worker-fire", "vg-worker-fall"]:
        try:
            checked_locations += 1
            proc = subprocess.run(
                [
                    "docker", "exec", container, "sh", "-lc",
                    "count=$(find /data/visionguard/detections -maxdepth 1 -name '*.jpg' 2>/dev/null | wc -l); "
                    "find /data/visionguard/detections -maxdepth 1 -name '*.jpg' -delete 2>/dev/null; "
                    "echo $count"
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if proc.returncode == 0:
                out = proc.stdout.strip().splitlines()
                if out:
                    try:
                        deleted_total += int(out[-1])
                    except ValueError:
                        pass
        except Exception:
            continue

    if checked_locations == 0:
        return False, "No detection image locations found"
    return True, f"Detection images cleared (deleted {deleted_total} files)"


def clear_redis_queues_and_streams(rconn) -> tuple[bool, str]:
    """Clear pipeline queues/streams used in development."""
    if not rconn:
        return False, "Redis not connected"

    targets = [
        "vg:critical",
        "vg:high",
        "vg:medium",
        "vg:ai:results",
        "vg:clip:requests",
    ]

    removed = 0
    for key in targets:
        try:
            removed += rconn.delete(key)
        except Exception:
            pass

    return True, f"Queues/streams cleared (removed {removed} keys)"


# ───────── Sidebar ─────────
with st.sidebar:
    st.title("🛡️ VisionGuard Debug")
    st.markdown("---")
    refresh_rate = st.selectbox(
        "Auto-refresh (seconds)",
        [2, 5, 10, 30],
        index=1,
    )
    
    st.markdown("---")
    st.markdown("### Connections")
    
    r = get_redis()
    if r:
        st.markdown('<span class="status-healthy">● Redis Connected</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-error">● Redis Disconnected</span>', unsafe_allow_html=True)

    db = get_db_connection()
    if db:
        st.markdown('<span class="status-healthy">● Database Available</span>', unsafe_allow_html=True)
        db.close()
    else:
        st.markdown('<span class="status-error">● Database Not Found</span>', unsafe_allow_html=True)
    
    det_dir = get_detection_dir()
    if det_dir:
        img_count = len(glob.glob(os.path.join(det_dir, "*.jpg")))
        st.markdown(f'<span class="status-healthy">● Detection Images ({img_count})</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-warning">● No Detection Images Dir</span>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Configuration")
    st.markdown(f"**Redis:** `{REDIS_HOST}:{REDIS_PORT}`")
    st.markdown(f"**DB:** `{DB_PATH}`")
    if det_dir:
        st.markdown(f"**Images:** `{det_dir}`")
    
    st.markdown("---")
    st.markdown("### 🧪 Development Actions")
    st.caption("Destructive utilities for local development only")

    confirm_dev_actions = st.checkbox(
        "Enable destructive actions",
        value=False,
        help="Required to use clear/reset buttons below",
    )

    if st.button("🗑️ Clear Database", disabled=not confirm_dev_actions):
        ok, msg = clear_database()
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    if st.button("🧹 Clear Detection Images", disabled=not confirm_dev_actions):
        ok, msg = clear_detection_images()
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    if st.button("📭 Clear Queues/Streams", disabled=not confirm_dev_actions):
        ok, msg = clear_redis_queues_and_streams(r)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    st.markdown("---")
    if st.button("🔄 Force Refresh"):
        st.cache_resource.clear()
        st.rerun()


# ───────── Main Header ─────────
st.title("🛡️ VisionGuard AI — Pipeline Debug Dashboard")
st.caption(f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  •  Auto-refresh every {refresh_rate}s")

# ═══════════════════════════════════════════════════════════
# SECTION 1: LIVE DETECTION GALLERY (NEW — Most Important)
# ═══════════════════════════════════════════════════════════
st.markdown("## 📸 Live Detection Gallery")

# Sync detection images from Docker containers to local cache
sync_detection_images()
det_dir = get_detection_dir()

if det_dir:
    # Filter controls
    filter_col1, filter_col2 = st.columns([1, 3])
    with filter_col1:
        model_filter = st.selectbox(
            "Filter by model",
            ["all", "weapon", "fire", "fall"],
            index=0,
            key="gallery_filter"
        )
    
    # Get detection images
    filter_val = None if model_filter == "all" else model_filter
    images = get_detection_images(det_dir, model_filter=filter_val, limit=12)
    
    if images:
        # Display in a grid — 3 columns for larger images
        cols_per_row = 3
        for row_start in range(0, len(images), cols_per_row):
            cols = st.columns(cols_per_row)
            for col_idx, img_path in enumerate(images[row_start:row_start + cols_per_row]):
                model, camera, ts = parse_detection_filename(img_path)
                with cols[col_idx]:
                    # Show image
                    st.image(
                        img_path,
                        use_container_width=True,
                    )
                    # Show metadata below image
                    emoji = model_emoji(model)
                    ts_str = ts.strftime("%H:%M:%S") if ts else "N/A"
                    st.markdown(
                        f"**{emoji} {model.upper()}** • cam: `{camera}` • {ts_str}"
                    )
    else:
        st.info("📭 No detection images yet — detections will appear here with bounding boxes when they occur.")
else:
    st.warning("Detection images directory not found. Images will appear after workers detect objects and save annotated frames.")

# ═══════════════════════════════════════════════════════════
# SECTION 2: PIPELINE STATUS
# ═══════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 📊 Pipeline Status")

st.markdown("""
```
Camera → [vg:critical / vg:high / vg:medium] → Workers → [vg:ai:results] → ECS → Database
```
""")

# ───── Task Queues ─────
st.markdown("### 📥 Task Queues")

if r:
    col1, col2, col3, col4 = st.columns(4)
    queue_lengths = {}
    total_queued = 0
    for q in TASK_QUEUES:
        try:
            l = r.llen(q)
        except Exception:
            l = -1
        queue_lengths[q] = l
        if l > 0:
            total_queued += l

    with col1:
        st.metric("🔴 Weapon Stream (vg:critical)", queue_lengths.get("vg:critical", 0), help="Weapon frames waiting for worker processing")
    with col2:
        st.metric("🟡 Fire Stream (vg:high)", queue_lengths.get("vg:high", 0), help="Fire/smoke frames waiting for worker processing")
    with col3:
        st.metric("🟢 Fall Stream (vg:medium)", queue_lengths.get("vg:medium", 0), help="Fall frames waiting for worker processing")
    with col4:
        st.metric("📦 Total Frame Backlog", total_queued, help="Sum of frames currently buffered in Redis")

    if total_queued > 100:
        st.warning(f"⚠️ {total_queued} frames queued — Workers are suffering high inference latency and falling behind the camera FPS!")
    elif total_queued == 0:
        st.success("✅ Real-time processing — Workers are matching Camera FPS with zero latency backlog.")
    else:
        st.info(f"ℹ️ {total_queued} frames in pipeline buffer being actively processed...")
else:
    st.error("Cannot connect to Redis")

# ───── Results Stream ─────
st.markdown("### 📤 Results Stream")

if r:
    col1, col2, col3 = st.columns(3)
    try:
        stream_len = r.xlen(RESULT_STREAM)
    except Exception:
        stream_len = -1

    try:
        stream_info = r.xinfo_stream(RESULT_STREAM)
        last_entry = stream_info.get("last-entry")
        last_id = stream_info.get("last-generated-id", "N/A")
    except Exception:
        last_entry = None
        last_id = "N/A"

    with col1:
        st.metric("Stream Length", stream_len)
    with col2:
        st.metric("Last ID", last_id)
    with col3:
        if last_entry:
            try:
                entry_id = last_entry[0] if isinstance(last_entry, (list, tuple)) else str(last_entry)
                ts_ms = int(str(entry_id).split("-")[0])
                age_s = (time.time() * 1000 - ts_ms) / 1000
                st.metric("Last Message Age", f"{age_s:.1f}s ago")
            except Exception:
                st.metric("Last Message Age", "N/A")
        else:
            st.metric("Last Message Age", "No messages")

    # Show recent stream messages with detection_image indicator
    if stream_len and stream_len > 0:
        with st.expander(f"📋 Recent Stream Messages (last 10)", expanded=False):
            try:
                recent = r.xrevrange(RESULT_STREAM, count=10)
                for msg_id, data in recent:
                    camera = data.get("camera_id", "?")
                    model = data.get("model_type", data.get("model", "?"))
                    conf = data.get("confidence", "?")
                    has_img = "📸" if data.get("detection_image") else "  "
                    st.text(f"  {has_img} [{msg_id}] model={model} conf={conf} camera={camera}")
            except Exception as e:
                st.error(f"Error reading stream: {e}")

# ═══════════════════════════════════════════════════════════
# SECTION 3: ECS STATE
# ═══════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 🧠 ECS v2 State")

if r:
    col1, col2, col3 = st.columns(3)
    try:
        stream_len = r.xlen(RESULT_STREAM)
        with col1:
            if stream_len == 0:
                st.metric("Processing", "Idle")
                st.success("No pending messages")
            elif stream_len < 50:
                st.metric("Processing", "Active")
                st.info(f"{stream_len} messages")
            else:
                st.metric("Processing", "Backlogged")
                st.warning(f"{stream_len} unprocessed")
    except Exception:
        with col1:
            st.metric("Processing", "Unknown")

    with col2:
        st.metric("Correlation Window", "2000ms")
    with col3:
        st.metric("Hard TTL", "15.0s")

    with st.expander("⏱️ ECS v2 Configuration", expanded=False):
        ecol1, ecol2, ecol3 = st.columns(3)
        with ecol1:
            st.markdown("**🔫 Weapon**")
            st.text("  Threshold: 0.60")
            st.text("  Cooldown:  30s")
        with ecol2:
            st.markdown("**🔥 Fire**")
            st.text("  Threshold: 0.45")
            st.text("  Cooldown:  60s")
            st.text("  Min detections: 3")
            st.text("  Window: 8.0s")
        with ecol3:
            st.markdown("**🤸 Fall**")
            st.text("  Threshold: 0.75")
            st.text("  Cooldown:  30s")

# ═══════════════════════════════════════════════════════════
# SECTION 4: DATABASE EVENTS
# ═══════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 💾 Database Events")

db = get_db_connection()
if db:
    try:
        cursor = db.cursor()

        # Total counts
        total = cursor.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        by_type = cursor.execute(
            "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"
        ).fetchall()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Events", total)
        type_counts = {r[0]: r[1] for r in by_type}
        with col2:
            st.metric("🔫 Weapon", type_counts.get("weapon_detected", 0))
        with col3:
            st.metric("🔥 Fire", type_counts.get("fire_detected", 0))
        with col4:
            st.metric("🤸 Fall", type_counts.get("fall_detected", 0))

        # Recent events table
        recent_events = cursor.execute("""
            SELECT event_type, confidence, camera_id, 
                   datetime(created_at, 'unixepoch', 'localtime') as time,
                   model_version
            FROM events 
            ORDER BY created_at DESC 
            LIMIT 20
        """).fetchall()

        if recent_events:
            st.markdown("### Recent Events (last 20)")
            st.dataframe(
                [
                    {
                        "Type": e[0],
                        "Confidence": f"{e[1]:.3f}" if e[1] else "N/A",
                        "Camera": e[2],
                        "Time": e[3],
                        "Model": e[4] if len(e) > 4 else "N/A",
                    }
                    for e in recent_events
                ],
                use_container_width=True,
            )
        else:
            st.info("No events in database — clean slate ✅")

        # Event statistics
        try:
            rate_query = cursor.execute("""
                SELECT event_type,
                       COUNT(*) as count,
                       MIN(confidence) as min_conf,
                       MAX(confidence) as max_conf,
                       AVG(confidence) as avg_conf
                FROM events 
                GROUP BY event_type
            """).fetchall()

            if rate_query:
                st.markdown("### Event Statistics")
                st.dataframe(
                    [
                        {
                            "Type": r[0],
                            "Count": r[1],
                            "Min Conf": f"{r[2]:.3f}" if r[2] else "N/A",
                            "Max Conf": f"{r[3]:.3f}" if r[3] else "N/A",
                            "Avg Conf": f"{r[4]:.3f}" if r[4] else "N/A",
                        }
                        for r in rate_query
                    ],
                    use_container_width=True,
                )
        except Exception:
            pass

        # Duplicate detection
        with st.expander("🔍 Duplicate Event Detection", expanded=False):
            try:
                dupes = cursor.execute("""
                    SELECT 
                        e1.event_type,
                        ROUND(e1.confidence, 3) as conf,
                        e1.camera_id,
                        datetime(e1.created_at, 'unixepoch', 'localtime'),
                        datetime(e2.created_at, 'unixepoch', 'localtime'),
                        ROUND(e2.created_at - e1.created_at, 1) as gap_s
                    FROM events e1
                    JOIN events e2 ON (
                        e1.event_type = e2.event_type AND
                        e1.camera_id = e2.camera_id AND
                        ABS(e1.confidence - e2.confidence) < 0.001 AND
                        e2.created_at > e1.created_at AND
                        (e2.created_at - e1.created_at) < 5.0
                    )
                    ORDER BY e1.created_at DESC
                    LIMIT 20
                """).fetchall()

                if dupes:
                    st.warning(f"⚠️ {len(dupes)} potential duplicate pairs found")
                    st.dataframe(
                        [
                            {
                                "Type": d[0],
                                "Confidence": d[1],
                                "Camera": d[2],
                                "Event 1": d[3],
                                "Event 2": d[4],
                                "Gap (s)": d[5],
                            }
                            for d in dupes
                        ],
                        use_container_width=True,
                    )
                else:
                    st.success("✅ No duplicates — ECS v2 cooldown working")
            except Exception as e:
                st.error(f"Error checking duplicates: {e}")

        db.close()
    except Exception as e:
        st.error(f"Database error: {e}")
        db.close()
else:
    st.warning("Database not found — set VG_DB_PATH if running outside Docker")

# ═══════════════════════════════════════════════════════════
# SECTION 5: REDIS KEYS
# ═══════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 🗝️ Redis Keys")

if r:
    with st.expander("All Redis Keys", expanded=False):
        try:
            keys = r.keys("vg:*")
            if keys:
                for key in sorted(keys):
                    key_type = r.type(key)
                    if key_type == "list":
                        length = r.llen(key)
                        st.text(f"  {key} (list, len={length})")
                    elif key_type == "stream":
                        length = r.xlen(key)
                        st.text(f"  {key} (stream, len={length})")
                    elif key_type == "string":
                        st.text(f"  {key} (string)")
                    elif key_type == "hash":
                        length = r.hlen(key)
                        st.text(f"  {key} (hash, fields={length})")
                    elif key_type == "set":
                        length = r.scard(key)
                        st.text(f"  {key} (set, members={length})")
                    else:
                        st.text(f"  {key} ({key_type})")
            else:
                st.info("No vg:* keys found in Redis")
        except Exception as e:
            st.error(f"Error listing keys: {e}")

# ───────── Footer ─────────
st.markdown("---")
st.caption("VisionGuard AI — Pipeline Debug Dashboard v2.0 • Detection images with bounding boxes")

# ───────── Auto-refresh ─────────
time.sleep(refresh_rate)
st.rerun()
