"""WebSockets for the live meeting (D1/D2 v0.3).

- /ws/meetings/{id}/audio?mic_id=N — mic upstream: binary frames of PCM16
  @16 kHz mono, bound to a registered mic (named multi-mic). Without mic_id
  the stream binds to the meeting's first mic. Text frames carry JSON
  control: {"type": "stop"}. The meeting must have been started via
  POST /api/meetings/{id}/start.
- /ws/meetings/{id}/events — downstream lifecycle events ({"type":"ended"}).
  Live captions are gone since v0.3; transcription progress is polled via
  GET /api/meetings/{id}/progress.

Auth is the same session cookie, checked on the handshake.
"""
from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from neurai.auth.deps import ws_current_user
from neurai.audio.session import UnknownMicError, get_session_manager
from neurai.db import get_db

router = APIRouter()


def _owns_meeting(user_id: int, meeting_id: int) -> bool:
    return get_db().query_one(
        "SELECT 1 FROM meetings WHERE id=? AND owner_id=?", (meeting_id, user_id),
    ) is not None


def _default_mic_id(meeting_id: int) -> int | None:
    row = get_db().query_one(
        "SELECT id FROM meeting_mics WHERE meeting_id=? ORDER BY id LIMIT 1", (meeting_id,),
    )
    return row["id"] if row else None


@router.websocket("/ws/meetings/{meeting_id}/audio")
async def audio_ws(websocket: WebSocket, meeting_id: int, mic_id: int | None = None):
    user = ws_current_user(websocket)
    if user is None or not _owns_meeting(user.id, meeting_id):
        await websocket.close(code=4401)
        return
    session = get_session_manager().get(meeting_id)
    if session is None:
        await websocket.close(code=4404)  # start the meeting over REST first
        return
    if mic_id is None:
        mic_id = _default_mic_id(meeting_id)
    if mic_id is None:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                try:
                    await session.feed(mic_id, message["bytes"])
                except UnknownMicError:
                    await websocket.close(code=4404)
                    break
            elif message.get("text"):
                try:
                    control = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                if control.get("type") == "stop":
                    await get_session_manager().stop(meeting_id)
                    await websocket.send_text(json.dumps({"type": "stopped"}))
                    break
    except WebSocketDisconnect:
        pass
    # NOTE: on disconnect without an explicit stop, the session stays live so
    # a dropped WiFi link can reconnect and keep recording (the encrypted
    # writer resumes). The meeting ends via /stop or the control message.


@router.websocket("/ws/meetings/{meeting_id}/events")
async def events_ws(websocket: WebSocket, meeting_id: int):
    user = ws_current_user(websocket)
    if user is None or not _owns_meeting(user.id, meeting_id):
        await websocket.close(code=4401)
        return
    session = get_session_manager().get(meeting_id)
    if session is None:
        await websocket.close(code=4404)
        return

    await websocket.accept()
    queue = session.subscribe()
    try:
        while True:
            event = await queue.get()
            await websocket.send_text(json.dumps(event, ensure_ascii=False))
            if event.get("type") == "ended":
                break
    except WebSocketDisconnect:
        pass
    finally:
        session.unsubscribe(queue)
        with contextlib.suppress(RuntimeError):
            await websocket.close()
