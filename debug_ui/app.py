"""
VisionGuard AI — Pipeline Debug Dashboard v3.0 (Streamlit)

Real-time monitoring of the complete detection pipeline:
  Camera → Redis Queues → AI Workers → Results Stream → ECS → Database

Organized by pipeline flow (Input → Processing → Output).
Read-only: no writes to Redis or PostgreSQL.

Run with: streamlit run debug_ui/app.py
"""

import streamlit as st
import redis
import os
import time
import json
import glob
from datetime import datetime

# ───────── Configuration ─────────
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6380"))
PG_HOST = os.getenv("VG_POSTGRES_HOST", "localhost")
PG_USER = os.getenv("VG_POSTGRES_USER", "postgres")
PG_DB = os.getenv("VG_POSTGRES_DB", "visionguard")

DETECTION_DIRS = [
    "/data/visionguard/detections",
    "/var/lib/docker/volumes/vg-app-data/_data/visionguard/detections",
    os.path.expanduser("~/data/visionguard/detections"),
]

TASK_QUEUES = ["vg:critical", "vg:high", "vg:medium"]
RESULT_STREAM = "vg:ai:results"
EVENTS_STREAM = "vg:events:finalized"

# Service name → (display name, emoji)
SERVICE_MAP = {
    "camera": ("Camera Capture", "📷"),
    "worker-weapon": ("Weapon Worker", "🔫"),
    "worker-fire": ("Fire Worker", "🔥"),
    "worker-fall": ("Fall Worker", "🤸"),
    "ecs": ("ECS Brain", "🧠"),
    "clip-recorder": ("Clip Recorder", "🎬"),
    "alert-worker": ("Alert Worker", "🚨"),
    "backend": ("Backend API", "🌐"),
}

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
    .stApp { background-color: #0a0e17; }
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460; border-radius: 12px; padding: 14px;
    }
    .status-healthy { color: #48bb78; font-weight: 600; }
    .status-warning { color: #ecc94b; font-weight: 600; }
    .status-error   { color: #fc8181; font-weight: 600; }
    .svc-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #0f3460; border-radius: 10px; padding: 12px;
        text-align: center; min-height: 100px;
    }
    .svc-card.stale { border-color: #ecc94b; }
    .svc-card.dead  { border-color: #fc8181; }
    .stImage > img { border-radius: 8px; border: 2px solid #0f3460; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

@st.cache_resource
def get_redis():
    """Create Redis connection (cached)."""
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT,
                        decode_responses=True,
                        socket_connect_timeout=3, socket_timeout=5)
        r.ping()
        return r
    except Exception:
        return None


def get_db_connection():
    """Get PostgreSQL connection."""
    try:
        import psycopg2
        return psycopg2.connect(host=PG_HOST, user=PG_USER,
                                password=os.getenv(
                                    "VG_POSTGRES_PASSWORD", "postgres"),
                                dbname=PG_DB, connect_timeout=3)
    except Exception:
        return None


def get_system_settings(r):
    """Read live system settings from Redis JSON key."""
    try:
        raw = r.get("vg:system_settings")
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def get_service_metrics(r):
    """Read all service heartbeat metrics from Redis."""
    metrics = {}
    now = time.time()
    try:
        for key in r.keys("vg:metrics:*"):
            # key format: vg:metrics:{service}:{instance_id}
            parts = key.split(":")
            if len(parts) >= 3:
                # handle multi-part names like worker-weapon
                service = ":".join(parts[2:-1])
                raw = r.get(key)
                if raw:
                    data = json.loads(raw)
                    ts = data.get("timestamp", 0)
                    data["age_s"] = round(now - ts, 1) if ts else 9999
                    data["service_key"] = service
                    metrics[service] = data
    except Exception:
        pass
    return metrics


def get_camera_fps(r):
    """Read per-camera actual FPS from Redis (15s TTL keys)."""
    fps_data = {}
    try:
        for key in r.keys("vg:metrics:camera:*:fps"):
            parts = key.split(":")
            if len(parts) >= 4:
                cam_id = parts[3]
                val = r.get(key)
                fps_data[cam_id] = float(val) if val else 0.0
    except Exception:
        pass
    return fps_data


def analyze_results_stream(r, count=60):
    """Analyze the AI results stream: throughput, per-model stats, latency."""
    result = {"throughput": None, "per_model": {}, "stream_len": 0,
              "last_id": "N/A", "last_age_s": None, "maxlen": None}
    try:
        result["stream_len"] = r.xlen(RESULT_STREAM) or 0
        info = r.xinfo_stream(RESULT_STREAM)
        result["last_id"] = info.get("last-generated-id", "N/A")
        le = info.get("last-entry")
        if le:
            eid = le[0] if isinstance(le, (list, tuple)) else str(le)
            ts_ms = int(str(eid).split("-")[0])
            result["last_age_s"] = round(
                (time.time() * 1000 - ts_ms) / 1000, 1)
        # maxlen from stream info
        try:
            result["maxlen"] = info.get("maxlen", None)
        except Exception:
            pass
    except Exception:
        pass

    try:
        sample = r.xrevrange(RESULT_STREAM, count=count)
        if len(sample) < 2:
            return result

        newest_ms = int(str(sample[0][0]).split("-")[0])
        oldest_ms = int(str(sample[-1][0]).split("-")[0])
        span_s = (newest_ms - oldest_ms) / 1000.0
        throughput = len(sample) / span_s if span_s > 0 else None
        result["throughput"] = throughput

        # Per-model stats
        models = {}
        for _, data in sample:
            m = data.get("model_type", data.get("model", "unknown"))
            if m not in models:
                models[m] = {"count": 0, "latencies": [], "confidences": []}
            models[m]["count"] += 1
            lat = data.get("inference_latency_ms")
            if lat is not None:
                try:
                    models[m]["latencies"].append(float(lat))
                except (ValueError, TypeError):
                    pass
            conf = data.get("confidence")
            if conf is not None:
                try:
                    models[m]["confidences"].append(float(conf))
                except (ValueError, TypeError):
                    pass

        total = sum(v["count"] for v in models.values())
        for m, stats in models.items():
            cnt = stats["count"]
            pct = cnt / total * 100 if total else 0
            rate = throughput * cnt / total if throughput else 0
            avg_lat = (sum(stats["latencies"]) / len(stats["latencies"])
                       if stats["latencies"] else None)
            confs = stats["confidences"]
            result["per_model"][m] = {
                "count": cnt, "pct": pct, "rate": rate,
                "avg_latency_ms": avg_lat,
                "avg_conf": sum(confs) / len(confs) if confs else None,
                "min_conf": min(confs) if confs else None,
                "max_conf": max(confs) if confs else None,
            }
    except Exception:
        pass
    return result


def get_detection_dir():
    """Find detection images directory."""
    for d in DETECTION_DIRS:
        if os.path.isdir(d):
            return d
    local_cache = os.path.join(os.path.dirname(__file__), ".detection_cache")
    if os.path.isdir(local_cache):
        return local_cache
    return None


def get_detection_images(detection_dir, model_filter=None, limit=12):
    """Get most recent detection images."""
    if not detection_dir or not os.path.isdir(detection_dir):
        return []
    pattern = f"{model_filter}_*.jpg" if model_filter else "*.jpg"
    images = glob.glob(os.path.join(detection_dir, pattern))
    images.sort(key=os.path.getmtime, reverse=True)
    return images[:limit]


def parse_detection_filename(filepath):
    """Parse model type, camera ID, and timestamp from filename."""
    name = os.path.basename(filepath).replace('.jpg', '')
    parts = name.split('_')
    if len(parts) >= 3:
        try:
            return parts[0], parts[1], datetime.fromtimestamp(int(parts[-1]) / 1000)
        except (ValueError, OSError):
            pass
    return "unknown", "unknown", None


def model_emoji(model_type: str) -> str:
    return {"weapon": "🔫", "fire": "🔥", "fall": "🤸"}.get(model_type, "❓")


# ═══════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════

with st.sidebar:
    st.title("🛡️ VisionGuard Debug")
    st.markdown("---")
    refresh_rate = st.selectbox(
        "Auto-refresh (seconds)", [2, 5, 10, 30], index=1)
    st.markdown("---")
    st.markdown("### Connections")

    r = get_redis()
    if r:
        st.markdown('<span class="status-healthy">● Redis Connected</span>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-error">● Redis Disconnected</span>',
                    unsafe_allow_html=True)

    db = get_db_connection()
    if db:
        st.markdown('<span class="status-healthy">● PostgreSQL Available</span>',
                    unsafe_allow_html=True)
        db.close()
    else:
        st.markdown('<span class="status-error">● PostgreSQL Not Found</span>',
                    unsafe_allow_html=True)

    det_dir = get_detection_dir()
    if det_dir:
        img_count = len(glob.glob(os.path.join(det_dir, "*.jpg")))
        st.markdown(f'<span class="status-healthy">● Detection Images ({img_count})</span>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<span class="status-warning">● No Detection Images Dir</span>',
                    unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Configuration")
    st.markdown(f"**Redis:** `{REDIS_HOST}:{REDIS_PORT}`")
    st.markdown(f"**PostgreSQL:** `{PG_USER}@{PG_HOST}/{PG_DB}`")

    st.markdown("---")
    st.markdown("### 🔒 Read-Only Mode")
    st.caption("This dashboard only READS from Redis and PostgreSQL. No writes.")

    st.markdown("---")
    if st.button("🔄 Force Refresh"):
        st.cache_resource.clear()
        st.rerun()


# ═══════════════════════════════════════════════════════════
# MAIN HEADER
# ═══════════════════════════════════════════════════════════

st.title("🛡️ VisionGuard AI — Pipeline Debug Dashboard")
st.caption(
    f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  •  "
    f"Auto-refresh every {refresh_rate}s  •  "
    f"Camera → Queues → AI Workers → Results → ECS → Database")

# Load shared data once
settings = get_system_settings(r) if r else {}
svc_metrics = get_service_metrics(r) if r else {}
cam_fps = get_camera_fps(r) if r else {}
results = analyze_results_stream(r) if r else {}


# ═══════════════════════════════════════════════════════════
# SECTION 1: SYSTEM HEALTH OVERVIEW
# ═══════════════════════════════════════════════════════════

st.markdown("---")
st.markdown("## 🏥 System Health")

if svc_metrics:
    cols = st.columns(4)
    for idx, (svc_key, (display_name, emoji)) in enumerate(SERVICE_MAP.items()):
        data = svc_metrics.get(svc_key)
        with cols[idx % 4]:
            if data:
                age = data.get("age_s", 9999)
                if age < 30:
                    status_cls = "status-healthy"
                    status_txt = "Healthy"
                elif age < 120:
                    status_cls = "status-warning"
                    status_txt = "Stale"
                else:
                    status_cls = "status-error"
                    status_txt = "Dead"
                cpu = data.get("cpu_percent", 0)
                mem = data.get("memory_gb", 0)
                st.markdown(
                    f"**{emoji} {display_name}**\n\n"
                    f'<span class="{status_cls}">● {status_txt}</span>\n\n'
                    f"CPU: {cpu:.1f}%  |  RAM: {mem:.0f} MB\n\n"
                    f"HB: {age:.0f}s ago",
                    unsafe_allow_html=True)
            else:
                st.markdown(
                    f"**{emoji} {display_name}**\n\n"
                    f'<span class="status-error">● No Heartbeat</span>',
                    unsafe_allow_html=True)
else:
    st.info("No service heartbeat data available in Redis.")


# ═══════════════════════════════════════════════════════════
# SECTION 2: CAMERA CAPTURE
# ═══════════════════════════════════════════════════════════

st.markdown("---")
st.markdown("## 📷 Camera Capture")

cam_settings = settings.get("cameraCapture", {})
default_fps = cam_settings.get("defaultFps", 5)
motion_thresh = cam_settings.get("motionThreshold", 0.02)
global_fps_target = settings.get("cameras", {}).get("globalFpsTarget", 15)

ccol1, ccol2, ccol3, ccol4 = st.columns(4)
with ccol1:
    st.metric("Default Camera FPS", default_fps)
with ccol2:
    st.metric("Motion Threshold", f"{motion_thresh:.2f}")
with ccol3:
    st.metric("Global FPS Target", global_fps_target,
              help="Display-only threshold (not enforced as a system cap)")

if cam_fps:
    total_fps = sum(cam_fps.values())
    with ccol4:
        st.metric("Total Capture FPS", f"{total_fps:.1f}",
                  help=f"Sum of {len(cam_fps)} active camera(s)")

    # Per-camera breakdown
    # Read camera config from cameras.json file (not Redis settings)
    cam_config_map = {}
    try:
        cam_config_path = os.path.join(os.path.dirname(__file__), "..", "cameras.json")
        if os.path.exists(cam_config_path):
            with open(cam_config_path, 'r') as f:
                cam_data = json.load(f)
                if isinstance(cam_data, dict) and "cameras" in cam_data:
                    for cam in cam_data["cameras"]:
                        if cam.get("id"):
                            cam_config_map[cam["id"]] = cam.get("fps", default_fps)
    except Exception:
        pass
    
    cam_cols = st.columns(min(len(cam_fps), 4))
    for idx, (cam_id, fps) in enumerate(sorted(cam_fps.items())):
        target_fps = cam_config_map.get(cam_id, default_fps)
        with cam_cols[idx % len(cam_cols)]:
            st.markdown(f"**📹 {cam_id}**\n\nActual: **{fps:.1f} FPS** (Target: {target_fps})")
else:
    with ccol4:
        st.metric("Total Capture FPS", "N/A",
                  help="Camera FPS keys expire after 15s of inactivity")
    st.info("No active cameras — FPS keys (vg:metrics:camera:*:fps) expired or cameras not running.")


# ═══════════════════════════════════════════════════════════
# SECTION 3: TASK QUEUES
# ═══════════════════════════════════════════════════════════

st.markdown("---")
st.markdown("## 📥 Task Queues")

queue_mgmt = settings.get("queueManagement", {})
task_ttl = queue_mgmt.get("taskTtlSeconds", 3600)
max_queue = queue_mgmt.get("maxQueueSize", 10000)

if r:
    col1, col2, col3, col4 = st.columns(4)
    queue_lengths = {}
    total_queued = 0
    for q in TASK_QUEUES:
        try:
            l = r.zcard(q)
        except Exception:
            l = -1
        queue_lengths[q] = l
        if l > 0:
            total_queued += l

    with col1:
        st.metric("🔴 Weapon (vg:critical)",
                  queue_lengths.get("vg:critical", 0))
    with col2:
        st.metric("🟡 Fire (vg:high)", queue_lengths.get("vg:high", 0))
    with col3:
        st.metric("🟢 Fall (vg:medium)", queue_lengths.get("vg:medium", 0))
    with col4:
        st.metric("📦 Total Backlog", total_queued)

    # Settings row
    st.caption(
        f"Queue TTL: {task_ttl}s  |  Max queue size: {max_queue:,}  |  Data type: sorted set (ZADD/ZPOPMIN)")

    if total_queued > 100:
        st.warning(
            f"⚠️ {total_queued} frames queued — Workers are falling behind camera FPS!")
    elif total_queued == 0:
        st.success("✅ Real-time — Workers matching Camera FPS with zero backlog.")
    else:
        st.info(f"ℹ️ {total_queued} frames in buffer being actively processed.")
else:
    st.error("Cannot connect to Redis")


# ═══════════════════════════════════════════════════════════
# SECTION 4: AI WORKER THROUGHPUT
# ═══════════════════════════════════════════════════════════

st.markdown("---")
st.markdown("## 🤖 AI Worker Throughput")

if r and results:
    throughput = results.get("throughput")
    stream_len = results.get("stream_len", 0)
    last_age = results.get("last_age_s")
    per_model = results.get("per_model", {})

    # Top metrics row
    wcol1, wcol2, wcol3, wcol4 = st.columns(4)
    with wcol1:
        if throughput is not None:
            st.metric("Total Throughput", f"{throughput:.1f} results/s",
                      help="All models combined, measured over last 60 messages")
        else:
            st.metric("Total Throughput", "N/A")
    with wcol2:
        st.metric("Stream Length", stream_len,
                  help=f"Maxlen: {results.get('maxlen', 'N/A')}")
    with wcol3:
        if last_age is not None:
            if last_age < 10:
                st.metric("Last Result Age", f"{last_age}s ago")
            elif last_age < 60:
                st.metric("Last Result Age", f"{last_age:.0f}s ago")
            else:
                st.metric("Last Result Age", f"{last_age/60:.1f}min ago")
        else:
            st.metric("Last Result Age", "N/A")
    with wcol4:
        n_models = len(per_model)
        st.metric("Active Models", n_models)

    # Per-model detail table
    if per_model:
        model_rows = []
        for m, stats in sorted(per_model.items()):
            model_rows.append({
                "Model": f"{model_emoji(m)} {m.upper()}",
                "Rate": f"{stats['rate']:.1f}/s",
                "Share": f"{stats['pct']:.0f}%",
                "Avg Latency": f"{stats['avg_latency_ms']:.0f}ms" if stats['avg_latency_ms'] else "N/A",
                "Avg Conf": f"{stats['avg_conf']:.3f}" if stats['avg_conf'] else "N/A",
                "Min Conf": f"{stats['min_conf']:.3f}" if stats['min_conf'] else "N/A",
                "Max Conf": f"{stats['max_conf']:.3f}" if stats['max_conf'] else "N/A",
            })
        st.dataframe(model_rows, use_container_width=True, hide_index=True)

    # Recent messages expander
    with st.expander("📋 Last 10 Raw Stream Messages", expanded=False):
        try:
            recent = r.xrevrange(RESULT_STREAM, count=10)
            for msg_id, data in recent:
                cam = data.get("camera_id", "?")
                model = data.get("model_type", data.get("model", "?"))
                conf = data.get("confidence", "?")
                lat = data.get("inference_latency_ms", "?")
                try:
                    lat_str = f"{float(lat):.0f}ms"
                except (ValueError, TypeError):
                    lat_str = str(lat)
                st.text(
                    f"  [{msg_id}] {model} conf={conf} lat={lat_str} cam={cam}")
        except Exception as e:
            st.error(f"Error reading stream: {e}")
else:
    st.info("No results stream data available.")


# ═══════════════════════════════════════════════════════════
# SECTION 5: ECS EVENT BRAIN
# ═══════════════════════════════════════════════════════════

st.markdown("---")
st.markdown("## 🧠 ECS Event Brain")

if r:
    ecol1, ecol2, ecol3, ecol4 = st.columns(4)

    ecs_cfg = settings.get("ecs", {})
    corr_window = ecs_cfg.get("correlationWindowMs", 400)
    hard_ttl = ecs_cfg.get("hardTtlSeconds", 2.0)

    try:
        stream_len = r.xlen(RESULT_STREAM)
        ecs_last_id = r.get("vg:ecs:last_id")
        pending = 0
        if ecs_last_id and ecs_last_id != "0-0":
            try:
                pending = r.xcount(RESULT_STREAM, f"({ecs_last_id}", "+")
            except Exception:
                pending = 0
        else:
            pending = stream_len or 0

        with ecol1:
            if pending == 0:
                st.metric("Processing", "Idle ✅")
            elif pending < 50:
                st.metric("Processing", f"Active ({pending})")
            else:
                st.metric("Processing", f"Backlog ({pending})")
        with ecol2:
            st.metric("Correlation Window", f"{corr_window}ms")
        with ecol3:
            st.metric("Hard TTL", f"{hard_ttl}s")
    except Exception as e:
        with ecol1:
            st.metric("Processing", "Unknown")
        st.error(f"ECS read error: {e}")

    # Event generation rate from finalized stream
    try:
        evt_len = r.xlen(EVENTS_STREAM)
        with ecol4:
            st.metric("Finalized Events", evt_len,
                      help="Total events in vg:events:finalized stream")
    except Exception:
        with ecol4:
            st.metric("Finalized Events", "N/A")

    # Live ECS config from settings (not hardcoded!)
    with st.expander("⏱️ ECS Configuration (live from vg:system_settings)", expanded=False):
        ecfg1, ecfg2, ecfg3 = st.columns(3)
        ecs_thresholds = ecs_cfg.get("thresholds", {})
        weapon_p = ecs_cfg.get("weaponPersistence", {})
        fire_p = ecs_cfg.get("firePersistence", {})
        fall_p = ecs_cfg.get("fallPersistence", {})

        with ecfg1:
            st.markdown("**🔫 Weapon**")
            st.text(f"  ECS threshold: {ecs_thresholds.get('weapon', 'N/A')}")
            st.text(
                f"  Min detections: {weapon_p.get('minDetections', 'N/A')}")
            st.text(f"  Window: {weapon_p.get('windowSec', 'N/A')}s")
            st.text(f"  Cooldown: {weapon_p.get('cooldownSec', 'N/A')}s")
        with ecfg2:
            st.markdown("**🔥 Fire**")
            st.text(f"  ECS threshold: {ecs_thresholds.get('fire', 'N/A')}")
            st.text(f"  Min detections: {fire_p.get('minDetections', 'N/A')}")
            st.text(f"  Window: {fire_p.get('windowSec', 'N/A')}s")
            st.text(f"  Cooldown: {fire_p.get('cooldownSec', 'N/A')}s")
        with ecfg3:
            st.markdown("**🤸 Fall**")
            st.text(f"  ECS threshold: {ecs_thresholds.get('fall', 'N/A')}")
            st.text(f"  Min detections: {fall_p.get('minDetections', 'N/A')}")
            st.text(f"  Window: {fall_p.get('windowSec', 'N/A')}s")
            st.text(f"  Cooldown: {fall_p.get('cooldownSec', 'N/A')}s")

    # Recent finalized events
    try:
        evt_sample = r.xrevrange(EVENTS_STREAM, count=10)
        if evt_sample:
            with st.expander(f"📋 Recent Finalized Events (last {len(evt_sample)})", expanded=False):
                for eid, edata in evt_sample:
                    etype = edata.get("event_type", "?")
                    conf = edata.get("confidence", "?")
                    sev = edata.get("severity", "?")
                    cam = edata.get("camera_id", "?")
                    try:
                        ts_ms = int(str(eid).split("-")[0])
                        age = (time.time() * 1000 - ts_ms) / 1000
                        if age < 60:
                            age_str = f"{age:.0f}s ago"
                        elif age < 3600:
                            age_str = f"{age/60:.1f}min ago"
                        else:
                            age_str = f"{age/3600:.1f}h ago"
                    except Exception:
                        age_str = "?"
                    try:
                        conf_str = f"{float(conf):.3f}"
                    except (ValueError, TypeError):
                        conf_str = str(conf)
                    st.text(f"  {model_emoji(etype.replace('_detected', ''))} {etype} "
                            f"conf={conf_str} sev={sev} cam={cam} ({age_str})")
    except Exception:
        pass
else:
    st.error("Cannot connect to Redis")


# ═══════════════════════════════════════════════════════════
# SECTION 6: DATABASE
# ═══════════════════════════════════════════════════════════

st.markdown("---")
st.markdown("## 💾 Database")

db = get_db_connection()
if db:
    try:
        cursor = db.cursor()

        # Event counts
        cursor.execute("SELECT COUNT(*) FROM events")
        total = cursor.fetchone()[0]
        cursor.execute(
            "SELECT event_type, COUNT(*) FROM events GROUP BY event_type")
        by_type = cursor.fetchall()
        type_counts = {row[0]: row[1] for row in by_type}

        dcol1, dcol2, dcol3, dcol4 = st.columns(4)
        with dcol1:
            st.metric("Total Events", total)
        with dcol2:
            st.metric("🔫 Weapon", type_counts.get(
                "weapon_detected", 0) + type_counts.get("weapon", 0))
        with dcol3:
            st.metric("🔥 Fire", type_counts.get(
                "fire_detected", 0) + type_counts.get("fire", 0))
        with dcol4:
            st.metric("🤸 Fall", type_counts.get(
                "fall_detected", 0) + type_counts.get("fall", 0))

        # Alerts summary
        try:
            cursor.execute("SELECT COUNT(*) FROM alerts")
            alert_total = cursor.fetchone()[0]
            cursor.execute(
                "SELECT status, COUNT(*) FROM alerts GROUP BY status"
            )
            alert_by_status = {row[0]: row[1] for row in cursor.fetchall()}
            acol1, acol2, acol3, acol4 = st.columns(4)
            with acol1:
                st.metric("Total Alerts", alert_total)
            with acol2:
                st.metric("Pending", alert_by_status.get("pending", 0))
            with acol3:
                st.metric("Dispatched", alert_by_status.get("dispatched", 0))
            with acol4:
                st.metric("Resolved", alert_by_status.get("resolved", 0))
        except Exception:
            pass

        # Event statistics
        try:
            cursor.execute("""
                SELECT event_type, COUNT(*),
                       MIN(confidence), MAX(confidence), AVG(confidence)
                FROM events GROUP BY event_type
            """)
            stats = cursor.fetchall()
            if stats:
                st.markdown("### Event Confidence Statistics")
                st.dataframe([
                    {"Type": s[0], "Count": s[1],
                     "Min": f"{s[2]:.3f}" if s[2] else "N/A",
                     "Max": f"{s[3]:.3f}" if s[3] else "N/A",
                     "Avg": f"{s[4]:.3f}" if s[4] else "N/A"}
                    for s in stats
                ], use_container_width=True, hide_index=True)
        except Exception:
            pass

        # Recent events
        cursor.execute("""
            SELECT event_type, confidence, camera_id,
                   to_timestamp(created_at) as time, model_version
            FROM events ORDER BY created_at DESC LIMIT 20
        """)
        recent_events = cursor.fetchall()
        if recent_events:
            st.markdown("### Recent Events (last 20)")
            st.dataframe([
                {"Type": e[0], "Confidence": f"{e[1]:.3f}" if e[1] else "N/A",
                 "Camera": e[2], "Time": e[3],
                 "Model": e[4] if len(e) > 4 else "N/A"}
                for e in recent_events
            ], use_container_width=True, hide_index=True)

        # Duplicate detection
        with st.expander("🔍 Duplicate Event Detection", expanded=False):
            try:
                cursor.execute("""
                    SELECT e1.event_type, ROUND(e1.confidence, 3),
                           e1.camera_id,
                           to_timestamp(e1.created_at),
                           to_timestamp(e2.created_at),
                           ROUND((e2.created_at - e1.created_at)::numeric, 1)
                    FROM events e1 JOIN events e2 ON (
                        e1.event_type = e2.event_type AND
                        e1.camera_id = e2.camera_id AND
                        ABS(e1.confidence - e2.confidence) < 0.001 AND
                        e2.created_at > e1.created_at AND
                        (e2.created_at - e1.created_at) < 5.0
                    ) ORDER BY e1.created_at DESC LIMIT 20
                """)
                dupes = cursor.fetchall()
                if dupes:
                    st.warning(
                        f"⚠️ {len(dupes)} potential duplicate pairs found")
                    st.dataframe([
                        {"Type": d[0], "Conf": d[1], "Camera": d[2],
                         "Event 1": d[3], "Event 2": d[4], "Gap(s)": d[5]}
                        for d in dupes
                    ], use_container_width=True, hide_index=True)
                else:
                    st.success("✅ No duplicates — ECS v2 cooldown working")
            except Exception as e:
                st.error(f"Error: {e}")

        db.close()
    except Exception as e:
        st.error(f"Database error: {e}")
        db.close()
else:
    st.warning("PostgreSQL not available — check connection")


# ═══════════════════════════════════════════════════════════
# SECTION 7: REDIS RESOURCES
# ═══════════════════════════════════════════════════════════

st.markdown("---")
st.markdown("## 🗝️ Redis Resources")

if r:
    try:
        info_mem = r.info("memory")
        info_cli = r.info("clients")
        info_key = r.info("keyspace")

        rcol1, rcol2, rcol3, rcol4 = st.columns(4)
        with rcol1:
            st.metric("Memory Used", info_mem.get("used_memory_human", "N/A"))
        with rcol2:
            st.metric("Peak Memory", info_mem.get(
                "used_memory_peak_human", "N/A"))
        with rcol3:
            st.metric("Connected Clients", info_cli.get(
                "connected_clients", "N/A"))
        with rcol4:
            # Total keys from keyspace
            db_info = info_key.get("db0", {})
            total_keys = db_info.get(
                "keys", "N/A") if isinstance(db_info, dict) else "N/A"
            st.metric("Total Keys (db0)", total_keys)

        # Key type breakdown
        with st.expander("📊 Key Type Breakdown + All Keys", expanded=False):
            keys = r.keys("vg:*")
            type_counts = {}
            type_details = {}
            if keys:
                for key in sorted(keys):
                    kt = r.type(key)
                    type_counts[kt] = type_counts.get(kt, 0) + 1
                    if kt == "stream":
                        length = r.xlen(key)
                        type_details[key] = f"stream, len={length}"
                    elif kt == "zset":
                        length = r.zcard(key)
                        type_details[key] = f"sorted set, len={length}"
                    elif kt == "string":
                        type_details[key] = "string"
                    elif kt == "hash":
                        length = r.hlen(key)
                        type_details[key] = f"hash, fields={length}"
                    elif kt == "set":
                        length = r.scard(key)
                        type_details[key] = f"set, members={length}"
                    elif kt == "list":
                        length = r.llen(key)
                        type_details[key] = f"list, len={length}"
                    else:
                        type_details[key] = kt

                st.markdown("**Key types:**  " + "  |  ".join(
                    f"{k}: {v}" for k, v in sorted(type_counts.items())))
                st.markdown("---")
                for key in sorted(type_details.keys()):
                    st.text(f"  {key} ({type_details[key]})")
            else:
                st.info("No vg:* keys found")
    except Exception as e:
        st.error(f"Redis INFO error: {e}")
else:
    st.error("Cannot connect to Redis")


# ═══════════════════════════════════════════════════════════
# SECTION 8: LIVE DETECTION GALLERY
# ═══════════════════════════════════════════════════════════

st.markdown("---")
st.markdown("## 📸 Live Detection Gallery")

det_dir = get_detection_dir()
if det_dir:
    filter_col1, _ = st.columns([1, 3])
    with filter_col1:
        model_filter = st.selectbox("Filter by model",
                                    ["all", "weapon", "fire", "fall"],
                                    index=0, key="gallery_filter")
    filter_val = None if model_filter == "all" else model_filter
    images = get_detection_images(det_dir, model_filter=filter_val, limit=12)

    if images:
        cols_per_row = 3
        for row_start in range(0, len(images), cols_per_row):
            cols = st.columns(cols_per_row)
            for col_idx, img_path in enumerate(images[row_start:row_start + cols_per_row]):
                model, camera, ts = parse_detection_filename(img_path)
                with cols[col_idx]:
                    st.image(img_path, use_container_width=True)
                    emoji = model_emoji(model)
                    ts_str = ts.strftime("%H:%M:%S") if ts else "N/A"
                    st.markdown(
                        f"**{emoji} {model.upper()}** • cam: `{camera}` • {ts_str}")
    else:
        st.info("📭 No detection images yet — will appear when workers detect objects.")
else:
    st.info("Detection images directory not found.")


# ───────── Footer ─────────
st.markdown("---")
st.caption("VisionGuard AI — Pipeline Debug Dashboard v3.0 • Read-only • "
           "Camera → Queues → Workers → Results → ECS → Database")

# ───────── Auto-refresh ─────────
time.sleep(refresh_rate)
st.rerun()
