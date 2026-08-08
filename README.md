# NeurAI

**دستیار هوش مصنوعی فارسی‌محور، چندکاره و آفلاین** — a Persian-first, offline-capable,
multi-task AI assistant platform for teams, deployed on-premise.

- 🎙️ **Live meeting transcription** in Persian — live captions during the meeting, a
  full-quality transcript with speaker labels minutes after it ends. Fully offline.
- 🧠 **Meeting intelligence** — summaries, action items, decisions
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

## Status

🚧 **Design locked (v0.2), build starting.** The architecture is in
[ARCHITECTURE.md](ARCHITECTURE.md). Key decisions: on-premise server + browser clients,
two-pass live transcription, 16 GB no-GPU baseline, Windows-first.

## Stack

| Layer | Technology |
|---|---|
| Server | Python FastAPI as a Windows service — ASR, harness, RAG, auth |
| Clients | Browser (React + TypeScript, RTL-first) · Tauri thin client later |
| Speech | faster-whisper two-pass (live small model → quality Persian large-v3) + local diarization |
| Local LLMs | Ollama (Qwen3 / Gemma / Aya, ~8B q4 on baseline) |
| Cloud LLMs | OpenRouter (opt-in, consent-gated) |
| Storage | SQLite + sqlite-vec on the server · optional encrypted Supabase backup |

## License

[Apache-2.0](LICENSE).
