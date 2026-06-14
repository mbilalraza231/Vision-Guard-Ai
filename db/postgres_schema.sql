-- VisionGuard AI - PostgreSQL Schema

-- Events Table
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,               -- UUID v4 (as string)
    camera_id TEXT NOT NULL,
    event_type TEXT NOT NULL,           -- weapon | fire | fall | ...
    severity TEXT NOT NULL,             -- critical | high | medium
    start_ts DOUBLE PRECISION NOT NULL,  -- epoch (seconds)
    end_ts DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL, -- 0.0 – 1.0
    model_version TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    clip_status TEXT NOT NULL DEFAULT 'pending',   -- pending | ready | failed
    clip_error TEXT,
    clip_updated_at DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'active',         -- active | acknowledged | resolved
    acknowledged_by TEXT,
    acknowledged_at DOUBLE PRECISION,
    resolved_by TEXT,
    resolved_at DOUBLE PRECISION,
    resolution TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_camera_created 
    ON events(camera_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_type_severity 
    ON events(event_type, severity);

-- Event Evidence Table
CREATE TABLE IF NOT EXISTS event_evidence (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL,         -- clip | snapshot
    storage_provider TEXT,               -- cloudinary | s3 | local
    public_url TEXT,
    created_at DOUBLE PRECISION NOT NULL,
    CONSTRAINT fk_event
        FOREIGN KEY(event_id) 
        REFERENCES events(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_evidence_event_id ON event_evidence(event_id);

-- Alerts Table
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    channel TEXT NOT NULL,               -- webhook | email | sms
    recipient TEXT,                      -- e.g. "John Doe" or "+123456789"
    status TEXT NOT NULL,                -- pending | sent | failed
    error_message TEXT,                  -- detail on failure
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_ts DOUBLE PRECISION,
    created_at DOUBLE PRECISION NOT NULL,
    details TEXT
);

CREATE INDEX IF NOT EXISTS idx_alerts_event_id ON alerts(event_id);

-- Alert Contacts Table
CREATE TABLE IF NOT EXISTS alert_contacts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    whatsapp BOOLEAN DEFAULT TRUE,
    email_alert BOOLEAN DEFAULT TRUE,
    min_severity TEXT DEFAULT 'medium',
    is_active BOOLEAN DEFAULT TRUE,
    zone_ids TEXT DEFAULT '[]',          -- JSON array of zone IDs
    created_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contacts_active ON alert_contacts(is_active);

-- Zones Table
CREATE TABLE IF NOT EXISTS zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    active_hours VARCHAR(100) DEFAULT '24/7',
    max_cameras INTEGER DEFAULT 0,
    max_alert_recipients INTEGER DEFAULT 0,
    priority_weapon VARCHAR(20) DEFAULT 'critical',    -- critical | high | medium | low
    priority_fire VARCHAR(20) DEFAULT 'high',          -- critical | high | medium | low
    priority_fall VARCHAR(20) DEFAULT 'medium',        -- critical | high | medium | low
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Cameras Table
CREATE TABLE IF NOT EXISTS cameras (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    fps INTEGER NOT NULL DEFAULT 5,
    motion_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.02,
    priority TEXT NOT NULL DEFAULT 'medium',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    zone_id TEXT,                        -- FK to zones
    created_at DOUBLE PRECISION NOT NULL
);

-- Incident Notes Table
CREATE TABLE IF NOT EXISTS incident_notes (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at DOUBLE PRECISION NOT NULL,
    user_name TEXT DEFAULT 'Security Operator',
    CONSTRAINT fk_incident_event
        FOREIGN KEY(event_id) 
        REFERENCES events(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_incident_notes_event_id ON incident_notes(event_id);

