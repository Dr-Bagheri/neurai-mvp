"""v0.3 meeting flow (D2 revised): recording-only live session (no captions),
named multi-mic, auto-queued quality pass with percent progress, playback,
manual relabel, SRT — all with the fake engine (CI-safe, no models)."""
import json
import time

import numpy as np

from conftest import as_user, signup

SAMPLE_RATE = 16_000


def _noise_pcm(seconds: float, amplitude: int = 3000) -> bytes:
    rng = np.random.default_rng(42)
    samples = (rng.standard_normal(int(SAMPLE_RATE * seconds)) * amplitude).astype(np.int16)
    return samples.tobytes()


def _wait_status(client, meeting_id: int, wanted: str, timeout_s: float = 15.0) -> str:
    deadline = time.time() + timeout_s
    status = ""
    while time.time() < deadline:
        status = client.get(f"/api/meetings/{meeting_id}").json()["status"]
        if status == wanted:
            return status
        time.sleep(0.2)
    return status


def test_full_meeting_lifecycle_room_mode(client):
    signup(client, "admin")
    meeting_id = client.post("/api/meetings", json={"title": "جلسه تست"}).json()["id"]

    assert client.post(f"/api/meetings/{meeting_id}/start").json()["status"] == "live"

    # starting registers a default mic automatically
    mics = client.get(f"/api/meetings/{meeting_id}/mics").json()
    assert len(mics) == 1 and mics[0]["name"] == "میکروفون ۱"

    # capacity rule (§4): a second live meeting is refused, in Persian
    other_id = client.post("/api/meetings", json={"title": "جلسه دوم"}).json()["id"]
    r = client.post(f"/api/meetings/{other_id}/start")
    assert r.status_code == 409 and "جلسه" in r.json()["detail"]

    with client.websocket_connect(f"/ws/meetings/{meeting_id}/audio") as ws:
        ws.send_bytes(_noise_pcm(4.0))     # recording only — no captions since v0.3
        ws.send_text(json.dumps({"type": "stop"}))
        assert json.loads(ws.receive_text())["type"] == "stopped"

    # quality pass auto-queues at meeting end and replaces nothing (no live pass)
    assert _wait_status(client, meeting_id, "done") == "done"

    # progress contract: done → 100
    progress = client.get(f"/api/meetings/{meeting_id}/progress").json()
    assert progress["status"] == "done" and progress["progress"] == 100

    segments = client.get(f"/api/meetings/{meeting_id}/transcript").json()
    assert segments and all(s["pass_name"] == "quality" for s in segments)
    assert segments[0]["speaker"] == "S1"  # single room mic → diarizer default label

    # manual relabel propagates through the transcript view (D2)
    client.post(f"/api/meetings/{meeting_id}/speakers/relabel",
                json={"label": "S1", "display_name": "سارا"})
    assert client.get(f"/api/meetings/{meeting_id}/transcript").json()[0]["speaker"] == "سارا"

    # audio-linked playback: encrypted at rest, served as a synthesized WAV
    r = client.get(f"/api/meetings/{meeting_id}/audio")
    assert r.status_code == 200 and r.content[:4] == b"RIFF"
    total = len(r.content)
    r = client.get(f"/api/meetings/{meeting_id}/audio", headers={"Range": "bytes=44-143"})
    assert r.status_code == 206 and len(r.content) == 100
    assert r.headers["content-range"] == f"bytes 44-143/{total}"

    # bookmarks + notes
    assert client.post(f"/api/meetings/{meeting_id}/bookmarks",
                       json={"t_ms": 1500, "note": "نکته مهم"}).status_code == 201
    assert client.post(f"/api/meetings/{meeting_id}/notes",
                       json={"text": "پیگیری بودجه", "t_ms": 2000}).status_code == 201

    from neurai.minutes.export import build_srt

    srt = build_srt(meeting_id)
    assert "-->" in srt and "سارا:" in srt


def test_named_multi_mic_labels_segments(client):
    """D2 v0.3: each WS stream binds to a registered mic; the user-chosen
    name tag flows to the speaker labels on transcript segments."""
    signup(client, "admin")
    meeting_id = client.post(
        "/api/meetings", json={"title": "جلسه چندمیکروفونه", "capture_mode": "participants"},
    ).json()["id"]

    mic_table = client.post(f"/api/meetings/{meeting_id}/mics",
                            json={"name": "میکروفون میز جلسه"}).json()["id"]
    mic_sara = client.post(f"/api/meetings/{meeting_id}/mics",
                           json={"name": "لپ‌تاپ سارا"}).json()["id"]

    # rename works pre-meeting
    client.patch(f"/api/meetings/{meeting_id}/mics/{mic_sara}", json={"name": "لپ‌تاپ سارا ✓"})

    client.post(f"/api/meetings/{meeting_id}/start")
    with client.websocket_connect(f"/ws/meetings/{meeting_id}/audio?mic_id={mic_table}") as ws:
        ws.send_bytes(_noise_pcm(3.5))
    with client.websocket_connect(f"/ws/meetings/{meeting_id}/audio?mic_id={mic_sara}") as ws:
        ws.send_bytes(_noise_pcm(3.5))
        ws.send_text(json.dumps({"type": "stop"}))
        assert json.loads(ws.receive_text())["type"] == "stopped"

    assert _wait_status(client, meeting_id, "done") == "done"
    segments = client.get(f"/api/meetings/{meeting_id}/transcript").json()
    speakers = {s["speaker"] for s in segments}
    assert speakers == {"میکروفون میز جلسه", "لپ‌تاپ سارا ✓"}

    # per-mic playback
    r = client.get(f"/api/meetings/{meeting_id}/audio", params={"mic_id": mic_sara})
    assert r.status_code == 200 and r.content[:4] == b"RIFF"

    # a mic with recorded audio cannot be removed
    r = client.delete(f"/api/meetings/{meeting_id}/mics/{mic_sara}")
    assert r.status_code == 409


def test_quality_pass_reports_progress(client):
    """The job row carries percent progress (D2 v0.3) — fake engine emits the
    same segment-end/total-duration fractions as faster-whisper."""
    signup(client, "admin")
    meeting_id = client.post("/api/meetings", json={"title": "پیشرفت"}).json()["id"]
    client.post(f"/api/meetings/{meeting_id}/start")
    with client.websocket_connect(f"/ws/meetings/{meeting_id}/audio") as ws:
        ws.send_bytes(_noise_pcm(6.0))
        ws.send_text(json.dumps({"type": "stop"}))
        ws.receive_text()
    assert _wait_status(client, meeting_id, "done") == "done"

    from neurai.db import get_db

    job = get_db().query_one(
        "SELECT progress, status FROM jobs WHERE kind='quality_pass' ORDER BY id DESC",
    )
    assert job["status"] == "done" and job["progress"] == 100
    # admin jobs view exposes the column
    jobs = client.get("/api/admin/jobs").json()
    assert any(j["kind"] == "quality_pass" and j["progress"] == 100 for j in jobs)


def test_broken_quality_engine_keeps_recording(client):
    """D2: an ASR failure must never lose the meeting — the job fails
    (visible to the admin) but every chunk stays in the sealed recording and
    a requeue with a working engine recovers the transcript."""
    import neurai.audio.asr as asr_mod

    class ExplodingEngine:
        def transcribe(self, pcm, offset_ms=0, language="fa", progress_cb=None):
            raise RuntimeError("Library cublas64_12.dll is not found")

    asr_mod.set_engine(ExplodingEngine())

    signup(client, "admin")
    meeting_id = client.post("/api/meetings", json={"title": "GPU خراب"}).json()["id"]
    client.post(f"/api/meetings/{meeting_id}/start")
    with client.websocket_connect(f"/ws/meetings/{meeting_id}/audio") as ws:
        ws.send_bytes(_noise_pcm(3.0))
        ws.send_text(json.dumps({"type": "stop"}))
        ws.receive_text()

    # job fails, recording intact
    from neurai.db import get_db
    from neurai.security.audiocrypt import pcm_size

    deadline = time.time() + 10
    job = None
    while time.time() < deadline:
        job = get_db().query_one(
            "SELECT * FROM jobs WHERE kind='quality_pass' ORDER BY id DESC")
        if job and job["status"] == "failed":
            break
        time.sleep(0.2)
    assert job is not None and job["status"] == "failed"

    mic = get_db().query_one(
        "SELECT audio_path FROM meeting_mics WHERE meeting_id=?", (meeting_id,))
    assert pcm_size(mic["audio_path"]) == int(3.0 * SAMPLE_RATE * 2)

    # requeue with a working engine → transcript recovered from disk
    asr_mod.set_engine(asr_mod.FakeAsrEngine("quality"))
    from neurai.jobs import get_job_queue

    get_job_queue().enqueue("quality_pass", {"meeting_id": meeting_id}, priority=2)
    assert _wait_status(client, meeting_id, "done") == "done"
    assert client.get(f"/api/meetings/{meeting_id}/transcript").json()


def test_ws_requires_auth_and_ownership(client):
    signup(client, "admin")
    meeting_id = client.post("/api/meetings", json={"title": "جلسه"}).json()["id"]
    client.post(f"/api/meetings/{meeting_id}/start")

    bob = signup(client, "bob")
    as_user(client, bob)
    import pytest
    from starlette.websockets import WebSocketDisconnect

    for endpoint in ("audio", "events"):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(f"/ws/meetings/{meeting_id}/{endpoint}") as ws:
                ws.receive_text()
