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
import os
import time
import json
import glob
from datetime import datetime, timedelta
from pathlib import Path

# ───────── Configuration ─────────
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
# Docker maps 6379→6380 on host
REDIS_PORT = int(os.getenv("REDIS_PORT", "6380"))
# PostgreSQL connection (read-only debug access)
PG_HOST = os.getenv("VG_POSTGRES_HOST", "localhost")
PG_USER = os.getenv("VG_POSTGRES_USER", "postgres")
PG_DB = os.getenv("VG_POSTGRES_DB", "visionguard")

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
    """Get PostgreSQL connection."""
    host = os.environ.get("VG_POSTGRES_HOST", "localhost")
    user = os.environ.get("VG_POSTGRES_USER", "postgres")
    db_name = os.environ.get("VG_POSTGRES_DB", "visionguard")
    password = os.environ.get("VG_POSTGRES_PASSWORD", "postgres")

    try:
        import psycopg2
        return psycopg2.connect(
            host=host,
            user=user,
            password=password,
            dbname=db_name,
            connect_timeout=3
        )
    except Exception:
        return None


def get_detection_dir():
    """Find detection images directory from shared volume paths."""
    for d in DETECTION_DIRS:
        if os.path.isdir(d):
            return d

    # Try local cache directory
    local_cache = os.path.join(os.path.dirname(__file__), ".detection_cache")
    if os.path.isdir(local_cache):
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
        st.markdown(
            '<span class="status-healthy">● Redis Connected</span>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<span class="status-error">● Redis Disconnected</span>', unsafe_allow_html=True)

    db = get_db_connection()
    if db:
        st.markdown(
            '<span class="status-healthy">● Database Available</span>', unsafe_allow_html=True)
        db.close()
    else:
        st.markdown(
            '<span class="status-error">● Database Not Found</span>', unsafe_allow_html=True)

    det_dir = get_detection_dir()
    if det_dir:
        img_count = len(glob.glob(os.path.join(det_dir, "*.jpg")))
        st.markdown(
            f'<span class="status-healthy">● Detection Images ({img_count})</span>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<span class="status-warning">● No Detection Images Dir</span>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Configuration")
    st.markdown(f"**Redis:** `{REDIS_HOST}:{REDIS_PORT}`")
    st.markdown(f"**PostgreSQL:** `{PG_USER}@{PG_HOST}/{PG_DB}`")
    if det_dir:
        st.markdown(f"**Images:** `{det_dir}`")

    st.markdown("---")
    st.markdown("### 🔒 Read-Only Mode")
    st.caption(
        "This dashboard only READS from Redis and PostgreSQL. No destructive actions available.")

    st.markdown("---")
    if st.button("🔄 Force Refresh"):
        st.cache_resource.clear()
        st.rerun()


# ───────── Main Header ─────────
st.title("🛡️ VisionGuard AI — Pipeline Debug Dashboard")
st.caption(
    f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  •  Auto-refresh every {refresh_rate}s")

# ═══════════════════════════════════════════════════════════
# SECTION 1: LIVE DETECTION GALLERY (NEW — Most Important)
# ═══════════════════════════════════════════════════════════
st.markdown("## 📸 Live Detection Gallery")

# Get detection images directory
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
        st.info(
            "📭 No detection images yet — detections will appear here with bounding boxes when they occur.")
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
            l = r.zcard(q)  # Sorted sets, not lists
        except Exception:
            l = -1
        queue_lengths[q] = l
        if l > 0:
            total_queued += l

    with col1:
        st.metric("🔴 Weapon Stream (vg:critical)", queue_lengths.get(
            "vg:critical", 0), help="Weapon frames waiting for worker processing")
    with col2:
        st.metric("🟡 Fire Stream (vg:high)", queue_lengths.get(
            "vg:high", 0), help="Fire/smoke frames waiting for worker processing")
    with col3:
        st.metric("🟢 Fall Stream (vg:medium)", queue_lengths.get(
            "vg:medium", 0), help="Fall frames waiting for worker processing")
    with col4:
        st.metric("📦 Total Frame Backlog", total_queued,
                  help="Sum of frames currently buffered in Redis")

    if total_queued > 100:
        st.warning(
            f"⚠️ {total_queued} frames queued — Workers are suffering high inference latency and falling behind the camera FPS!")
    elif total_queued == 0:
        st.success(
            "✅ Real-time processing — Workers are matching Camera FPS with zero latency backlog.")
    else:
        st.info(
            f"ℹ️ {total_queued} frames in pipeline buffer being actively processed...")
else:
    st.error("Cannot connect to Redis")

# ───── Results Stream ─────
st.markdown("### 📤 Results Stream")

if r:
    col1, col2, col3, col4 = st.columns(4)
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

    # Calculate throughput: look at last 60 messages, measure time span
    throughput = None
    try:
        sample = r.xrevrange(RESULT_STREAM, count=60)
        if len(sample) >= 2:
            newest_ms = int(str(sample[0][0]).split("-")[0])
            oldest_ms = int(str(sample[-1][0]).split("-")[0])
            span_s = (newest_ms - oldest_ms) / 1000.0
            if span_s > 0:
                throughput = len(sample) / span_s
    except Exception:
        pass

    with col1:
        st.metric("Stream Length", stream_len)
    with col2:
        st.metric("Last ID", last_id)
    with col3:
        if last_entry:
            try:
                entry_id = last_entry[0] if isinstance(
                    last_entry, (list, tuple)) else str(last_entry)
                ts_ms = int(str(entry_id).split("-")[0])
                age_s = (time.time() * 1000 - ts_ms) / 1000
                st.metric("Last Message Age", f"{age_s:.1f}s ago")
            except Exception:
                st.metric("Last Message Age", "N/A")
        else:
            st.metric("Last Message Age", "No messages")
    with col4:
        if throughput is not None:
            st.metric("Worker Throughput", f"{throughput:.1f} results/s",
                      help="AI inference results per second (all models combined, measured over last 60 messages)")
        else:
            st.metric("Worker Throughput", "N/A")

    # Per-model breakdown
    if stream_len and stream_len > 0:
        with st.expander(f"📋 Recent Stream Messages (last 10) + Per-Model Throughput", expanded=False):
            try:
                recent = r.xrevrange(RESULT_STREAM, count=10)
                for msg_id, data in recent:
                    camera = data.get("camera_id", "?")
                    model = data.get("model_type", data.get("model", "?"))
                    conf = data.get("confidence", "?")
                    has_img = "📸" if data.get("detection_image") else "  "
                    st.text(
                        f"  {has_img} [{msg_id}] model={model} conf={conf} camera={camera}")
            except Exception as e:
                st.error(f"Error reading stream: {e}")

            # Per-model breakdown from the throughput sample
            if throughput is not None:
                st.markdown("**Per-model rate** (from last 60 results):")
                model_counts = {}
                try:
                    sample2 = r.xrevrange(RESULT_STREAM, count=60)
                    for _, data in sample2:
                        m = data.get("model_type", data.get(
                            "model", "unknown"))
                        model_counts[m] = model_counts.get(m, 0) + 1
                    total = sum(model_counts.values())
                    for m, cnt in sorted(model_counts.items()):
                        pct = cnt / total * 100
                        rate = throughput * cnt / total
                        st.text(f"  {m}: {rate:.1f}/s ({pct:.0f}%)")
                except Exception:
                    pass

# ═══════════════════════════════════════════════════════════
# SECTION 3: ECS STATE
# ═══════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 🧠 ECS v2 State")

if r:
    col1, col2, col3 = st.columns(3)
    try:
        stream_len = r.xlen(RESULT_STREAM)
        ecs_last_id = r.get("vg:ecs:last_id")

        # Calculate real backlog
        # If last_id exists, we count how many messages are AFTER it
        pending_count = 0
        if ecs_last_id and ecs_last_id != "0-0":
            try:
                # XCOUNT gives us messages in a range.
                # Range is (ecs_last_id to + (the end)
                # The "(" makes it "exclusive" (messages strictly after the ID)
                pending_count = r.xcount(RESULT_STREAM, f"({ecs_last_id}", "+")
            except Exception:
                pending_count = 0
        else:
            # If no ID, everything is pending
            pending_count = stream_len

        with col1:
            if pending_count == 0:
                st.metric("Processing", "Idle")
                st.success("Brain is caught up! ✅")
            elif pending_count < 50:
                st.metric("Processing", "Active")
                st.info(f"{pending_count} pending")
            else:
                st.metric("Processing", "Backlogged")
                st.warning(f"{pending_count} unprocessed")

            st.caption(f"Stream: {stream_len} | Pending: {pending_count}")
    except Exception as e:
        with col1:
            st.metric("Processing", "Unknown")
            st.caption(f"Error: {e}")

    with col2:
        st.metric("Correlation Window", "400ms")
    with col3:
        st.metric("Hard TTL", "2.0s")

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
        cursor.execute("SELECT COUNT(*) FROM events")
        total = cursor.fetchone()[0]
        cursor.execute(
            "SELECT event_type, COUNT(*) FROM events GROUP BY event_type"
        )
        by_type = cursor.fetchall()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Events", total)
        type_counts = {r[0]: r[1] for r in by_type}
        with col2:
            weapon_count = type_counts.get(
                "weapon_detected", 0) + type_counts.get("weapon", 0)
            st.metric("🔫 Weapon", weapon_count)
        with col3:
            fire_count = type_counts.get(
                "fire_detected", 0) + type_counts.get("fire", 0)
            st.metric("🔥 Fire", fire_count)
        with col4:
            fall_count = type_counts.get(
                "fall_detected", 0) + type_counts.get("fall", 0)
            st.metric("🤸 Fall", fall_count)

        # Recent events table
        cursor.execute("""
            SELECT event_type, confidence, camera_id, 
                   to_timestamp(created_at) as time,
                   model_version
            FROM events 
            ORDER BY created_at DESC 
            LIMIT 20
        """)
        recent_events = cursor.fetchall()

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
            cursor.execute("""
                SELECT event_type,
                       COUNT(*) as count,
                       MIN(confidence) as min_conf,
                       MAX(confidence) as max_conf,
                       AVG(confidence) as avg_conf
                FROM events 
                GROUP BY event_type
            """)
            rate_query = cursor.fetchall()

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
                cursor.execute("""
                    SELECT 
                        e1.event_type,
                        ROUND(e1.confidence, 3) as conf,
                        e1.camera_id,
                        to_timestamp(e1.created_at) as event1_time,
                        to_timestamp(e2.created_at) as event2_time,
                        ROUND((e2.created_at - e1.created_at)::numeric, 1) as gap_s
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
                """)
                dupes = cursor.fetchall()

                if dupes:
                    st.warning(
                        f"⚠️ {len(dupes)} potential duplicate pairs found")
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
    st.warning("Database not available — check PostgreSQL connection")

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
                    elif key_type == "zset":
                        length = r.zcard(key)
                        st.text(f"  {key} (sorted set, len={length})")
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
st.caption(
    "VisionGuard AI — Pipeline Debug Dashboard v2.0 • Detection images with bounding boxes")

# ───────── Auto-refresh ─────────
time.sleep(refresh_rate)
st.rerun()
