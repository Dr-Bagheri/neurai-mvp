# NeurAI

**دستیار هوش مصنوعی فارسی‌محور، چندکاره و آفلاین** — a Persian-first, offline-capable,
multi-task AI assistant platform.

- 🎙️ **Meeting transcription** in Persian — fully offline, with speaker labels
- 🧠 **Meeting intelligence** — summaries, action items, decisions
- 💬 **Persian chat assistant** and 📄 **document Q&A (RAG)** over your own files
- 🏠 **Local-first:** runs air-gapped with local models (faster-whisper, Ollama)
- ☁️ **Cloud-enhanced:** automatically uses frontier models via OpenRouter (MiniMax M3, …) when online, with graceful fallback to local
- 🔄 Optional Supabase sync/backup — off by default, never required

## Status

🚧 **Design phase.** The full proposed architecture is in [ARCHITECTURE.md](ARCHITECTURE.md)
and is currently under discussion. No code yet — decisions first.

## Planned stack

| Layer | Technology |
|---|---|
| Desktop shell | Tauri 2 + React + TypeScript (RTL-first UI) |
| AI engine | Python (FastAPI sidecar): faster-whisper, diarization, RAG |
| Local LLMs | Ollama (Qwen3 / Gemma / Aya) |
| Cloud LLMs | OpenRouter (MiniMax M3 default) |
| Storage | SQLite + sqlite-vec (local) · Supabase (optional sync) |

## License

TBD (MIT proposed).
