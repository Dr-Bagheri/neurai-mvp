# NeurAI server

The Python FastAPI engine — ASR, model harness, RAG, skills, auth, storage —
per [ARCHITECTURE.md](../ARCHITECTURE.md). The browser UI in `../webui` is
served by this server as a static bundle.

## Layout

```
neurai/
├── main.py        # FastAPI app factory, lifespan (job worker), webui serving
├── config.py      # env-driven boot config (NEURAI_*); runtime settings live in DB
├── db/            # SQLite (WAL) schema + access layer — per-user scoping everywhere
├── auth/          # local accounts, argon2id hashes, session cookies
├── api/           # REST + WebSocket routers (meetings, chat, documents, admin, …)
├── audio/         # live recording sessions, GPU quality pass w/ progress, diarization
├── harness/       # complete(): local/cloud routing, consent gate, fallback, map-reduce
├── skills/        # Skill Runtime (ACL, manifests, confirmation gate, audit) + intent router
├── rag/           # embeddings (Ollama BGE-M3), owner-scoped vector search, indexing
├── fa/            # fa_normalize(), Jalali calendar
├── minutes/       # صورتجلسه/standup templates, SRT, Word export
└── jobs/          # persistent priority queue; heavy jobs yield to live meetings
```

## Run (dev)

```
cd server
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\python -m neurai.main
```

Open http://localhost:8471 — first visit asks for the admin account
(`/api/auth/setup`). API docs at `/docs`.

### Without any models installed

`NEURAI_ASR=fake` runs the whole pipeline with a deterministic fake ASR
engine and hash embeddings — every feature works end-to-end (this is what CI
uses, network-blocked). With real models:

- **ASR:** `pip install -e .[asr]` (faster-whisper); models auto-download on
  first use, or pre-place them for air-gapped installs.
- **LLM + embeddings:** install [Ollama](https://ollama.com), then
  `ollama pull qwen3.5:4b` and `ollama pull bge-m3` (D14).
- **Diarization (optional):** `pip install -e .[diarization]` (pyannote 3.1,
  pinned <4) + `NEURAI_HF_TOKEN` for the gated model; without it the quality
  pass skips diarization gracefully.
- **Word export:** `pip install -e .[export]` (python-docx).

Key env vars (see `neurai/config.py` for all): `NEURAI_DATA_DIR`,
`NEURAI_PORT`, `NEURAI_PROFILE` (`auto`|`air_gapped`), `NEURAI_OLLAMA_URL`,
`NEURAI_LOCAL_MODEL`, `NEURAI_ASR_QUALITY_MODEL`, `NEURAI_ASR_MODEL_DIR`
(an alternate local CTranslate2 model dir — the D14 Persian-turbo bake-off
hook), `NEURAI_HF_TOKEN`, `NEURAI_OLLAMA_TIMEOUT` (default 600 s),
`NEURAI_OLLAMA_KEEP_ALIVE` (default `30m`), `NEURAI_OLLAMA_THINK`
(the installer sets `false` for qwen3.5 — D14 think-false).

Offline hygiene (D9): cached Whisper models load with `local_files_only`
first, so an air-gapped server never pings HuggingFace for revision checks.

Cloud (OpenRouter) is **off** until an admin enables it via
`PUT /api/admin/settings` *and* a meeting/chat opts in (`allow_cloud`) — D3.

## Tests

```
.venv\Scripts\python -m pytest
```

The suite runs fully offline (fake engines) and covers the architecture's
security claims: per-user isolation over REST *and* through skills, the
consent-gated cloud policy, mid-task cloud→local fallback, the confirmation
gate on side-effectful skills, and the append-only audit log.

## TypeScript client for the webui

```
.venv\Scripts\python scripts\export_openapi.py    # writes ../webui/openapi.json
```

## Security hardening in place (D4/D8)

- argon2id password hashes (scrypt verify-fallback), login lockout backoff,
  password change revokes all sessions (`POST /api/auth/change-password`).
- Secrets (OpenRouter key, at-rest keys) in a **DPAPI-backed store** under
  `<data>/secrets/` — never in the DB, config files, or repo.
- **Encryption at rest, default-on (Phase 1 exit criterion):**
  - Database via **SQLCipher** (`sqlcipher3-wheels`, a base dependency).
  - Recordings as sealed **AES-256-CTR** files (`meeting_N.neura`, see
    `neurai/security/audiocrypt.py`). CTR was chosen because it preserves
    both invariants at once: chunks are still encrypted + fsynced the moment
    they arrive (crash-safe, D2 — no finalization step exists to lose), and
    byte-offset random access keeps Range-seekable playback (the WAV
    container is synthesized at serving time).
- **Crash recovery:** meetings still `live` at startup flip to processing and
  their quality pass is queued — the sealed recording is already complete up
  to the crash.
- **Versioned SQL migrations from 001** (`neurai/db/migrations/`; steward
  ruling: numbered plain-SQL runner, no ORM). Never edit a shipped migration —
  every schema change is a new numbered file.
- **True deletion (D4):** deleting a meeting removes transcript, audio,
  exports, and embeddings/search entries together.
- Per-meeting **sensitivity**: «محرمانه» meetings are forced local-only and
  excluded from cross-meeting indexing.
- **Tamper-evident admin audit (D12):** destructive/security-relevant admin
  actions (archive removal via `GET/DELETE /api/admin/meetings[/{id}]`,
  profile/key changes) append to a hash-chained JSONL file
  (`admin-audit.jsonl`; records `{ts, actor, action, details, prev_hash,
  hash}` with `hash = SHA256(prev_hash ‖ canonical_json)` and a random
  genesis anchor); `GET /api/admin/audit-file` reads it and
  `GET /api/admin/audit-file/verify` walks the chain and reports the first
  broken line. No API can modify it.
- **Grounded generation (D5):** meeting skills refuse to summarize an empty
  or trivial transcript (honest Persian answer, no LLM call) and every
  generation prompt carries an explicit anti-fabrication clause.
- **Stop button (D5):** `POST /api/chats/{id}/cancel` aborts the in-flight
  Ollama/OpenRouter request (CPU freed); the message POST returns
  `type: "stopped"` and the chat stores «⏹ تولید پاسخ متوقف شد.».
- **Compute (D13 v0.3):** GPU-first, one behavior, no setting — ASR loads
  on CUDA with a forced-initialization probe and falls back to CPU silently
  on any load failure (logged, never fatal).
- **Platform-control skills (D7 amendment):** the assistant can administer
  the platform through chat («این جلسه رو حذف کن», «دستگاه پردازش رو بذار روی
  GPU») — only via the Skill Runtime: admin manifests enforced in the runtime
  (denial is shaped like "unknown skill", not probeable), every mutating
  skill behind the rule-2 confirmation card, and all operations go through
  `neurai/platform_ops.py` — the same core the REST admin API calls, so D12
  chain logging happens in one shared path. Skills: get_status,
  delete_meeting, delete_document, set_setting, trigger_backup.
- **Snapshot backup (D4):** `POST /api/admin/backup` uploads a SQLCipher
  snapshot (ciphertext; key never leaves the server) to Supabase storage
  (bucket `neurai-backups`). Requires `supabase_url`/`supabase_key` in the
  secret store; hard-disabled under the air-gapped profile.
- **Write-only cloud credentials:** `GET /api/admin/cloud-status` returns
  `openrouter_configured`/`supabase_configured` booleans only — credential
  values are never returned by any endpoint.

## Online mode (D15)

- **One admin switch:** `PUT /api/admin/mode` (`offline` | `online`). Default
  offline; going online is **probe-gated** (rejected without reachable
  internet) and every change is D12-chained via the shared settings path.
  The air-gapped profile removes the online option entirely.
- **Per-task cloud routing** (all via OpenRouter, admin-overridable):
  `cloud_chat_model` (default `anthropic/claude-sonnet-5`) for chat/skills/
  translation; `cloud_heavy_model` (default `anthropic/claude-opus-5`) for
  summaries/action items/صورتجلسه. Retrieval/embeddings stay local always.
- **Consent-gated cloud ASR (§2.1-3 [REVISED v0.3-online]):** an
  OpenAI-compatible `/audio/transcriptions` provider (secrets
  `cloud_asr_url`/`cloud_asr_key`, model `cloud_asr_model`; default Groq
  `whisper-large-v3-turbo`). Used ONLY when the server is online AND the
  meeting has an explicit per-meeting «رونویسی ابری» opt-in; every use is
  D12-chained; cloud failure falls back to the local GPU pass (never a lost
  transcript). **«محرمانه» meetings refuse cloud transcription even with
  consent — D4 sensitivity is absolute.**

## v0.3 pipeline (D2/D13/D14 revised)

- **No live captions:** during a meeting the server only records (encrypted,
  crash-safe). The quality pass auto-queues at meeting end and reports
  **percent progress** (`GET /api/meetings/{id}/progress`; jobs.progress).
- **Named multi-mic:** register mics per meeting (`/api/meetings/{id}/mics`),
  each WS audio stream binds to a mic id, and the user-chosen name flows to
  speaker labels. Single-room-mic meetings get diarizer labels instead.
- **Models (D14):** faster-whisper large-v3 int8 GPU (Persian-turbo bake-off
  via `NEURAI_ASR_MODEL_DIR`), pyannote 3.1 (optional extra, after ASR),
  qwen3.5:4b think-false, bge-m3.

## Deliberately not here yet

- Speaker identification (enrollment round / voice profiles) — diarizer
  labels + manual relabel cover room mode today.
- Windows service installer + HTTPS cert generation (Phase 4).
