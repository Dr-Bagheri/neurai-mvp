"""D15: offline/online mode (probe-gated), per-task cloud routing, and the
consent-gated cloud ASR path with automatic local fallback."""
import json
import time

import anyio
import numpy as np

from conftest import signup

SAMPLE_RATE = 16_000


def _noise_pcm(seconds: float) -> bytes:
    rng = np.random.default_rng(7)
    return (rng.standard_normal(int(SAMPLE_RATE * seconds)) * 3000).astype(np.int16).tobytes()


def _wait_status(client, meeting_id, wanted, timeout_s=15.0):
    deadline = time.time() + timeout_s
    status = ""
    while time.time() < deadline:
        status = client.get(f"/api/meetings/{meeting_id}").json()["status"]
        if status == wanted:
            return status
        time.sleep(0.2)
    return status


# -- 1. mode switch, probe-gated ---------------------------------------------------

def test_mode_switch_probe_gated(client, monkeypatch):
    from neurai.harness import connectivity

    signup(client, "admin")
    assert client.get("/api/admin/mode").json()["mode"] == "offline"  # default

    # disconnected server: Online is refused with a Persian detail
    monkeypatch.setattr(connectivity, "probe_internet", lambda *a, **k: False)
    assert client.get("/api/admin/mode").json()["online_available"] is False
    r = client.put("/api/admin/mode", json={"mode": "online"})
    assert r.status_code == 409 and "اینترنت" in r.json()["detail"]
    assert client.get("/api/admin/mode").json()["mode"] == "offline"

    # reachable: switch succeeds and is D12-chained
    monkeypatch.setattr(connectivity, "probe_internet", lambda *a, **k: True)
    r = client.put("/api/admin/mode", json={"mode": "online"})
    assert r.json() == {"mode": "online", "online_available": True}
    records = client.get("/api/admin/audit-file").json()
    changed = [x for x in records if x["action"] == "settings_changed"]
    assert changed and changed[-1]["details"].get("server_mode") == "online"

    # harness gate follows the mode — one source of truth
    assert connectivity.cloud_allowed() is True
    client.put("/api/admin/mode", json={"mode": "offline"})  # no probe needed
    assert connectivity.cloud_allowed() is False


def test_air_gapped_locks_offline(client, monkeypatch):
    from neurai.harness import connectivity

    signup(client, "admin")
    client.put("/api/admin/settings", json={"connectivity_profile": "air_gapped"})
    monkeypatch.setattr(connectivity, "_probe", lambda *a, **k: True)  # even if reachable

    mode = client.get("/api/admin/mode").json()
    assert mode == {"mode": "offline", "online_available": False}
    r = client.put("/api/admin/mode", json={"mode": "online"})
    assert r.status_code == 409 and "ایزوله" in r.json()["detail"]


# -- 2. per-task cloud routing -------------------------------------------------------

def test_per_task_model_routing(client, monkeypatch):
    from neurai.db import get_db
    from neurai.harness import connectivity
    from neurai.harness.backends import BackendReply
    from neurai.harness.harness import Constraints, Harness

    signup(client, "admin")
    get_db().set_setting("server_mode", "online")
    monkeypatch.setattr(connectivity, "probe_cloud", lambda *a, **k: True)

    picked = []

    class CaptureCloud:
        source = "cloud"

        def __init__(self, model=None):
            picked.append(model)

        async def chat(self, messages, tools=None, timeout=None, options=None):
            return BackendReply(text="cloud", model=picked[-1] or "?")

    class StubLocal:
        source = "local"

        async def chat(self, messages, tools=None, timeout=None, options=None):
            return BackendReply(text="local", model="stub")

    h = Harness()
    h.set_backends(StubLocal, CaptureCloud)

    anyio.run(h.complete, "summarize", [{"role": "user", "content": "x"}],
              Constraints(allow_cloud=True))
    anyio.run(h.complete, "minutes", [{"role": "user", "content": "x"}],
              Constraints(allow_cloud=True))
    anyio.run(h.complete, "translate", [{"role": "user", "content": "x"}],
              Constraints(allow_cloud=True))
    anyio.run(h.complete, "chat_agent", [{"role": "user", "content": "x"}],
              Constraints(allow_cloud=True))
    assert picked == [
        "anthropic/claude-opus-5",    # summarize → heavy
        "anthropic/claude-opus-5",    # minutes → heavy
        "anthropic/claude-sonnet-5",  # translate → chat family
        "anthropic/claude-sonnet-5",  # chat_agent → chat family
    ]

    # admin-overridable
    get_db().set_setting("cloud_heavy_model", "custom/heavy-model")
    anyio.run(h.complete, "summarize", [{"role": "user", "content": "x"}],
              Constraints(allow_cloud=True))
    assert picked[-1] == "custom/heavy-model"


# -- 3. cloud ASR consent matrix -------------------------------------------------------

def _configure_cloud_asr(online: bool = True):
    from neurai.db import get_db
    from neurai.security import set_secret

    set_secret("cloud_asr_url", "https://api.groq.com/openai/v1")
    set_secret("cloud_asr_key", "gsk-test-secret")
    if online:
        get_db().set_setting("server_mode", "online")


def _stub_cloud_asr(monkeypatch, fail: bool = False):
    import neurai.audio.quality_pass  # noqa: F401 — module imports cloud_asr lazily
    from neurai.audio import cloud_asr
    from neurai.audio.asr import AsrSegment

    calls = {"n": 0}

    async def stub(pcm, language="fa"):
        calls["n"] += 1
        if fail:
            raise RuntimeError("provider 500")
        return [AsrSegment(start_ms=0, end_ms=3000, text="رونوشت ابری آزمایشی")]

    monkeypatch.setattr(cloud_asr, "transcribe_cloud", stub)
    return calls


def _run_meeting(client, cloud_transcribe: bool):
    body = {"title": "جلسه", "cloud_transcribe": cloud_transcribe}
    meeting_id = client.post("/api/meetings", json=body).json()["id"]
    client.post(f"/api/meetings/{meeting_id}/start")
    with client.websocket_connect(f"/ws/meetings/{meeting_id}/audio") as ws:
        ws.send_bytes(_noise_pcm(3.0))
        ws.send_text(json.dumps({"type": "stop"}))
        ws.receive_text()
    return meeting_id


def test_cloud_asr_opt_in_blocked_when_offline(client):
    signup(client, "admin")
    _configure_cloud_asr(online=False)
    r = client.post("/api/meetings", json={"title": "x", "cloud_transcribe": True})
    assert r.status_code == 409 and "آنلاین" in r.json()["detail"]

    meeting_id = client.post("/api/meetings", json={"title": "x"}).json()["id"]
    r = client.put(f"/api/meetings/{meeting_id}/cloud-transcribe", json={"enabled": True})
    assert r.status_code == 409


def test_cloud_asr_confidential_never(client):
    from neurai.db import get_db

    signup(client, "admin")
    _configure_cloud_asr(online=True)
    meeting_id = client.post("/api/meetings", json={
        "title": "x", "sensitivity": "confidential",
    }).json()["id"]
    r = client.put(f"/api/meetings/{meeting_id}/cloud-transcribe", json={"enabled": True})
    assert r.status_code == 409 and "محرمانه" in r.json()["detail"]
    assert get_db().query_one(
        "SELECT cloud_transcribe FROM meetings WHERE id=?", (meeting_id,)
    )["cloud_transcribe"] == 0


def test_cloud_asr_no_consent_stays_local(client, monkeypatch):
    signup(client, "admin")
    _configure_cloud_asr(online=True)
    calls = _stub_cloud_asr(monkeypatch)
    meeting_id = _run_meeting(client, cloud_transcribe=False)
    assert _wait_status(client, meeting_id, "done") == "done"
    assert calls["n"] == 0
    segments = client.get(f"/api/meetings/{meeting_id}/transcript").json()
    assert segments and "ابری" not in segments[0]["text"]  # local fake engine text


def test_cloud_asr_with_consent_and_chaining(client, monkeypatch):
    signup(client, "admin")
    _configure_cloud_asr(online=True)
    calls = _stub_cloud_asr(monkeypatch)
    meeting_id = _run_meeting(client, cloud_transcribe=True)
    assert _wait_status(client, meeting_id, "done") == "done"
    assert calls["n"] == 1

    segments = client.get(f"/api/meetings/{meeting_id}/transcript").json()
    assert segments[0]["text"] == "رونوشت ابری آزمایشی"

    # D12: every cloud-ASR use is chained — meeting id + provider host, no
    # content, no secrets
    records = client.get("/api/admin/audit-file").json()
    used = [x for x in records if x["action"] == "cloud_asr_used"]
    assert used and used[-1]["details"] == {
        "meeting_id": meeting_id, "provider": "api.groq.com", "ok": True,
    }
    dump = json.dumps(records)
    assert "gsk-test-secret" not in dump and "رونوشت ابری" not in dump
    assert client.get("/api/admin/audit-file/verify").json()["intact"] is True


def test_cloud_asr_failure_falls_back_to_local(client, monkeypatch):
    """A transcript must never be lost to a cloud error."""
    signup(client, "admin")
    _configure_cloud_asr(online=True)
    calls = _stub_cloud_asr(monkeypatch, fail=True)
    meeting_id = _run_meeting(client, cloud_transcribe=True)
    assert _wait_status(client, meeting_id, "done") == "done"
    assert calls["n"] == 1

    segments = client.get(f"/api/meetings/{meeting_id}/transcript").json()
    assert segments, "local fallback must still produce a transcript"
    assert "ابری" not in segments[0]["text"]

    records = client.get("/api/admin/audit-file").json()
    used = [x for x in records if x["action"] == "cloud_asr_used"]
    assert used and used[-1]["details"]["ok"] is False


def test_cloud_asr_mode_recheck_at_job_run(client, monkeypatch):
    """Opt-in was granted while online, but the server went offline before
    the quality pass ran → the cloud path is unreachable at job run."""
    from neurai.db import get_db

    signup(client, "admin")
    _configure_cloud_asr(online=True)
    calls = _stub_cloud_asr(monkeypatch)
    meeting_id = client.post("/api/meetings",
                             json={"title": "x", "cloud_transcribe": True}).json()["id"]
    get_db().set_setting("server_mode", "offline")   # back offline before recording

    client.post(f"/api/meetings/{meeting_id}/start")
    with client.websocket_connect(f"/ws/meetings/{meeting_id}/audio") as ws:
        ws.send_bytes(_noise_pcm(3.0))
        ws.send_text(json.dumps({"type": "stop"}))
        ws.receive_text()
    assert _wait_status(client, meeting_id, "done") == "done"
    assert calls["n"] == 0                            # never reached the cloud
    assert client.get(f"/api/meetings/{meeting_id}/transcript").json()


def test_settings_expose_cloud_asr_booleans_only(client):
    signup(client, "admin")
    _configure_cloud_asr(online=False)
    settings = client.get("/api/admin/settings").json()
    assert settings["cloud_asr_configured"] is True
    assert settings["server_mode"] == "offline"
    assert "gsk-test-secret" not in json.dumps(settings)
