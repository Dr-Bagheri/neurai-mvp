"""Background job queue (§4).

Rules encoded here, per the capacity plan:
- The live meeting gets priority: heavy jobs (quality pass, LLM summarization,
  indexing) do not start while a meeting is live; they wait in the queue.
- One worker — the 16 GB baseline runs one heavy thing at a time.
- Jobs are persisted in SQLite so a service restart resumes the queue.

Handlers are registered by name; payloads are JSON.
"""
from __future__ import annotations

import asyncio
import json
import logging
import traceback
from typing import Any, Awaitable, Callable

from neurai.db import get_db

log = logging.getLogger("neurai.jobs")

Handler = Callable[[dict[str, Any]], Awaitable[None]]

# Jobs that must yield to a live meeting.
HEAVY_KINDS = {"quality_pass", "summarize_meeting", "index_transcript", "index_document"}

_POLL_INTERVAL_S = 1.5


class JobQueue:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._stopping = False
        # set by the live session manager; checked before heavy jobs start
        self.live_meeting_active: Callable[[], bool] = lambda: False

    def register(self, kind: str, handler: Handler) -> None:
        self._handlers[kind] = handler

    def enqueue(self, kind: str, payload: dict[str, Any], priority: int = 5) -> int:
        job_id = get_db().insert(
            "INSERT INTO jobs(kind, payload, priority) VALUES(?,?,?)",
            (kind, json.dumps(payload, ensure_ascii=False), priority),
        )
        self._wake.set()
        return job_id

    # -- worker ---------------------------------------------------------------

    async def start(self) -> None:
        # Recover jobs that were mid-flight when the service stopped.
        get_db().execute("UPDATE jobs SET status='queued' WHERE status='running'")
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="neurai-job-worker")

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def _next_job(self):
        db = get_db()
        row = db.query_one(
            "SELECT * FROM jobs WHERE status='queued' ORDER BY priority, id LIMIT 1"
        )
        if row and row["kind"] in HEAVY_KINDS and self.live_meeting_active():
            return None  # wait for the meeting to end
        return row

    async def _run(self) -> None:
        db = get_db()
        while not self._stopping:
            row = self._next_job()
            if row is None:
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=_POLL_INTERVAL_S)
                except asyncio.TimeoutError:
                    pass
                continue

            job_id, kind = row["id"], row["kind"]
            handler = self._handlers.get(kind)
            db.execute(
                "UPDATE jobs SET status='running', started_at=datetime('now') WHERE id=?",
                (job_id,),
            )
            if handler is None:
                db.execute(
                    "UPDATE jobs SET status='failed', error=?, finished_at=datetime('now') WHERE id=?",
                    (f"no handler for kind '{kind}'", job_id),
                )
                continue
            try:
                await handler(json.loads(row["payload"]))
                db.execute(
                    "UPDATE jobs SET status='done', finished_at=datetime('now') WHERE id=?",
                    (job_id,),
                )
            except Exception as e:  # job failures must never kill the worker
                log.error("job %s (%s) failed: %s\n%s", job_id, kind, e, traceback.format_exc())
                db.execute(
                    "UPDATE jobs SET status='failed', error=?, finished_at=datetime('now') WHERE id=?",
                    (str(e)[:2000], job_id),
                )

    def notify(self) -> None:
        """Wake the worker (e.g. when a live meeting ends)."""
        self._wake.set()


_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = JobQueue()
    return _queue
