-- VisionGuard AI - Per-Zone Detection Priority
-- Adds severity override columns for each detection type per zone.
-- Defaults match the backend rule engine: weapon=critical, fire=high, fall=medium

ALTER TABLE zones ADD COLUMN IF NOT EXISTS priority_weapon  VARCHAR(20) DEFAULT 'critical';
ALTER TABLE zones ADD COLUMN IF NOT EXISTS priority_fire    VARCHAR(20) DEFAULT 'high';
ALTER TABLE zones ADD COLUMN IF NOT EXISTS priority_fall    VARCHAR(20) DEFAULT 'medium';
