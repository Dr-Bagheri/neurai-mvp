"""Live meeting sessions (D2 v0.3): recording only — no live ASR.

A meeting registers one or more **named microphones** (meeting_mics table);
each WS audio stream binds to a registered mic id and appends to that mic's
own encrypted crash-safe recording (`meeting_<id>_mic_<micid>.neura`, D11 —
chunks encrypted + fsynced on arrival, no finalization step). The mic's
user-chosen name flows to speaker labels in the quality pass.

The events WebSocket only carries lifecycle events now ({"type": "ended"});
transcription progress is polled via GET /api/meetings/{id}/progress.

`LiveSessionManager` enforces the concurrency cap (§4): starting a second
meeting while one is live is refused with «جلسه‌ای در حال ضبط است» — a config
cap, not an architectural limit.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("neurai.audio")

from neurai.config import get_config
from neurai.db import get_db

from .asr import SAMPLE_RATE

_BYTES_PER_MS = SAMPLE_RATE * 2 // 1000

DEFAULT_MIC_NAME = "میکروفون ۱"


class MeetingBusyError(Exception):
    """Raised when the live-meeting cap is reached."""

    message_fa = "جلسه‌ای در حال ضبط است"


class UnknownMicError(Exception):
    message_fa = "میکروفون ثبت نشده است"


class LiveSession:
    def __init__(self, meeting_id: int, owner_id: int):
        self.meeting_id = meeting_id
        self.owner_id = owner_id
        self._writers: dict[int, Any] = {}   # mic_id → EncryptedAudioWriter
        self._subscribers: set[asyncio.Queue] = set()
        self._closed = False

    # -- event fan-out (lifecycle only since v0.3) ----------------------------

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _broadcast(self, event: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    # -- audio ingest ----------------------------------------------------------

    def _writer_for(self, mic_id: int):
        writer = self._writers.get(mic_id)
        if writer is not None:
            return writer
        from neurai.security.audiocrypt import EncryptedAudioWriter

        db = get_db()
        mic = db.query_one(
            "SELECT * FROM meeting_mics WHERE id=? AND meeting_id=?",
            (mic_id, self.meeting_id),
        )
        if mic is None:
            raise UnknownMicError()
        cfg = get_config()
        path = Path(mic["audio_path"]) if mic["audio_path"] else (
            cfg.recordings_dir / f"meeting_{self.meeting_id}_mic_{mic_id}.neura"
        )
        writer = EncryptedAudioWriter(path)  # append mode: reconnects resume
        db.execute("UPDATE meeting_mics SET audio_path=? WHERE id=?", (str(path), mic_id))
        # meetings.audio_path points at the first mic's recording (playback default)
        db.execute(
            "UPDATE meetings SET audio_path=COALESCE(audio_path, ?) WHERE id=?",
            (str(path), self.meeting_id),
        )
        self._writers[mic_id] = writer
        return writer

    async def feed(self, mic_id: int, chunk: bytes) -> None:
        if self._closed:
            return
        # D2 invariant: audio hits disk (encrypted + fsynced) as it arrives;
        # a crash or power cut never loses more than the in-flight chunk.
        self._writer_for(mic_id).write(chunk)

    async def finish(self) -> None:
        if self._closed:
            return
        self._closed = True
        for writer in self._writers.values():
            writer.close()  # sealed as-is: no finalization step to lose
        self._writers.clear()
        self._broadcast({"type": "ended"})


class LiveSessionManager:
    def __init__(self) -> None:
        self._sessions: dict[int, LiveSession] = {}
        self._lock = asyncio.Lock()

    def any_live(self) -> bool:
        return bool(self._sessions)

    def get(self, meeting_id: int) -> LiveSession | None:
        return self._sessions.get(meeting_id)

    async def start(self, meeting_id: int, owner_id: int) -> LiveSession:
        cfg = get_config()
        async with self._lock:
            if meeting_id in self._sessions:
                return self._sessions[meeting_id]
            if len(self._sessions) >= cfg.max_live_meetings:
                raise MeetingBusyError()
            db = get_db()
            # a meeting always has at least one mic when recording starts
            if db.query_one("SELECT 1 FROM meeting_mics WHERE meeting_id=?", (meeting_id,)) is None:
                db.insert("INSERT INTO meeting_mics(meeting_id, name) VALUES(?,?)",
                          (meeting_id, DEFAULT_MIC_NAME))
            session = LiveSession(meeting_id, owner_id)
            self._sessions[meeting_id] = session
            db.execute(
                "UPDATE meetings SET status='live', started_at=datetime('now') WHERE id=?",
                (meeting_id,),
            )
            return session

    async def stop(self, meeting_id: int) -> None:
        async with self._lock:
            session = self._sessions.pop(meeting_id, None)
        if session is None:
            return
        await session.finish()
        db = get_db()
        db.execute(
            "UPDATE meetings SET status='processing', ended_at=datetime('now') WHERE id=?",
            (meeting_id,),
        )
        # Auto-queue the quality pass (D2 v0.3); it reports percent progress.
        from neurai.jobs import get_job_queue

        queue = get_job_queue()
        queue.enqueue("quality_pass", {"meeting_id": meeting_id}, priority=2)
        queue.notify()


def recover_crashed_meetings() -> list[int]:
    """Startup pass (D2): a meeting still marked 'live' means the server died
    mid-recording. Every mic recording on disk is already complete up to the
    crash (fsynced, no finalization step), so recovery is: flip to processing
    and queue the quality pass."""
    from neurai.jobs import get_job_queue
    from neurai.security.audiocrypt import pcm_size

    db = get_db()
    recovered: list[int] = []
    for row in db.query("SELECT id FROM meetings WHERE status='live'"):
        meeting_id = row["id"]
        mics = db.query(
            "SELECT audio_path FROM meeting_mics WHERE meeting_id=? AND audio_path IS NOT NULL",
            (meeting_id,),
        )
        has_audio = any(
            Path(m["audio_path"]).exists() and pcm_size(m["audio_path"]) > 0 for m in mics
        )
        if not has_audio:
            db.execute("UPDATE meetings SET status='failed' WHERE id=?", (meeting_id,))
            continue
        db.execute(
            "UPDATE meetings SET status='processing', "
            "ended_at=COALESCE(ended_at, datetime('now')) WHERE id=?",
            (meeting_id,),
        )
        get_job_queue().enqueue("quality_pass", {"meeting_id": meeting_id}, priority=2)
        recovered.append(meeting_id)
    return recovered


_manager: LiveSessionManager | None = None


def get_session_manager() -> LiveSessionManager:
    global _manager
    if _manager is None:
        _manager = LiveSessionManager()
    return _manager
