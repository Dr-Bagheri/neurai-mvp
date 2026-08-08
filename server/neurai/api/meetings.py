"""Meetings API: CRUD, live start/stop, transcript, relabel, bookmarks,
notes, audio playback (Range-capable), summaries, exports. All queries are
owner-scoped (D7 rule 1)."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from neurai.audio.session import MeetingBusyError, get_session_manager
from neurai.auth.deps import CurrentUser, current_user
from neurai.db import get_db

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


class MeetingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    capture_mode: str = Field(default="room", pattern="^(room|participants)$")
    language: str = Field(default="fa", pattern="^(fa|en)$")
    allow_cloud: bool = False
    series_id: int | None = None
    # D4 data lifecycle: «محرمانه» is local-only forever, excluded from
    # cross-meeting indexing; allow_cloud is forced off for it.
    sensitivity: str = Field(default="normal", pattern="^(normal|confidential)$")


class MeetingOut(BaseModel):
    id: int
    title: str
    capture_mode: str
    status: str
    language: str
    allow_cloud: bool
    sensitivity: str
    series_id: int | None
    started_at: str | None
    ended_at: str | None
    created_at: str


def _own_meeting(user: CurrentUser, meeting_id: int):
    row = get_db().query_one(
        "SELECT * FROM meetings WHERE id=? AND owner_id=?", (meeting_id, user.id),
    )
    if row is None:
        raise HTTPException(404, "جلسه پیدا نشد")
    return row


def _to_out(row) -> MeetingOut:
    return MeetingOut(
        id=row["id"], title=row["title"], capture_mode=row["capture_mode"],
        status=row["status"], language=row["language"],
        allow_cloud=bool(row["allow_cloud"]), sensitivity=row["sensitivity"],
        series_id=row["series_id"],
        started_at=row["started_at"], ended_at=row["ended_at"], created_at=row["created_at"],
    )


@router.get("", response_model=list[MeetingOut])
def list_meetings(user: CurrentUser = Depends(current_user)):
    rows = get_db().query(
        "SELECT * FROM meetings WHERE owner_id=? ORDER BY created_at DESC, id DESC", (user.id,),
    )
    return [_to_out(r) for r in rows]


@router.post("", response_model=MeetingOut, status_code=201)
def create_meeting(body: MeetingCreate, user: CurrentUser = Depends(current_user)):
    db = get_db()
    if body.series_id is not None:
        series = db.query_one(
            "SELECT 1 FROM meeting_series WHERE id=? AND owner_id=?", (body.series_id, user.id),
        )
        if series is None:
            raise HTTPException(404, "سری جلسات پیدا نشد")
    allow_cloud = body.allow_cloud and body.sensitivity != "confidential"
    meeting_id = db.insert(
        "INSERT INTO meetings(owner_id, title, capture_mode, language, allow_cloud, series_id, sensitivity) "
        "VALUES(?,?,?,?,?,?,?)",
        (user.id, body.title, body.capture_mode, body.language,
         int(allow_cloud), body.series_id, body.sensitivity),
    )
    return _to_out(db.query_one("SELECT * FROM meetings WHERE id=?", (meeting_id,)))


@router.get("/{meeting_id}", response_model=MeetingOut)
def get_meeting(meeting_id: int, user: CurrentUser = Depends(current_user)):
    return _to_out(_own_meeting(user, meeting_id))


@router.delete("/{meeting_id}")
def delete_meeting(meeting_id: int, user: CurrentUser = Depends(current_user)):
    """True deletion (D4): removes the transcript, audio, embeddings, and
    search-index entries together — not just the DB row."""
    import shutil

    from neurai.config import get_config

    meeting = _own_meeting(user, meeting_id)
    if get_session_manager().get(meeting_id) is not None:
        raise HTTPException(409, "جلسه در حال ضبط است؛ ابتدا آن را متوقف کنید")

    db = get_db()
    # embeddings / search index (rag_chunks has no FK to meetings on purpose —
    # delete explicitly so the index can never outlive the meeting)
    db.execute(
        "DELETE FROM rag_chunks WHERE owner_id=? AND kind='transcript' AND ref_id=?",
        (user.id, meeting_id),
    )
    # audio (the sealed .neura recording) and exported files
    cfg = get_config()
    if meeting["audio_path"]:
        Path(meeting["audio_path"]).unlink(missing_ok=True)
    shutil.rmtree(cfg.exports_dir / str(meeting_id), ignore_errors=True)
    # row + cascades (segments, speaker names, bookmarks, notes, summaries);
    # action_items keep living as user-owned objects (meeting_id → NULL)
    db.execute("DELETE FROM meetings WHERE id=? AND owner_id=?", (meeting_id, user.id))
    return {"ok": True}


@router.post("/{meeting_id}/start")
async def start_meeting(meeting_id: int, user: CurrentUser = Depends(current_user)):
    meeting = _own_meeting(user, meeting_id)
    if meeting["status"] not in ("created", "live"):
        raise HTTPException(409, "این جلسه قبلاً ضبط شده است")
    try:
        await get_session_manager().start(meeting_id, user.id)
    except MeetingBusyError as e:
        raise HTTPException(409, e.message_fa)
    return {"ok": True, "status": "live"}


@router.post("/{meeting_id}/stop")
async def stop_meeting(meeting_id: int, user: CurrentUser = Depends(current_user)):
    _own_meeting(user, meeting_id)
    await get_session_manager().stop(meeting_id)
    return {"ok": True, "status": "processing"}


# -- transcript ---------------------------------------------------------------

class SegmentOut(BaseModel):
    id: int
    pass_name: str
    start_ms: int
    end_ms: int
    speaker: str | None
    text: str


@router.get("/{meeting_id}/transcript", response_model=list[SegmentOut])
def get_transcript(meeting_id: int, user: CurrentUser = Depends(current_user)):
    _own_meeting(user, meeting_id)
    db = get_db()
    names = {
        r["label"]: r["display_name"]
        for r in db.query("SELECT label, display_name FROM speaker_names WHERE meeting_id=?", (meeting_id,))
    }
    # quality pass wins once it exists (D2)
    for pass_name in ("quality", "live"):
        rows = db.query(
            "SELECT * FROM transcript_segments WHERE meeting_id=? AND pass=? ORDER BY start_ms",
            (meeting_id, pass_name),
        )
        if rows:
            return [
                SegmentOut(
                    id=r["id"], pass_name=pass_name, start_ms=r["start_ms"], end_ms=r["end_ms"],
                    speaker=names.get(r["speaker_label"], r["speaker_label"]), text=r["text"],
                )
                for r in rows
            ]
    return []


class RelabelBody(BaseModel):
    label: str
    display_name: str = Field(min_length=1, max_length=100)


@router.post("/{meeting_id}/speakers/relabel")
def relabel_speaker(meeting_id: int, body: RelabelBody, user: CurrentUser = Depends(current_user)):
    """Manual relabel (D2): name propagates to all of that speaker's segments."""
    _own_meeting(user, meeting_id)
    get_db().execute(
        "INSERT INTO speaker_names(meeting_id, label, display_name) VALUES(?,?,?) "
        "ON CONFLICT(meeting_id, label) DO UPDATE SET display_name=excluded.display_name",
        (meeting_id, body.label, body.display_name),
    )
    return {"ok": True}


# -- audio playback (audio-linked transcript, D2 UX) -----------------------------
#
# Recordings are AES-CTR-encrypted at rest (D4). The WAV container is
# synthesized here: 44-byte header + decrypted PCM, streamed with Range
# support so the player can seek to any sentence without the server
# decrypting the whole meeting.

_WAV_HEADER_LEN = 44


def _wav_header(pcm_len: int) -> bytes:
    import struct

    from neurai.audio.asr import SAMPLE_RATE

    return (
        b"RIFF" + struct.pack("<I", 36 + pcm_len) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16)
        + b"data" + struct.pack("<I", pcm_len)
    )


@router.get("/{meeting_id}/audio")
def get_audio(meeting_id: int, request: Request, user: CurrentUser = Depends(current_user)):
    from neurai.security import audiocrypt

    meeting = _own_meeting(user, meeting_id)
    path = meeting["audio_path"]
    if not path or not Path(path).exists():
        raise HTTPException(404, "فایل صوتی موجود نیست")

    pcm_len = audiocrypt.pcm_size(path)
    total = _WAV_HEADER_LEN + pcm_len
    header = _wav_header(pcm_len)

    start, end = 0, total - 1
    range_header = request.headers.get("range")
    status = 200
    if range_header:
        m = re.match(r"bytes=(\d*)-(\d*)$", range_header.strip())
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), total - 1)
            else:  # suffix range: last N bytes
                start = max(0, total - int(m.group(2)))
            if start > end or start >= total:
                raise HTTPException(416, headers={"Content-Range": f"bytes */{total}"})
            status = 206

    def stream():
        pos = start
        if pos < _WAV_HEADER_LEN:
            yield header[pos:min(end + 1, _WAV_HEADER_LEN)]
            pos = _WAV_HEADER_LEN
        chunk_size = 1 << 18
        while pos <= end:
            n = min(chunk_size, end - pos + 1)
            data = audiocrypt.read_pcm_range(path, pos - _WAV_HEADER_LEN, n)
            if not data:
                break
            yield data
            pos += len(data)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    return StreamingResponse(stream(), status_code=status, media_type="audio/wav", headers=headers)


# -- bookmarks («علامت بزن») ------------------------------------------------------

class BookmarkCreate(BaseModel):
    t_ms: int = Field(ge=0)
    note: str = ""


@router.post("/{meeting_id}/bookmarks", status_code=201)
def add_bookmark(meeting_id: int, body: BookmarkCreate, user: CurrentUser = Depends(current_user)):
    _own_meeting(user, meeting_id)
    bookmark_id = get_db().insert(
        "INSERT INTO bookmarks(meeting_id, user_id, t_ms, note) VALUES(?,?,?,?)",
        (meeting_id, user.id, body.t_ms, body.note),
    )
    return {"id": bookmark_id}


@router.get("/{meeting_id}/bookmarks")
def list_bookmarks(meeting_id: int, user: CurrentUser = Depends(current_user)):
    _own_meeting(user, meeting_id)
    rows = get_db().query(
        "SELECT id, t_ms, note, created_at FROM bookmarks "
        "WHERE meeting_id=? AND user_id=? ORDER BY t_ms",
        (meeting_id, user.id),
    )
    return [dict(r) for r in rows]


# -- meeting notepad ---------------------------------------------------------------

class NoteCreate(BaseModel):
    text: str = Field(min_length=1)
    t_ms: int | None = None


@router.post("/{meeting_id}/notes", status_code=201)
def add_note(meeting_id: int, body: NoteCreate, user: CurrentUser = Depends(current_user)):
    _own_meeting(user, meeting_id)
    note_id = get_db().insert(
        "INSERT INTO meeting_notes(meeting_id, user_id, t_ms, text) VALUES(?,?,?,?)",
        (meeting_id, user.id, body.t_ms, body.text),
    )
    return {"id": note_id}


@router.get("/{meeting_id}/notes")
def list_notes(meeting_id: int, user: CurrentUser = Depends(current_user)):
    _own_meeting(user, meeting_id)
    rows = get_db().query(
        "SELECT id, t_ms, text, created_at FROM meeting_notes "
        "WHERE meeting_id=? AND user_id=? ORDER BY id",
        (meeting_id, user.id),
    )
    return [dict(r) for r in rows]


# -- summaries & exports --------------------------------------------------------------

@router.get("/{meeting_id}/summaries")
def list_summaries(meeting_id: int, user: CurrentUser = Depends(current_user)):
    _own_meeting(user, meeting_id)
    rows = get_db().query(
        "SELECT id, kind, content, source, model, created_at FROM summaries "
        "WHERE meeting_id=? ORDER BY id DESC",
        (meeting_id,),
    )
    return [dict(r) for r in rows]


@router.get("/{meeting_id}/exports/{filename}")
def download_export(meeting_id: int, filename: str, user: CurrentUser = Depends(current_user)):
    from neurai.config import get_config

    _own_meeting(user, meeting_id)
    base = (get_config().exports_dir / str(meeting_id)).resolve()
    path = (base / filename).resolve()
    if base not in path.parents or not path.exists():
        raise HTTPException(404, "فایل پیدا نشد")
    return FileResponse(str(path), filename=filename)


# -- series ------------------------------------------------------------------------------

class SeriesCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)


series_router = APIRouter(prefix="/api/series", tags=["series"])


@series_router.post("", status_code=201)
def create_series(body: SeriesCreate, user: CurrentUser = Depends(current_user)):
    series_id = get_db().insert(
        "INSERT INTO meeting_series(owner_id, title) VALUES(?,?)", (user.id, body.title),
    )
    return {"id": series_id, "title": body.title}


@series_router.get("")
def list_series(user: CurrentUser = Depends(current_user)):
    rows = get_db().query(
        "SELECT id, title, created_at FROM meeting_series WHERE owner_id=? ORDER BY id DESC",
        (user.id,),
    )
    return [dict(r) for r in rows]
