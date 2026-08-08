"""Live meeting sessions (Phase 1 core).

One `LiveSession` per live meeting: receives PCM16@16k chunks from the
browser WebSocket, appends them to the recording (kept for audio-linked
playback), runs the live ASR pass on utterance boundaries, stores live
segments, and broadcasts captions to subscribed viewers.

Crash-safe recording (D2 invariant): chunks are appended to a raw `.pcm`
file and fsynced as they arrive — a server crash never loses meeting audio.
The playable `.wav` (fixed 44-byte header + the same PCM) is finalized on
stop; `recover_orphaned_recordings()` finalizes any `.pcm` left behind by a
crash at next startup and queues its quality pass.

`LiveSessionManager` enforces the concurrency cap (§4): starting a second
meeting while one is live is refused with «جلسه‌ای در حال ضبط است» — a config
cap, not an architectural limit.
"""
from __future__ import annotations

import asyncio
import os
import re
import struct
from pathlib import Path
from typing import Any

from neurai.config import get_config
from neurai.db import get_db
from neurai.fa import fa_normalize

from .asr import SAMPLE_RATE, get_live_engine
from .vad import trailing_silence_ms

# Endpointing: transcribe on ≥700 ms trailing silence, or force a pass when
# the pending buffer reaches 15 s (keeps latency bounded on continuous speech).
_SILENCE_TRIGGER_MS = 700
_MAX_WINDOW_MS = 15_000
_MIN_BUFFER_MS = 1_000

_BYTES_PER_MS = SAMPLE_RATE * 2 // 1000


class MeetingBusyError(Exception):
    """Raised when the live-meeting cap is reached."""

    message_fa = "جلسه‌ای در حال ضبط است"


def _write_wav_from_pcm(pcm_path: Path, wav_path: Path) -> None:
    """Wrap a raw PCM16@16k mono file in a WAV container (streamed copy)."""
    data_size = pcm_path.stat().st_size
    byte_rate = SAMPLE_RATE * 2
    header = (
        b"RIFF" + struct.pack("<I", 36 + data_size) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, byte_rate, 2, 16)
        + b"data" + struct.pack("<I", data_size)
    )
    with open(wav_path, "wb") as out, open(pcm_path, "rb") as src:
        out.write(header)
        while True:
            block = src.read(1 << 20)
            if not block:
                break
            out.write(block)


class LiveSession:
    def __init__(self, meeting_id: int, owner_id: int, wav_path: Path):
        self.meeting_id = meeting_id
        self.owner_id = owner_id
        self.wav_path = wav_path
        self.pcm_path = wav_path.with_suffix(".pcm")
        # append mode: a reconnecting session after a dropped WS keeps the audio
        self._pcm = open(self.pcm_path, "ab")
        self._buffer = bytearray()
        self._written_ms = 0          # audio written to disk so far
        self._buffer_start_ms = 0     # meeting-time offset of buffer[0]
        self._subscribers: set[asyncio.Queue] = set()
        self._closed = False
        self._asr_lock = asyncio.Lock()

    # -- caption fan-out ------------------------------------------------------

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    def _broadcast(self, event: dict[str, Any]) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # slow viewer: drop captions, never block the pipeline

    # -- audio ingest ---------------------------------------------------------

    async def feed(self, chunk: bytes) -> None:
        if self._closed:
            return
        # D2 invariant: audio hits disk as it arrives; fsync so a crash (or
        # power cut) never loses more than the in-flight chunk.
        self._pcm.write(chunk)
        self._pcm.flush()
        os.fsync(self._pcm.fileno())
        self._written_ms += len(chunk) // _BYTES_PER_MS
        self._buffer.extend(chunk)
        buffer_ms = len(self._buffer) // _BYTES_PER_MS
        if buffer_ms < _MIN_BUFFER_MS:
            return
        if buffer_ms >= _MAX_WINDOW_MS or trailing_silence_ms(bytes(self._buffer)) >= _SILENCE_TRIGGER_MS:
            pcm = bytes(self._buffer)
            offset = self._buffer_start_ms
            self._buffer.clear()
            self._buffer_start_ms = offset + buffer_ms
            await self._transcribe(pcm, offset)

    async def _transcribe(self, pcm: bytes, offset_ms: int) -> None:
        async with self._asr_lock:  # one live ASR call at a time (16 GB baseline)
            engine = get_live_engine()
            segments = await asyncio.to_thread(engine.transcribe, pcm, offset_ms)
        db = get_db()
        for seg in segments:
            text = fa_normalize(seg.text)
            if not text:
                continue
            seg_id = db.insert(
                "INSERT INTO transcript_segments(meeting_id, pass, start_ms, end_ms, text) "
                "VALUES(?,?,?,?,?)",
                (self.meeting_id, "live", seg.start_ms, seg.end_ms, text),
            )
            self._broadcast({
                "type": "caption",
                "segment_id": seg_id,
                "start_ms": seg.start_ms,
                "end_ms": seg.end_ms,
                "text": text,
            })

    async def finish(self) -> None:
        if self._closed:
            return
        self._closed = True
        # flush whatever speech is left in the buffer
        if len(self._buffer) // _BYTES_PER_MS >= _MIN_BUFFER_MS:
            await self._transcribe(bytes(self._buffer), self._buffer_start_ms)
        self._buffer.clear()
        self._pcm.close()
        _write_wav_from_pcm(self.pcm_path, self.wav_path)
        self.pcm_path.unlink(missing_ok=True)
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
            wav_path = cfg.recordings_dir / f"meeting_{meeting_id}.wav"
            session = LiveSession(meeting_id, owner_id, wav_path)
            self._sessions[meeting_id] = session
            db = get_db()
            db.execute(
                "UPDATE meetings SET status='live', started_at=datetime('now'), audio_path=? "
                "WHERE id=?",
                (str(wav_path), meeting_id),
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
        # Queue the quality pass (D2); the worker starts it now that no meeting is live.
        from neurai.jobs import get_job_queue

        queue = get_job_queue()
        queue.enqueue("quality_pass", {"meeting_id": meeting_id}, priority=2)
        queue.notify()


def recover_orphaned_recordings() -> list[int]:
    """Startup pass (D2): a crash mid-meeting leaves meeting_N.pcm behind.
    Finalize it into a playable WAV, mark the meeting for processing, and
    queue its quality pass — a server crash must never lose a meeting."""
    from neurai.jobs import get_job_queue

    cfg = get_config()
    db = get_db()
    recovered: list[int] = []
    for pcm_path in sorted(cfg.recordings_dir.glob("meeting_*.pcm")):
        m = re.match(r"meeting_(\d+)\.pcm$", pcm_path.name)
        if not m:
            continue
        meeting_id = int(m.group(1))
        wav_path = pcm_path.with_suffix(".wav")
        if pcm_path.stat().st_size == 0:
            pcm_path.unlink(missing_ok=True)
            continue
        _write_wav_from_pcm(pcm_path, wav_path)
        pcm_path.unlink(missing_ok=True)
        db.execute(
            "UPDATE meetings SET status='processing', audio_path=?, "
            "ended_at=COALESCE(ended_at, datetime('now')) WHERE id=?",
            (str(wav_path), meeting_id),
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
