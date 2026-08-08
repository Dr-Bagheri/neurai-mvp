"""End-to-end live meeting flow with the fake ASR engine: start → stream mic
audio over WS → live captions stored → stop → quality pass replaces the
transcript → playback + SRT available. No model files needed (CI-safe)."""
import json
import time

import numpy as np

from conftest import signup

SAMPLE_RATE = 16_000


def _noise_pcm(seconds: float, amplitude: int = 3000) -> bytes:
    rng = np.random.default_rng(42)
    samples = (rng.standard_normal(int(SAMPLE_RATE * seconds)) * amplitude).astype(np.int16)
    return samples.tobytes()


def _silence_pcm(seconds: float) -> bytes:
    return np.zeros(int(SAMPLE_RATE * seconds), dtype=np.int16).tobytes()


def _wait_status(client, meeting_id: int, wanted: str, timeout_s: float = 15.0) -> str:
    deadline = time.time() + timeout_s
    status = ""
    while time.time() < deadline:
        status = client.get(f"/api/meetings/{meeting_id}").json()["status"]
        if status == wanted:
            return status
        time.sleep(0.2)
    return status


def test_full_meeting_lifecycle(client):
    signup(client, "admin")
    meeting_id = client.post("/api/meetings", json={"title": "جلسه تست"}).json()["id"]

    assert client.post(f"/api/meetings/{meeting_id}/start").json()["status"] == "live"

    # capacity rule (§4): a second live meeting is refused, in Persian
    other_id = client.post("/api/meetings", json={"title": "جلسه دوم"}).json()["id"]
    r = client.post(f"/api/meetings/{other_id}/start")
    assert r.status_code == 409
    assert "جلسه" in r.json()["detail"]

    with client.websocket_connect(f"/ws/meetings/{meeting_id}/audio") as ws:
        ws.send_bytes(_noise_pcm(3.0))
        ws.send_bytes(_silence_pcm(1.0))   # trailing silence triggers the live pass
        time.sleep(0.5)                     # let the ASR task store segments
        ws.send_text(json.dumps({"type": "stop"}))
        assert json.loads(ws.receive_text())["type"] == "stopped"

    # quality pass runs in the background worker and replaces the live pass
    assert _wait_status(client, meeting_id, "done") == "done"

    segments = client.get(f"/api/meetings/{meeting_id}/transcript").json()
    assert segments, "quality transcript should exist"
    assert all(s["pass_name"] == "quality" for s in segments)
    assert segments[0]["speaker"] == "S1"  # room mode default label

    # manual relabel propagates through the transcript view (D2)
    client.post(f"/api/meetings/{meeting_id}/speakers/relabel",
                json={"label": "S1", "display_name": "سارا"})
    segments = client.get(f"/api/meetings/{meeting_id}/transcript").json()
    assert segments[0]["speaker"] == "سارا"

    # audio-linked playback: encrypted at rest, served as a synthesized WAV
    r = client.get(f"/api/meetings/{meeting_id}/audio")
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF"
    total = len(r.content)

    # Range seeking (click a sentence → play that moment)
    r = client.get(f"/api/meetings/{meeting_id}/audio", headers={"Range": "bytes=44-143"})
    assert r.status_code == 206
    assert len(r.content) == 100
    assert r.headers["content-range"] == f"bytes 44-143/{total}"

    # bookmarks + notes
    assert client.post(f"/api/meetings/{meeting_id}/bookmarks",
                       json={"t_ms": 1500, "note": "نکته مهم"}).status_code == 201
    assert client.get(f"/api/meetings/{meeting_id}/bookmarks").json()[0]["t_ms"] == 1500
    assert client.post(f"/api/meetings/{meeting_id}/notes",
                       json={"text": "پیگیری بودجه", "t_ms": 2000}).status_code == 201

    # SRT export builds from the quality transcript
    from neurai.minutes.export import build_srt

    srt = build_srt(meeting_id)
    assert "-->" in srt and "سارا:" in srt


def test_ws_requires_auth_and_ownership(client):
    from conftest import as_user

    signup(client, "admin")
    meeting_id = client.post("/api/meetings", json={"title": "جلسه"}).json()["id"]
    client.post(f"/api/meetings/{meeting_id}/start")

    bob = signup(client, "bob")
    as_user(client, bob)
    from starlette.websockets import WebSocketDisconnect
    import pytest

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/meetings/{meeting_id}/audio") as ws:
            ws.receive_text()
