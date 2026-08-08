-- NeurAI schema, migration 001. SQLite + WAL. Source of truth for all data (D4).
-- Per-user scoping is the ACL primitive (D7 rule 1): every user-facing query
-- filters on owner_id/user_id; sharing and workspaces are additive later.
-- (schema_meta is created by the migration runner itself.)

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL
);

-- Runtime-mutable settings (connectivity profile, cloud enabled, model names…)
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meeting_series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    series_id INTEGER REFERENCES meeting_series(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    capture_mode TEXT NOT NULL DEFAULT 'room',          -- room | participants
    status TEXT NOT NULL DEFAULT 'created',             -- created|live|processing|done|failed
    language TEXT NOT NULL DEFAULT 'fa',
    allow_cloud INTEGER NOT NULL DEFAULT 0,             -- per-meeting consent (D3)
    audio_path TEXT,
    started_at TEXT,
    ended_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_meetings_owner ON meetings(owner_id, created_at DESC);

CREATE TABLE IF NOT EXISTS transcript_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    pass TEXT NOT NULL DEFAULT 'live',                  -- live | quality
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    speaker_label TEXT,                                  -- diarizer label ('S1') or username
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_segments_meeting ON transcript_segments(meeting_id, pass, start_ms);

-- Manual relabel (D2): maps a diarizer label to a human name, per meeting.
CREATE TABLE IF NOT EXISTS speaker_names (
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    display_name TEXT NOT NULL,
    PRIMARY KEY (meeting_id, label)
);

CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    t_ms INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meeting_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    t_ms INTEGER,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,                                  -- summary | decisions | minutes
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'local',                -- local | cloud (🏠/☁️ badge)
    model TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS action_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER REFERENCES meetings(id) ON DELETE SET NULL,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assignee TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'open',                 -- open | done | dropped
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_action_items_owner ON action_items(owner_id, status);

CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                                  -- user | assistant | tool
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',                     -- local | cloud | '' for user msgs
    provenance TEXT NOT NULL DEFAULT '[]',               -- JSON: consulted resources (D7 rule 5)
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    mime TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'uploaded',             -- uploaded | indexed | failed
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- RAG chunks for both transcripts and documents. owner_id denormalized so the
-- ACL is a WHERE clause on the vector query itself (D7 rule 1).
CREATE TABLE IF NOT EXISTS rag_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,                                  -- transcript | document
    ref_id INTEGER NOT NULL,                             -- meeting_id or document_id
    seq INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB,                                      -- float32[] little-endian
    embed_model TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rag_owner ON rag_chunks(owner_id, kind);

-- Append-only skill audit log (D7 rule 5). No UPDATE/DELETE path in code.
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    skill TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    resource TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'local',
    ok INTEGER NOT NULL DEFAULT 1,
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                                  -- quality_pass | index_transcript | …
    payload TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'queued',               -- queued|running|done|failed
    priority INTEGER NOT NULL DEFAULT 5,                 -- lower = sooner
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    finished_at TEXT
);

-- Opt-in persistent voice profiles for room-mode speaker ID (D2). Embeddings
-- stay local, deletable by the user.
CREATE TABLE IF NOT EXISTS voice_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    embedding BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
