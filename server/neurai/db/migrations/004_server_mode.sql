-- D15: one admin-facing Offline/Online mode replaces the raw cloud toggle.
-- Carry over stored intent (cloud_enabled=1 → online), then drop the old key
-- so there is exactly one source of truth. Meetings gain the explicit
-- per-meeting cloud-transcription opt-in («رونویسی ابری» — §2.1-3 amendment).

INSERT INTO settings(key, value)
SELECT 'server_mode', 'online' FROM settings
WHERE key = 'cloud_enabled' AND value = '1'
  AND NOT EXISTS (SELECT 1 FROM settings WHERE key = 'server_mode');

DELETE FROM settings WHERE key = 'cloud_enabled';

ALTER TABLE meetings ADD COLUMN cloud_transcribe INTEGER NOT NULL DEFAULT 0;
