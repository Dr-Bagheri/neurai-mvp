# NeurAI

**دستیار هوش مصنوعی فارسی‌محور، چندکاره و آفلاین** — a Persian-first, offline-capable,
multi-task AI assistant platform for teams, deployed on-premise.

- 🎙️ **Live meeting transcription** in Persian — live captions during the meeting, a
  full-quality transcript with speaker labels minutes after it ends. Fully offline.
  Click any sentence to hear that moment; bookmark key moments live.
- 🧠 **Meeting intelligence** — summaries, decisions, and a live **action-item tracker**
  (assignees, due dates, resurfacing in recurring meetings); cross-meeting search and
  "since last time" recaps
- 📋 **صورتجلسه رسمی** — formal Iranian minutes templates with گفتاری→نوشتاری register
  conversion, Word/PDF export, Jalali dates
- 💬 **Persian chat assistant** and 📄 **document Q&A (RAG)** over your own files
- 🛠️ **Skills (AI-native):** ask in plain Persian — «جلسه دیروز رو خلاصه کن» — and the
  assistant calls the right tools itself; every call runs with *your* permissions, on an
  audited, locked-down skill runtime
- 🏠 **Local-first:** one server on your office network, used from any browser on the LAN;
  runs air-gapped with local models (faster-whisper, Ollama)
- ☁️ **Cloud-enhanced (opt-in):** frontier models via OpenRouter when online and explicitly
  enabled, with automatic fallback to local
- 🔌 **True dual-mode:** one architecture, two runtime profiles — every feature works
  offline; cloud only upgrades text tasks under consent, and audio never leaves the server
  in any mode (admin can lock the server to a fully air-gapped profile)
- 🔄 Optional encrypted snapshot backup — off by default, never required
- 🔒 **Hardened by default:** encrypted at rest, crash-safe recording, signed offline
  updates for air-gapped servers, per-meeting «محرمانه» sensitivity levels — and
  **no telemetry, ever**

## Screenshots

The web UI (RTL-first, Vazirmatn, Jalali dates), running against the demo data set:

| Meetings archive | Meeting transcript |
|---|---|
| ![Meetings dashboard — Jalali dates, capture modes, local-only and confidential badges](docs/screenshots/shot-dashboard.png) | ![Meeting page — speaker-labeled transcript with audio-linked playback](docs/screenshots/shot-meeting.png) |

| Live meeting | Persian chat assistant |
|---|---|
| ![Live meeting — real-time captions with bookmarks](docs/screenshots/shot-live.png) | ![Chat assistant — skills with provenance badges](docs/screenshots/shot-chat.png) |

| Action-item tracker | Admin dashboard |
|---|---|
| ![Action items — assignees, due dates, status](docs/screenshots/shot-actions.png) | ![Admin — job queue, models, connectivity profile](docs/screenshots/shot-admin.png) |

## Architecture at a glance

One on-premise server, browser clients on the LAN, local models by default, cloud as a
consent-gated upgrade. Full detail with all locked decisions (D1–D11):
**[ARCHITECTURE.md](ARCHITECTURE.md)**.

```mermaid
flowchart TB
    Browsers["Team browsers (LAN)<br/>React + TS, RTL-first<br/>mic over WebSocket"]

    subgraph Server["Office server — Windows, 16 GB baseline"]
        API["FastAPI — auth, jobs, UI"]
        SK["Skill Runtime<br/>ACLs · confirmation gate · audit log"]
        H["Model Harness<br/>routing · fallback · chunking · tool loop"]
        AP["Audio Pipeline<br/>VAD → live ASR → quality ASR → diarization → fa post-processing"]
        DL["SQLite (SQLCipher)<br/>encrypted at rest, per-user scoping"]
        LM["Local models<br/>faster-whisper · Ollama ~8B · BGE-M3"]
    end

    Cloud["Cloud (optional)<br/>OpenRouter LLMs · Supabase encrypted backup"]

    Browsers --> API --> SK --> H --> LM
    API --> AP --> LM
    SK --> DL
    H -. "consent-gated, text only —<br/>audio never leaves the server" .-> Cloud
    DL -. "encrypted snapshots (opt-in)" .-> Cloud
```

## Repository layout

| Path | Contents |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Single source of truth — all decisions (D1–D11), threat model, roadmap |
| [`server/`](server/) | Python FastAPI engine: audio pipeline, model harness, skills runtime, RAG, auth, SQLite layer, tests |
| [`webui/`](webui/) | React + TypeScript client (Vite) — served by the engine in production |
| [`docs/`](docs/) | Screenshots, benchmark results (Phase 0), ADRs |
| [`CLAUDE.md`](CLAUDE.md) | Working agreement for the parallel AI sessions building this project |
| [`.github/workflows/`](.github/workflows/) | CI — offline test suite (encryption active, fake ASR engine); lint + Persian eval set with network blocked planned |

## Try the UI demo

The web UI runs standalone against mock data (no models needed):

```bash
npm install --prefix webui
npm run dev --prefix webui
```

Open http://localhost:5173 — sign in with any username/password (demo mode).

## Status

🚧 **Design locked (v0.2), build started.** The architecture is in
[ARCHITECTURE.md](ARCHITECTURE.md). Key decisions: on-premise server + browser clients,
two-pass live transcription, 16 GB no-GPU baseline, Windows-first.

The **web UI is built** ([`webui/`](webui/)): React + TypeScript, RTL-first, Vazirmatn,
Jalali dates — all MVP screens (live meeting, transcript + playback, chat with skills and
the confirmation gate, action items, RAG, admin) running against a typed mock of the
FastAPI engine. See [webui/README.md](webui/README.md).

The **server engine is built** ([`server/`](server/)): auth/sessions (argon2id + lockout),
versioned SQL migrations, crash-safe two-pass audio pipeline (pluggable ASR), consent-gated
model harness with cloud→local fallback, Skill Runtime (ACLs, confirmation gate, audit),
owner-scoped RAG, صورتجلسه/SRT export, job queue, and admin API. Encryption at rest is
default-on: SQLCipher database + sealed AES-256-CTR recordings (D11). 41 offline tests
green; OpenAPI contract exported to `webui/openapi.json`. See [server/README.md](server/README.md).

## Stack

| Layer | Technology |
|---|---|
| Server | Python FastAPI — ASR, harness, RAG, auth. Windows: full one-click installer (service). Linux: Docker Compose |
| Clients | Browser (React + TypeScript, RTL-first) · Tauri thin client later |
| Speech | faster-whisper two-pass (live small model → quality Persian large-v3) + local diarization |
| Local LLMs | Ollama (Qwen3 / Gemma / Aya, ~8B q4 on baseline) |
| Cloud LLMs | OpenRouter (opt-in, consent-gated) |
| Storage | SQLite (SQLCipher) + local vector search on the server · optional encrypted Supabase backup |

## License

[Apache-2.0](LICENSE).
