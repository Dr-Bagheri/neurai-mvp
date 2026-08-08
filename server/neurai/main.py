"""NeurAI server entry point — FastAPI app factory (D1).

The engine owns everything: API, WebSockets, job worker, and serving the
built webui bundle. `neurai-server` (console script) runs it under uvicorn;
the Windows service installer wraps the same entry point.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from neurai import __version__
from neurai.config import get_config

log = logging.getLogger("neurai")


def _register_job_handlers() -> None:
    from neurai.audio.quality_pass import run_quality_pass
    from neurai.jobs import get_job_queue
    from neurai.rag.ingest import index_document_job, index_transcript_job

    queue = get_job_queue()
    queue.register("quality_pass", run_quality_pass)
    queue.register("index_transcript", index_transcript_job)
    queue.register("index_document", index_document_job)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from neurai.audio import get_session_manager
    from neurai.db import get_db
    from neurai.jobs import get_job_queue

    cfg = get_config()
    cfg.ensure_dirs()
    get_db()  # opens + migrates

    _register_job_handlers()
    queue = get_job_queue()
    # §4: heavy jobs yield to a live meeting
    queue.live_meeting_active = get_session_manager().any_live
    await queue.start()
    log.info("NeurAI server %s ready (profile=%s)", __version__, cfg.connectivity_profile)
    yield
    await queue.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="NeurAI",
        version=__version__,
        description="Persian-first, offline-capable meeting intelligence server",
        lifespan=_lifespan,
    )

    from neurai.api import action_items, admin, auth, chat, documents, meetings, search, ws

    app.include_router(auth.router)
    app.include_router(meetings.router)
    app.include_router(meetings.series_router)
    app.include_router(chat.router)
    app.include_router(action_items.router)
    app.include_router(documents.router)
    app.include_router(search.router)
    app.include_router(admin.router)
    app.include_router(ws.router)

    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__}

    # Serve the webui bundle if it has been built (zero client install — D1).
    webui = get_config().webui_dir
    if webui.is_dir() and (webui / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=webui / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith(("api/", "ws/")):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            candidate = (webui / path).resolve()
            if path and candidate.is_file() and webui.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(webui / "index.html")

    return app


def run() -> None:
    import uvicorn

    cfg = get_config()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    run()
