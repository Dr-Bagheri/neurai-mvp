"""Quality pass job (D2): full recording → large model → diarization →
Persian post-processing → authoritative transcript replaces the live one."""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from neurai.db import get_db
from neurai.fa import fa_normalize

from .asr import get_quality_engine
from .diarization import assign_speakers, get_diarizer


async def run_quality_pass(payload: dict[str, Any]) -> None:
    import asyncio

    meeting_id = int(payload["meeting_id"])
    db = get_db()
    meeting = db.query_one("SELECT * FROM meetings WHERE id=?", (meeting_id,))
    if meeting is None:
        return
    wav_path = meeting["audio_path"]
    if not wav_path or not Path(wav_path).exists():
        db.execute("UPDATE meetings SET status='failed' WHERE id=?", (meeting_id,))
        raise RuntimeError(f"recording missing for meeting {meeting_id}")

    with wave.open(wav_path, "rb") as w:
        pcm = w.readframes(w.getnframes())

    engine = get_quality_engine()
    segments = await asyncio.to_thread(engine.transcribe, pcm, 0, meeting["language"])

    # Diarize (room mode). Per-participant mode gets exact labels at capture
    # time, so diarization is skipped.
    if meeting["capture_mode"] == "room":
        turns = await asyncio.to_thread(get_diarizer().diarize, wav_path)
        for seg in segments:
            seg.speaker_label = "S1"  # default when diarizer returns nothing
        if turns:
            assign_speakers(segments, turns)
    else:
        for seg in segments:
            seg.speaker_label = None

    # Replace the rough live transcript with the authoritative one.
    db.execute(
        "DELETE FROM transcript_segments WHERE meeting_id=? AND pass='quality'",
        (meeting_id,),
    )
    for seg in segments:
        db.execute(
            "INSERT INTO transcript_segments(meeting_id, pass, start_ms, end_ms, speaker_label, text) "
            "VALUES(?,?,?,?,?,?)",
            (
                meeting_id, "quality", seg.start_ms, seg.end_ms,
                getattr(seg, "speaker_label", None),
                fa_normalize(seg.text) if meeting["language"] == "fa" else seg.text,
            ),
        )
    db.execute("UPDATE meetings SET status='done' WHERE id=?", (meeting_id,))

    # Index the final transcript for RAG / cross-meeting search.
    from neurai.jobs import get_job_queue

    get_job_queue().enqueue("index_transcript", {"meeting_id": meeting_id}, priority=6)
