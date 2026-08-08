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
├── auth/          # local accounts, scrypt hashes, session cookies
├── api/           # REST + WebSocket routers (meetings, chat, documents, admin, …)
├── audio/         # live sessions, two-pass ASR (pluggable engines), VAD, diarization
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
  `ollama pull qwen3:8b` and `ollama pull bge-m3`.
- **Word export:** `pip install -e .[export]` (python-docx).

Key env vars (see `neurai/config.py` for all): `NEURAI_DATA_DIR`,
`NEURAI_PORT`, `NEURAI_PROFILE` (`auto`|`air_gapped`), `NEURAI_OLLAMA_URL`,
`NEURAI_LOCAL_MODEL`, `NEURAI_ASR_LIVE_MODEL`, `NEURAI_ASR_QUALITY_MODEL`.

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

- argon2id password hashes (scrypt verify-fallback), login lockout backoff.
- Secrets (OpenRouter key, at-rest DB key) in a **DPAPI-backed store** under
  `<data>/secrets/` — never in the DB, config files, or repo.
- **Crash-safe recording:** audio chunks are fsynced to a raw `.pcm` as they
  arrive; orphaned recordings are finalized + queued for the quality pass at
  next startup.
- **Versioned SQL migrations from 001** (`neurai/db/migrations/`).
- DB **at-rest encryption** via SQLCipher when `pip install -e .[encryption]`
  is present (warns loudly when absent — dev/CI only).
- Per-meeting **sensitivity**: «محرمانه» meetings are forced local-only and
  excluded from cross-meeting indexing.

## Deliberately not here yet

- Real diarization/speaker-ID backends (interface in `audio/diarization.py`;
  3D-Speaker is the week-0 candidate) — everything downstream works via the
  `S1` default + manual relabel.
- Silero VAD (energy endpointer in `audio/vad.py` drives the live loop for now).
- Encrypted Supabase snapshot backup (MVP+1, D4).
- Windows service installer + HTTPS cert generation (Phase 4).
