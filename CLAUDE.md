# NeurAI — session guide

NeurAI is a Persian-first, offline-capable, on-premise AI meeting-assistant platform
(FastAPI server on Windows + browser clients over LAN). Early build phase: the server
engine (`server/`) and webui (`webui/`) skeletons exist; models are not wired yet.

## Source of truth

**[ARCHITECTURE.md](ARCHITECTURE.md) is the single source of truth for all technical
decisions.** Read it before designing or implementing anything. README.md is the public
summary and must be kept in sync with it.

## Rules for every session

1. **Do not contradict locked decisions** (D1–D10 and the §6 decision log) in code or docs.
   If a decision seems wrong while implementing, do not silently deviate — surface it to
   the user and, if they agree, amend ARCHITECTURE.md first (mark the change `[REVISED]`,
   update the §6 decision log), then implement.
2. **New architectural choices get numbered decisions.** Anything that constrains future
   work (library choice with lock-in, schema design, protocol, security mechanism) goes
   into ARCHITECTURE.md as `D8`, `D9`, … with a short rationale — before or alongside the
   code, not after.
3. **Security invariants are non-negotiable** (see D7 and §2.1):
   - Audio never leaves the server, in any mode.
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
