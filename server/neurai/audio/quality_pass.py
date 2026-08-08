"""Quality pass job (D2 v0.3): the single transcription pass, GPU-first,
with percent progress.

Per registered mic: decrypt recording → faster-whisper → segments labeled
with the mic's user-chosen name (named multi-mic). Room-mode meetings with a
single mic run diarization afterwards (sequenced — ASR then diarization so
both fit 4 GB VRAM in turn, D14); the diarizer labels (S1…) override the mic
name there since one mic heard several people.

Progress: fraction of total recorded audio consumed across all mics,
persisted on the job row (jobs.progress 0–100) — the meeting page polls
GET /api/meetings/{id}/progress.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from neurai.db import get_db
from neurai.fa import fa_normalize

from .asr import SAMPLE_RATE, get_quality_engine
from .diarization import assign_speakers, get_diarizer


async def run_quality_pass(payload: dict[str, Any]) -> None:
    import asyncio

    from neurai.jobs import get_job_queue
    from neurai.security.audiocrypt import pcm_size, read_pcm

    meeting_id = int(payload["meeting_id"])
    job_id = payload.get("_job_id")
    db = get_db()
    meeting = db.query_one("SELECT * FROM meetings WHERE id=?", (meeting_id,))
    if meeting is None:
        return

    mics = [
        m for m in db.query(
            "SELECT * FROM meeting_mics WHERE meeting_id=? ORDER BY id", (meeting_id,),
        )
        if m["audio_path"] and Path(m["audio_path"]).exists() and pcm_size(m["audio_path"]) > 0
    ]
    if not mics:
        db.execute("UPDATE meetings SET status='failed' WHERE id=?", (meeting_id,))
        raise RuntimeError(f"no recordings for meeting {meeting_id}")

    queue = get_job_queue()
    total_bytes = sum(pcm_size(m["audio_path"]) for m in mics)
    done_bytes = 0
    last_pct = -1

    def report(mic_bytes: int, fraction: float) -> None:
        nonlocal last_pct
        if job_id is None or total_bytes == 0:
            return
        pct = int((done_bytes + fraction * mic_bytes) * 100 / total_bytes)
        if pct != last_pct:
            last_pct = pct
            queue.set_progress(job_id, pct)

    all_segments: list[tuple[Any, str | None]] = []  # (segment, speaker_label)
    single_room_mic = meeting["capture_mode"] == "room" and len(mics) == 1

    # D15 cloud ASR — only in online mode + explicit per-meeting consent +
    # provider configured; re-checked HERE (mode may have changed since the
    # opt-in). Every use is D12-chained; ANY failure falls back to the local
    # GPU pass — a transcript is never lost to a cloud error.
    async def _transcribe_mics(transcriber) -> list[tuple[Any, str | None]]:
        nonlocal done_bytes
        done_bytes = 0
        collected: list[tuple[Any, str | None]] = []
        for mic in mics:
            pcm = read_pcm(mic["audio_path"])
            mic_bytes = len(pcm)
            segments = await transcriber(pcm, mic_bytes)
            label = None if single_room_mic else mic["name"]
            collected.extend((seg, label) for seg in segments)
            done_bytes += mic_bytes
            report(0, 0.0)  # refresh percent at mic boundaries
        return collected

    used_cloud = False
    if bool(meeting["cloud_transcribe"]):
        from neurai.harness import connectivity

        from . import cloud_asr

        if connectivity.is_online_mode() and cloud_asr.provider_config() is not None:
            from neurai.security import adminlog

            try:
                async def cloud_transcriber(pcm, mic_bytes):
                    segs = await cloud_asr.transcribe_cloud(pcm, meeting["language"])
                    report(mic_bytes, 1.0)
                    return segs

                all_segments = await _transcribe_mics(cloud_transcriber)
                used_cloud = True
                adminlog.append("system", "cloud_asr_used", {
                    "meeting_id": meeting_id, "provider": cloud_asr.provider_host(),
                    "ok": True,
                })
            except Exception as e:
                adminlog.append("system", "cloud_asr_used", {
                    "meeting_id": meeting_id, "provider": cloud_asr.provider_host(),
                    "ok": False,
                })
                import logging

                logging.getLogger("neurai.audio").warning(
                    "cloud ASR failed for meeting %s (%s) — falling back to local pass",
                    meeting_id, e,
                )

    if not used_cloud:
        engine = get_quality_engine()

        async def local_transcriber(pcm, mic_bytes):
            return await asyncio.to_thread(
                engine.transcribe, pcm, 0, meeting["language"],
                lambda frac, mb=mic_bytes: report(mb, frac),
            )

        all_segments = await _transcribe_mics(local_transcriber)

    if single_room_mic:
        segs_only = [seg for seg, _ in all_segments]
        for seg in segs_only:
            seg.speaker_label = "S1"  # default when the diarizer yields nothing
        turns = await asyncio.to_thread(get_diarizer().diarize, mics[0]["audio_path"])
        if turns:
            assign_speakers(segs_only, turns)
        all_segments = [(seg, seg.speaker_label) for seg in segs_only]

    db.execute("DELETE FROM transcript_segments WHERE meeting_id=? AND pass='quality'",
               (meeting_id,))
    for seg, label in sorted(all_segments, key=lambda pair: pair[0].start_ms):
        db.execute(
            "INSERT INTO transcript_segments(meeting_id, pass, start_ms, end_ms, speaker_label, text) "
            "VALUES(?,?,?,?,?,?)",
            (
                meeting_id, "quality", seg.start_ms, seg.end_ms, label,
                fa_normalize(seg.text) if meeting["language"] == "fa" else seg.text,
            ),
        )
    db.execute("UPDATE meetings SET status='done' WHERE id=?", (meeting_id,))
    if job_id is not None:
        queue.set_progress(job_id, 100)

    # Index the final transcript for RAG / cross-meeting search.
    get_job_queue().enqueue("index_transcript", {"meeting_id": meeting_id}, priority=6)
