"""Feature batch: stop button (D5), admin removal + D12 chain, compute modes
(D13), summary grounding (D5), online-mode plumbing (D4 backup)."""
import json
import threading
import time

import anyio
import pytest

from conftest import as_user, signup


# -- 1. stop button ------------------------------------------------------------

def _install_slow_backend(delay_s: float = 30.0):
    import neurai.harness.harness as harness_mod
    from neurai.harness.backends import BackendReply
    from neurai.harness.harness import Harness

    class SlowBackend:
        source = "local"

        async def chat(self, messages, tools=None, timeout=None, options=None):
            import asyncio

            await asyncio.sleep(delay_s)
            return BackendReply(text="پاسخ دیرهنگام", model="slow-stub")

    h = Harness()
    h.set_backends(SlowBackend, SlowBackend)
    harness_mod.set_harness(h)


def test_stop_button_cancels_generation(client):
    signup(client, "admin")
    _install_slow_backend(delay_s=30.0)
    chat_id = client.post("/api/chats", json={}).json()["id"]

    result = {}

    def send():
        result["response"] = client.post(
            f"/api/chats/{chat_id}/messages", json={"content": "سلام دستیار"},
        )

    t = threading.Thread(target=send)
    start = time.time()
    t.start()
    time.sleep(0.8)  # let the request reach the slow backend
    r = client.post(f"/api/chats/{chat_id}/cancel")
    assert r.json()["cancelled"] is True
    t.join(timeout=10)
    assert not t.is_alive(), "message request should return promptly after cancel"
    assert time.time() - start < 15  # nowhere near the 30 s backend sleep

    body = result["response"].json()
    assert body["type"] == "stopped"
    assert "متوقف" in body["content"]
    # chat history reflects the stop, not an error
    messages = client.get(f"/api/chats/{chat_id}/messages").json()
    assert any("متوقف" in m["content"] for m in messages if m["role"] == "assistant")


def test_cancel_with_nothing_in_flight(client):
    signup(client, "admin")
    chat_id = client.post("/api/chats", json={}).json()["id"]
    assert client.post(f"/api/chats/{chat_id}/cancel").json()["cancelled"] is False


# -- 2. admin removal + D12 hash chain ------------------------------------------

def test_admin_removal_logs_to_chain(client):
    from neurai.db import get_db

    signup(client, "admin")
    bob = signup(client, "bob")
    as_user(client, bob)
    meeting_id = client.post("/api/meetings", json={"title": "جلسه باب"}).json()["id"]
    get_db().insert(
        "INSERT INTO transcript_segments(meeting_id, pass, start_ms, end_ms, text) "
        "VALUES(?, 'quality', 0, 1000, 'متن')", (meeting_id,),
    )

    # non-admin cannot use the admin removal
    assert client.delete(f"/api/admin/meetings/{meeting_id}").status_code == 403

    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    listed = client.get("/api/admin/meetings").json()
    assert any(m["id"] == meeting_id and m["owner"] == "bob" for m in listed)

    assert client.delete(f"/api/admin/meetings/{meeting_id}").json() == {"ok": True}
    assert client.delete(f"/api/admin/meetings/{meeting_id}").status_code == 404

    # D12: destructive action is on the chain, chain verifies intact
    records = client.get("/api/admin/audit-file").json()
    assert records[0]["action"] == "genesis"
    removal = [r for r in records if r["action"] == "meeting_removed"]
    assert removal and removal[-1]["details"]["meeting_id"] == meeting_id
    assert removal[-1]["actor"] == "admin"
    verdict = client.get("/api/admin/audit-file/verify").json()
    assert verdict["intact"] is True and verdict["records"] >= 2


def test_chain_detects_tampering(client):
    from neurai.config import get_config
    from neurai.security import adminlog

    signup(client, "admin")
    adminlog.append("admin", "test_event", {"n": 1})
    adminlog.append("admin", "test_event", {"n": 2})
    assert adminlog.verify()["intact"] is True

    path = get_config().data_dir / adminlog.FILE_NAME
    lines = path.read_text(encoding="utf-8").splitlines()
    # tamper with the middle record's details
    record = json.loads(lines[1])
    record["details"] = {"n": 999}
    lines[1] = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    verdict = adminlog.verify()
    assert verdict["intact"] is False
    assert verdict["broken_at_line"] == 2

    # deleting a line breaks it too
    path.write_text("\n".join([lines[0]] + lines[2:]) + "\n", encoding="utf-8")
    assert adminlog.verify()["intact"] is False


def test_settings_changes_are_chained(client):
    signup(client, "admin")
    client.put("/api/admin/settings", json={"connectivity_profile": "air_gapped",
                                            "openrouter_key": "sk-test"})
    records = client.get("/api/admin/audit-file").json()
    changed = [r for r in records if r["action"] == "settings_changed"]
    assert changed
    details = changed[-1]["details"]
    assert details["connectivity_profile"] == "air_gapped"
    assert details["openrouter_key"] == "set"          # kind only, never the value
    assert "sk-test" not in json.dumps(records)


# -- 3. compute modes (D13) -----------------------------------------------------

def test_gpu_first_single_mode(app_env):
    """D13 v0.3: one behavior — try CUDA, silent CPU fallback, never fatal,
    no setting anywhere."""
    from neurai.audio.asr import load_gpu_first

    def loader_no_cuda(device):
        if device == "cuda":
            raise RuntimeError("Library cublas64_12.dll is not found")
        return f"model-on-{device}"

    model, device = load_gpu_first(loader_no_cuda)
    assert (model, device) == ("model-on-cpu", "cpu")
    model, device = load_gpu_first(lambda d: f"model-on-{d}")
    assert device == "cuda"


def test_asr_device_setting_is_gone(client):
    """D13 v0.3 migration: the old setting is not exposed, not mutable, and
    any stored value was dropped by migration 003."""
    from neurai.db import get_db

    signup(client, "admin")
    settings = client.get("/api/admin/settings").json()
    assert "asr_device" not in settings
    # unknown fields are ignored; nothing lands in the settings table
    client.put("/api/admin/settings", json={"asr_device": "cuda"})
    assert get_db().get_setting("asr_device") is None


# -- 4. summary grounding (D5) ---------------------------------------------------

def test_no_transcript_means_honest_answer_no_llm_call(client):
    import neurai.harness.harness as harness_mod
    from neurai.harness.harness import Harness
    from neurai.skills import SkillContext, get_skill_runtime

    signup(client, "admin")

    calls = {"n": 0}

    class CountingBackend:
        source = "local"

        async def chat(self, messages, tools=None, timeout=None, options=None):
            calls["n"] += 1
            from neurai.harness.backends import BackendReply

            return BackendReply(text="خلاصه جعلی", model="stub")

    h = Harness()
    h.set_backends(CountingBackend, CountingBackend)
    harness_mod.set_harness(h)

    from neurai.db import get_db

    meeting_id = client.post("/api/meetings", json={"title": "جلسه خالی"}).json()["id"]
    admin_id = get_db().query_one("SELECT id FROM users WHERE username='admin'")["id"]
    ctx = SkillContext(user_id=admin_id, username="admin")

    for skill in ("summarize_meeting", "extract_action_items"):
        result = anyio.run(get_skill_runtime().execute, skill, {"meeting_id": meeting_id}, ctx)
        assert "رونوشتی ثبت نشده" in result["error"]
    assert calls["n"] == 0, "no LLM call may happen without a transcript"

    # a trivially short transcript is treated the same
    get_db().insert(
        "INSERT INTO transcript_segments(meeting_id, pass, start_ms, end_ms, text) "
        "VALUES(?, 'quality', 0, 500, 'بله')", (meeting_id,),
    )
    result = anyio.run(get_skill_runtime().execute, "summarize_meeting",
                       {"meeting_id": meeting_id}, ctx)
    assert "رونوشتی ثبت نشده" in result["error"]
    assert calls["n"] == 0

    # minutes export refuses the same way
    from neurai.minutes.export import build_minutes_body

    with pytest.raises(RuntimeError, match="رونوشتی ثبت نشده"):
        anyio.run(build_minutes_body, meeting_id, False, "plain")


def test_user_cloud_readiness(client):
    """Any user (not just admins) can read cloud readiness with a reason, so
    the allow-cloud toggle can explain itself. No secret material."""
    signup(client, "admin")
    client.put("/api/admin/settings", json={"openrouter_key": "sk-user-test"})

    bob = signup(client, "bob")
    as_user(client, bob)
    # non-admin: admin endpoint forbidden, user endpoint allowed
    assert client.get("/api/admin/cloud-status").status_code == 403
    r = client.get("/api/cloud").json()
    assert r == {"cloud_ready": False, "reason": "offline_mode"}

    from neurai.db import get_db

    get_db().set_setting("server_mode", "online")  # D15 switch (probe-gating tested elsewhere)

    as_user(client, bob)
    r = client.get("/api/cloud")
    assert r.json() == {"cloud_ready": True, "reason": "ready"}
    assert "sk-user-test" not in r.text

    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    client.put("/api/admin/settings", json={"connectivity_profile": "air_gapped"})
    as_user(client, bob)
    assert client.get("/api/cloud").json() == {"cloud_ready": False, "reason": "air_gapped"}


# -- 5. online-mode plumbing ------------------------------------------------------

def test_cloud_status_booleans_only(client):
    signup(client, "admin")
    status = client.get("/api/admin/cloud-status").json()
    assert status == {"profile": "auto", "openrouter_configured": False,
                      "supabase_configured": False}

    client.put("/api/admin/settings", json={
        "supabase_url": "https://example.supabase.co", "supabase_key": "sb-secret-xyz",
    })
    status = client.get("/api/admin/cloud-status").json()
    assert status["supabase_configured"] is True
    assert "sb-secret-xyz" not in json.dumps(status)

    # clearing works
    client.put("/api/admin/settings", json={"supabase_key": ""})
    assert client.get("/api/admin/cloud-status").json()["supabase_configured"] is False


def test_backup_guards(client):
    signup(client, "admin")
    # not configured → 400
    assert client.post("/api/admin/backup").status_code == 400
    client.put("/api/admin/settings", json={
        "supabase_url": "https://example.supabase.co", "supabase_key": "sb-secret",
    })
    # air-gapped → hard-disabled
    client.put("/api/admin/settings", json={"connectivity_profile": "air_gapped"})
    assert client.post("/api/admin/backup").status_code == 403
    client.put("/api/admin/settings", json={"connectivity_profile": "auto"})
    r = client.post("/api/admin/backup")
    assert r.status_code == 200 and "job_id" in r.json()


def test_backup_snapshot_job_uploads_encrypted_db(client, monkeypatch):
    import sqlite3

    import neurai.backup as backup_mod
    from neurai.db import get_db

    signup(client, "admin")
    client.put("/api/admin/settings", json={
        "supabase_url": "https://example.supabase.co", "supabase_key": "sb-secret",
    })
    get_db().set_setting("probe_marker", "42")

    uploaded = {}

    async def fake_upload(url, key, bucket, name, data):
        uploaded.update(url=url, key=key, bucket=bucket, name=name, data=data)

    monkeypatch.setattr(backup_mod, "_upload", fake_upload)
    anyio.run(backup_mod.backup_snapshot_job, {"actor": "admin"})

    assert uploaded["bucket"] == backup_mod.BUCKET
    assert uploaded["url"].startswith("https://example.supabase.co")
    # the uploaded snapshot is ciphertext: plain SQLite cannot read it
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp()) / "snapshot.db"
    tmp.write_bytes(uploaded["data"])
    plain = sqlite3.connect(str(tmp))
    with pytest.raises(sqlite3.DatabaseError):
        plain.execute("SELECT * FROM settings").fetchall()
    plain.close()

    # ...but the SQLCipher driver with the local key CAN (it's a real snapshot)
    import sqlcipher3

    from neurai.db.database import AT_REST_KEY_NAME
    from neurai.security import get_or_create_key

    conn = sqlcipher3.connect(str(tmp))
    conn.execute(f"PRAGMA key = \"x'{get_or_create_key(AT_REST_KEY_NAME)}'\"")
    row = conn.execute("SELECT value FROM settings WHERE key='probe_marker'").fetchone()
    assert row[0] == "42"
    conn.close()


def test_backup_job_refuses_air_gapped(client, monkeypatch):
    import neurai.backup as backup_mod

    signup(client, "admin")
    client.put("/api/admin/settings", json={
        "supabase_url": "https://example.supabase.co", "supabase_key": "sb-secret",
        "connectivity_profile": "air_gapped",
    })

    async def must_not_upload(*a, **k):
        raise AssertionError("air-gapped profile must never reach the network")

    monkeypatch.setattr(backup_mod, "_upload", must_not_upload)
    with pytest.raises(RuntimeError, match="air-gapped"):
        anyio.run(backup_mod.backup_snapshot_job, {})
