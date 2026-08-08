-- v0.3 pipeline revision (D2/D13 [REVISED v0.3], D14):
--   * quality-pass jobs report percent progress
--   * named multi-mic capture: explicit mic registry per meeting, each with
--     its own encrypted recording; the name tag flows to speaker labels
--   * the asr_device setting is gone (D13 v0.3: one behavior, no choice) —
--     drop any stored value so nothing lingers

ALTER TABLE jobs ADD COLUMN progress INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS meeting_mics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    audio_path TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mics_meeting ON meeting_mics(meeting_id);

DELETE FROM settings WHERE key = 'asr_device';
