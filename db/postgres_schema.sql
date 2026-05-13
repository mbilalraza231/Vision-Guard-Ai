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
    clip_updated_at DOUBLE PRECISION
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
    status TEXT NOT NULL,                -- pending | sent | failed
    attempts INTEGER NOT NULL DEFAULT 0,
    last_attempt_ts DOUBLE PRECISION,
    created_at DOUBLE PRECISION NOT NULL,
    CONSTRAINT fk_alert_event
        FOREIGN KEY(event_id) 
        REFERENCES events(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_alerts_event_id ON alerts(event_id);
