# NeurAI — session guide

NeurAI is a Persian-first, offline-capable, on-premise AI meeting-assistant platform
(FastAPI server on Windows + browser clients over LAN). Build phase: the server engine
(`server/`, 41 tests, encryption default-on) and webui (`webui/`, mock-backed) are built;
real ASR/LLM models are not wired yet (fake/pluggable engines only).

## Source of truth

**[ARCHITECTURE.md](ARCHITECTURE.md) is the single source of truth for all technical
decisions.** Read it before designing or implementing anything. README.md is the public
summary and must be kept in sync with it.

## Rules for every session

1. **Do not contradict locked decisions** (D1–D15 and the §6 decision log) in code or docs.
   If a decision seems wrong while implementing, do not silently deviate — surface it to
   the user and, if they agree, amend ARCHITECTURE.md first (mark the change `[REVISED]`,
   update the §6 decision log), then implement.
2. **New architectural choices get numbered decisions.** Anything that constrains future
   work (library choice with lock-in, schema design, protocol, security mechanism) goes
   into ARCHITECTURE.md as `D8`, `D9`, … with a short rationale — before or alongside the
   code, not after.
3. **Security invariants are non-negotiable** (see D7 and §2.1):
   - Audio stays local by default; ONLY online mode + explicit per-meeting consent
     may send audio to cloud ASR (D15, §2.1-3 [REVISED v0.3-online]). Offline and
     air-gapped modes never send anything, and diarization is always local.
   - Access control is enforced in the data layer / Skill Runtime (user-scoped queries),
     never via prompts.
   - Transcripts and documents are untrusted input; side-effectful skills require human
     confirmation in the UI.
   - Cloud calls only through the Model Harness, only under the consent gate; the
     air-gapped profile must disable all network paths.
   - Every feature must work in the offline profile; CI runs the eval set with network
     blocked.
   - Crash-safe recording: audio chunks hit disk as they arrive; a server crash must never
     lose a meeting (D2).
   - Encryption at rest from migration 001; secrets in Windows DPAPI, never in config
     files or the repo (D4, D8).
   - **No telemetry, ever** — nothing phones home (D9).
4. **Persian-first:** UI is RTL-first, text passes through the shared `fa_normalize()`
   wrapper, dates are Jalali-capable, and new prompts get Persian evals.
5. **Roadmap discipline:** current phase and definitions of done are in ARCHITECTURE.md §5.
   Don't pull backlog items (§5.1) forward without the user's say-so.

## v0.3 in flight (2026-08-08, user-approved)

ARCHITECTURE.md is amended: D2 [REVISED v0.3] (live captions REMOVED — single GPU
quality pass with percent progress), D13 [REVISED v0.3] (one GPU-first compute mode,
no setting), NEW D14 model lineup (large-v3 int8 GPU + vhdm Persian-turbo bake-off,
pyannote 3.1 pinned <4, **qwen3.5:4b think-false** replaces qwen3:8b, bge-m3),
baseline now **16 GB RAM / 8-core / 4 GB GPU**, UI restructure in §6 (search in top
bar, enlarged left assistant panel, Logs menu item, one Meetings section, named
multi-mic). Backend/frontend/docs sessions have their work packages; steward cuts
installer 0.2.0 when they land, then the publisher refreshes the GitHub repo
(new README/details, screenshots, diagrams).

## Workflow

The user runs multiple Claude sessions in parallel on this repo — implementation sessions
(front-end, backend, docs), one architecture steward, and one **publishing session** that
is the only one with working GitHub access (github.com/Dr-Bagheri/neurai-mvp).

- **Do not run `git commit`, `git reset`, or `git push`** — the publishing session syncs
  the working tree and publishes; it keeps local history aligned to origin/main. Save
  files only in a consistent state; its watcher picks them up.
- Don't add binary files intended for GitHub (docs/*.docx is gitignored on purpose).
- When describing changes (in messages or docs), reference the decision(s) implemented,
  e.g. "engine: two-pass ASR skeleton (D2)". Default branch: `main`.

## Status (update when it changes)

- 2026-08-08 (D15 backend): offline/online mode + per-task routing + consent-gated
  cloud ASR implemented, 87 tests green, openapi.json regenerated. server_mode
  offline|online (default offline) is the ONE cloud switch — replaces cloud_enabled
  (migration 004 maps stored intent and drops the key; harness gate reads mode only).
  GET/PUT /api/admin/mode: going online is probe-gated (probe_internet — not mode-gated,
  air-gapped never probes), rejected with Persian detail when unreachable;
  {mode, online_available} for the UI; changes D12-chained; gate also applies through
  the set_setting skill path (one source of truth). Per-task routing: cloud_heavy_model
  (default anthropic/claude-opus-5) for summarize/minutes/merge_notes,
  cloud_chat_model (sonnet-5) for chat/skills/translation. Cloud ASR (D15/§2.1-3
  amendment): secrets cloud_asr_url/cloud_asr_key + setting cloud_asr_model (default
  Groq whisper-large-v3-turbo); per-meeting cloud_transcribe opt-in (migration 004,
  create-time + PUT /api/meetings/{id}/cloud-transcribe, pre-meeting only, blocked
  offline, never for «محرمانه»); quality pass uses the cloud path only when
  online+consent+configured (re-checked at job run), D12-chains every use (meeting id +
  provider host, ok flag — no content/secrets), and ANY failure falls back to the local
  GPU pass — transcript never lost. /api/cloud reason "cloud_disabled" renamed
  "offline_mode". Version still 0.1.8 (steward cuts 0.2.0).
- 2026-08-08 (v0.3 backend): D2/D13 [REVISED v0.3] + D14 + named multi-mic implemented,
  77 tests green, openapi.json regenerated. Live ASR pass REMOVED (recording-only
  sessions; /ws/.../captions → /ws/.../events, lifecycle only). Quality pass auto-queues
  with percent progress (jobs.progress via segment-end/duration; polled at
  GET /api/meetings/{id}/progress). asr_device setting fully removed (migration 003
  drops stored value): one GPU-first behavior with forced-init CUDA probe + silent CPU
  fallback + runtime rebuild belt. D14: qwen3.5:4b think-false default,
  NEURAI_ASR_MODEL_DIR bake-off hook, pyannote 3.1 optional extra ([diarization])
  sequenced after ASR with graceful skip, bge-m3 unchanged. Named multi-mic: meeting_mics
  table (migration 003), CRUD under /api/meetings/{id}/mics, WS audio binds ?mic_id=N,
  per-mic encrypted recordings (meeting_N_mic_M.neura), mic name → speaker labels
  (single-room-mic → diarizer labels), per-mic playback ?mic_id=. Version left at 0.1.8
  per steward instruction (steward bumps to 0.2.0 at installer cut).

- 2026-08-08: Architecture v0.2 locked (decisions D1–D10 + feature set). Keep core code
  OS-neutral — Windows installer and Linux Docker are packaging layers only (D10). Next up:
  **Phase 0** — Persian ASR bake-off on real meeting audio, diarization/speaker-embedding
  license check, load test on a 16 GB no-GPU machine. Results go in `docs/`.
- 2026-08-08: `server/` engine built (D1–D5, D7 + parts of D8): auth/sessions
  (argon2 + lockout), versioned SQL migrations, two-pass audio pipeline with crash-safe
  recording + pluggable ASR (fake engine for CI), consent-gated harness with map-reduce
  and cloud→local fallback, Skill Runtime (ACL/manifests/confirmation gate/audit) +
  intent router, owner-scoped RAG, صورتجلسه/SRT export, job queue, admin API, DPAPI
  secret store, SQLCipher hook. 37 offline tests green (`server/tests/`). OpenAPI
  contract exported to `webui/openapi.json`. Migration deviation RESOLVED by steward
  ruling: numbered-SQL runner accepted, D4 amended `[REVISED]` (no Alembic/ORM).
  Scope ruling: DB **and audio** at-rest encryption are Phase 1 exit criteria
  (default-on before any real meeting data; dev/CI may run unencrypted on fake data).
  Still Phase 4 as planned: retention policy, TLS/installer, signed bundles,
  structured JSON logs (D8/D9 remainder).
- 2026-08-08 (later): Phase 1 encryption exit criteria IMPLEMENTED, default-on:
  SQLCipher is now a base dependency (DB unreadable as plain SQLite — tested), and
  recordings are sealed AES-256-CTR files (`meeting_N.neura`) — CTR preserves both
  the D2 crash-safety invariant (chunks encrypted+fsynced on arrival, no finalization
  step) and Range-seekable playback (WAV synthesized at serving time). Crash recovery
  is now a status flip + requeued quality pass. 40 tests green, whole suite runs with
  encryption active. Approach documented in server/README.md.
- 2026-08-08 (later): sealed-audio format promoted to **D11** by steward. Its hard
  requirement (per-file CTR nonce uniqueness under one master key) verified: nonce is
  128-bit per-file from `secrets.token_bytes` (CSPRNG), resume continues the keystream
  at the ciphertext-length offset (no position reuse). Covered by
  `test_audio_nonce_uniqueness_per_file` — asserts distinct nonces + distinct
  ciphertexts for identical plaintext across 20 files, 16-byte length, CSPRNG source,
  and disjoint keystream on append-resume. 41 tests green.
- 2026-08-08 (review): full D1–D11 audit vs code passed (D2/D3/D9/D11 fully hold; rest
  correct for phase). Docs re-synced (README D1–D11/status/CI claim, webui/server READMEs).
  Wheel packaging fixed: migration SQL now ships as package-data (fresh installs had no
  tables). **Local-only Windows install pack** (D10) built at `installer/` — offline
  wheels + webui + install/uninstall scripts, verified end-to-end (health OK, DB
  encrypted); `installer/`, `docs/*.pdf`, `docs/*.docx` are gitignored by user request.
  Open fix-list handed to sessions: D7 rule-3 manifest enforcement, fa_normalize on RAG
  ingest/query, webui types generated from openapi.json, client.ts still 100% mock.
- 2026-08-08 (feature batch, backend): D12/D13 + D5 amendments implemented, 58 tests
  green, openapi.json regenerated. (1) Stop button: `POST /api/chats/{id}/cancel`
  aborts the in-flight backend HTTP request via a per-chat task registry; chat records
  «متوقف شد» (design: explicit cancel endpoint, documented in api/generation.py).
  (2) Admin archive: `GET/DELETE /api/admin/meetings[/{id}]` (true deletion, any owner)
  + D12 hash-chained `admin-audit.jsonl` (security/adminlog.py, random genesis anchor,
  read + verify endpoints); settings/key changes also chained (kinds only, no secret
  values). (3) D13: `asr_device` cpu|cuda|auto runtime admin setting; CUDA probe falls
  back to CPU on any load failure, engines rebuild on next acquisition. (4) Grounding:
  empty/trivial transcripts get an honest Persian refusal with zero LLM calls;
  anti-fabrication clause on all generation prompts. (5) Online plumbing:
  supabase_url/supabase_key secrets, `GET /api/admin/cloud-status` (booleans only),
  `POST /api/admin/backup` → SQLCipher-ciphertext snapshot upload via Supabase storage
  REST (air-gapped: hard-disabled, checked at trigger AND at job run).
- 2026-08-08 (platform-control assistant, backend): D7-amendment implemented, 70 tests
  green. New `neurai/platform_ops.py` — shared core for REST admin API AND skills
  (identical checks, D12 chain in one path; admin.py/documents.py now delegate).
  Skills (skills/platform.py): get_status (read-only), delete_meeting, delete_document
  (owner-or-admin), set_asr_device, set_setting, trigger_backup — admin manifests
  enforced in the runtime with unknown-skill-shaped denial (not probeable, audit
  records truth), all mutating skills behind the rule-2 confirmation card, admin
  tools hidden from non-admin tool loops. Persian intent patterns for delete/device/
  status/backup phrasings. No new REST endpoints (rides chat + /confirm);
  openapi.json regenerated (admin/status response gained fields).
  closed — (1) D7 rule 3: runtime now strips `allow_cloud` from skills whose manifest
  lacks `llm:cloud` (enforced), docstring rewritten to state exactly what's enforced vs
  declarative-until-third-party-skills; (2) fa_normalize applied on document ingest and
  on search queries (Arabic ي/ك queries now match normalized chunks — tested); (3)
  minutes/export meeting read is owner-scoped; (4) `POST /api/auth/change-password`
  added — revokes all sessions, re-issues the caller's (D8). 45 tests green,
  openapi.json regenerated (webui session: one new auth endpoint).
