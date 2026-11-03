-- Migration 1: Add type, status, position columns to notes table
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%f', 'now'))
);

-- Insert initial version if not exists
INSERT INTO schema_version (version) SELECT 0 WHERE NOT EXISTS (SELECT 1 FROM schema_version);

-- Add type column if not exists (for new installations or after migration)
ALTER TABLE notes ADD COLUMN IF NOT EXISTS type VARCHAR(30);

-- Add status column if not exists (migration from old version)
ALTER TABLE notes ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'none';

-- Add position column if not exists (migration from old version)
ALTER TABLE notes ADD COLUMN IF NOT EXISTS position INTEGER DEFAULT 0;