# NeurAI Web UI

The browser client from [ARCHITECTURE.md](../ARCHITECTURE.md) D1/D5: **React + TypeScript,
RTL-first, Persian-first**, built with Vite and served by the FastAPI engine as a static
bundle in production.

## Run

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check + production bundle in dist/
```

## Current state: UI complete, engine mocked

The server does not exist yet, so the UI runs against an in-browser mock engine:

- `src/api/types.ts` — mirrors the future FastAPI/Pydantic schema (snake_case fields).
  Once the server exists these types are replaced by `openapi-typescript` output (D6).
- `src/api/client.ts` — the **only** place the UI gets data. Each function body becomes a
  `fetch("/api/…")` call later; pages don't change.
- `src/api/mock.ts` — demo data (Persian meetings, transcripts, action items, audit log)
  and canned skill-driven chat answers.

`vite.config.ts` already proxies `/api` and `/ws` to `127.0.0.1:8321` for when the engine
arrives.

## What's implemented

| Screen | Architecture feature |
|---|---|
| Login | local accounts on the office server (D1) |
| جلسه‌ها (dashboard) | meeting archive, series detection, status/capture-mode/local-only badges |
| جلسهٔ زنده | capture-mode picker (room-mic / per-participant), enrollment round, local-only flag, **«محرمانه» sensitivity level** (D4 — forces local-only, excluded from search/backup), simulated live captions, در-جلسه bookmarks (`Ctrl+B`), meeting notepad (D2) |
| Meeting detail | audio-linked playback (simulated player), diarized transcript, click-to-seek, **manual speaker relabel**, summary + مصوبات with 🏠/☁️ provenance, صورتجلسه preview + Word/PDF/SRT export buttons, notes with merge-notes hook (D2/D5) |
| دستیار (chat) | skill chips (tool-use loop), 🏠/☁️ badge per answer, source citations, **confirmation gate for side-effectful skills** (D7 rule 2) |
| جستجو | cross-meeting transcript search (D7 `search_transcripts`) |
| کارها | action-item tracker: live status objects, overdue flags, resurfacing note |
| اسناد | RAG document list + local-retrieval explanation |
| مدیریت سرور | connectivity profile (auto / air-gapped), per-workspace cloud consent, **D9 health page** (RAM, disk usage + fill projection, model status, last-error log, job queue), **retention policy settings** (D4), **append-only skill audit log** (§2.1, D7 rule 5) |
| تنظیمات | Persian digits toggle, dark theme, voice-profile management (D2) |

Persian-first details (D5): `dir="rtl"` at the root (LTR is per-element the exception),
Vazirmatn (bundled locally — no CDN, works air-gapped), Jalali dates everywhere
(`src/lib/jalali.ts`, dependency-free), Persian-digit rendering behind a user setting.
