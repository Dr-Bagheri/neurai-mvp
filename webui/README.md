# NeurAI Web UI

The browser client from [ARCHITECTURE.md](../ARCHITECTURE.md) D1/D5: **React + TypeScript,
RTL-first, Persian-first**, built with Vite and served by the FastAPI engine as a static
bundle in production. **Wired to the real server API** — no mock layer.

## Run (development)

```bash
# 1. start the engine (default port 8471)
cd ../server && .venv/Scripts/python -m neurai.main

# 2. start the UI dev server (proxies /api and /ws to 127.0.0.1:8471)
npm install
npm run dev      # http://localhost:5173
```

Production: `npm run build` → the engine serves `dist/` itself (D1, zero client install).

## API contract (D6)

- [`openapi.json`](openapi.json) is exported from the live server schema.
- `src/api/schema.d.ts` is **generated** from it: `npm run gen:api` — rerun whenever the
  server schema changes; never edit by hand.
- [`src/api/types.ts`](src/api/types.ts) re-exports the generated models and hand-types
  the endpoints the server returns as plain dicts (typed against
  `server/neurai/api/*.py` — keep in sync).
- [`src/api/client.ts`](src/api/client.ts) is the only fetch surface; FastAPI's Persian
  `detail` messages surface directly in the UI via `ApiError`.

## What's implemented (all against the real API)

| Screen | Wiring |
|---|---|
| First run | `GET /api/auth/status` → setup page → `POST /api/auth/setup` (admin account) |
| Login / session | `POST /api/auth/login`, cookie restore via `GET /api/auth/me`, logout |
| جلسه‌ها (one Meetings section — v0.3) | live-meeting controls on top, records under (`GET /api/meetings` + `GET /api/series`); the old `/live` route redirects here. **No live captions (D2 v0.3):** setup (title, capture mode, **named mics** via `POST /api/meetings/{id}/mics` — «میکروفون میز جلسه», «لپ‌تاپ سارا», flags) → recording (mic list, bookmarks `Ctrl+B`, timestamped notepad; audio as PCM16@16kHz over `/ws/meetings/{id}/audio` per mic) → processing with a **percent progress bar** (`GET /api/meetings/{id}/progress`); series pick shows **resurfaced open action items** |
| Meeting detail | transcript (`/transcript`, quality pass wins; mic tags flow into speaker labels), **real `<audio>`** on the Range-seekable `/audio` WAV (click a sentence to seek), processing state shows the same % progress, manual speaker relabel (`/speakers/relabel`), summaries (`/summaries`) with 🏠/☁️ badges, timestamped notes |
| دستیار (global panel + archive page) | the assistant is a **persistent panel docked at the physical LEFT edge** of the RTL shell, present on every route, collapsible (open by default; state remembered). `/chat` remains the full-page archive of the same conversation — state is shared via `ChatContext`, so switching surfaces never loses history or an in-flight generation. Features on both surfaces: intent-router chips, 🏠/☁️ source badge, provenance citations, cloud-fallback marker, the **D7 confirmation gate** (deletion-type skills get explicit **destructive styling**), and the **stop button** («■ توقف» → `POST /cancel`, rendered as the stored «⏹ تولید پاسخ متوقف شد.» state). After a confirmed side-effectful skill, a `mutationCounter` bump makes open pages (admin, dashboard) refetch so the UI reflects what the assistant just did. The allow-cloud toggle is always visible and self-disables with the reason from `GET /api/cloud` |
| جستجو (top bar — v0.3) | search moved into the top bar on every page; submits to the `/search` results page (`POST /api/search` — semantic, transcript/document filter, score shown) |
| گزارش‌ها (Logs — new v0.3) | one menu item consolidating the job queue (`/api/admin/jobs`), the append-only skill audit (`/api/admin/audit`), and **گزارش امنیتی** — the D12 hash-chained audit file with a chain-integrity badge (`/audit-file`, `/audit-file/verify`) |
| کارها | `GET/PATCH /api/action-items` (open/done/dropped) |
| اسناد | upload (`POST /api/documents`, PDF/TXT/MD ≤50 MB), status chips, true-delete |
| مدیریت سرور | `GET/PUT /api/admin/settings` + the **D15 Offline/Online switch** (`GET/PUT /api/admin/mode` — Online disabled with the reason when the internet is unreachable or air-gapped), `/status`, `/users` + create user; **write-only cloud credential fields** (OpenRouter + Supabase + **cloud-ASR provider** — server never returns values) + «پشتیبان‌گیری ابری» backup-now button; **meeting archive across all users** with typed-confirmation true-delete. The cpu/cuda/auto compute dropdown is gone — compute is GPU-first with silent CPU fallback, no setting (D13 v0.3). Meeting setup carries the explicit per-meeting **«رونویسی ابری» consent** (D15) — disabled for «محرمانه» meetings, which refuse cloud ASR absolutely |
| تنظیمات | Persian digits, dark theme, change password (revokes other sessions — D8) |

Persian-first details (D5): `dir="rtl"` at the root, Vazirmatn bundled locally (no CDN —
works air-gapped), Jalali dates everywhere (`src/lib/jalali.ts`, dependency-free),
Persian-digit rendering behind a user setting.

## Known gaps (server-side, tracked for the steward)

- **Relabel-of-a-relabel:** `/transcript` returns display names, so a second rename of the
  same speaker sends the display name as `label`, which no longer matches the raw
  `speaker_label`. Needs the raw label in `SegmentOut` (or relabel-by-display-name
  server-side).
- The D9 health extras (disk projection, model load state, error log) and D4 retention
  settings have no admin endpoints yet; the admin page shows what `/api/admin/*` provides.
- ~~Non-admin cloud readiness~~ closed: the chat allow-cloud toggle now reads
  `GET /api/cloud` (any authenticated user) and disables itself with the specific Persian
  reason (`air_gapped` / `cloud_disabled` / `no_api_key`); admin views keep the detailed
  `/api/admin/cloud-status`.
