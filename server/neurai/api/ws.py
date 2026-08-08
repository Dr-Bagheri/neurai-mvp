"""WebSockets for the live meeting (D1/D2).

- /ws/meetings/{id}/audio    — mic upstream: binary frames of PCM16 @16 kHz
  mono. Text frames carry JSON control: {"type": "stop"}. The meeting must
  have been started via POST /api/meetings/{id}/start.
- /ws/meetings/{id}/captions — downstream: JSON caption events for viewers.

Auth is the same session cookie, checked on the handshake.
"""
from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from neurai.auth.deps import ws_current_user
from neurai.audio.session import get_session_manager
from neurai.db import get_db

router = APIRouter()


def _owns_meeting(user_id: int, meeting_id: int) -> bool:
    return get_db().query_one(
        "SELECT 1 FROM meetings WHERE id=? AND owner_id=?", (meeting_id, user_id),
    ) is not None


@router.websocket("/ws/meetings/{meeting_id}/audio")
async def audio_ws(websocket: WebSocket, meeting_id: int):
    user = ws_current_user(websocket)
    if user is None or not _owns_meeting(user.id, meeting_id):
        await websocket.close(code=4401)
        return
    session = get_session_manager().get(meeting_id)
    if session is None:
        await websocket.close(code=4404)  # start the meeting over REST first
        return

    await websocket.accept()
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                await session.feed(message["bytes"])
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
    # a dropped WiFi link can reconnect and keep recording. The meeting ends
    # via /stop or the control message.


@router.websocket("/ws/meetings/{meeting_id}/captions")
async def captions_ws(websocket: WebSocket, meeting_id: int):
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
