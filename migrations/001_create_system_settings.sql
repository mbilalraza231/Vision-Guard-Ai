-- VisionGuard AI - System Settings Table
-- Stores dashboard configuration as a single JSONB row.

CREATE TABLE IF NOT EXISTS system_settings (
    id          SERIAL PRIMARY KEY,
    data        JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed a single row with empty data (defaults are applied in application code).
INSERT INTO system_settings (data)
SELECT '{}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM system_settings);
