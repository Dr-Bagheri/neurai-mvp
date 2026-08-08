"""Platform-control skills (D7 amendment): admin enforcement in the runtime,
rule-2 confirmation on every mutating skill, shared core with REST (D12
chain in one path), no capability beyond the REST API."""
import json

import anyio

from conftest import as_user, signup


def _ctx(username: str, *, admin: bool, confirmed: bool = False):
    from neurai.db import get_db
    from neurai.skills import SkillContext

    row = get_db().query_one("SELECT id FROM users WHERE username=?", (username,))
    return SkillContext(user_id=row["id"], username=username,
                        is_admin=admin, confirmed=confirmed)


def _execute(skill, params, ctx):
    from neurai.skills import get_skill_runtime

    return anyio.run(get_skill_runtime().execute, skill, params, ctx)


def test_non_admin_denial_matches_unknown_skill_shape(client):
    """A non-admin invoking an admin skill gets the IDENTICAL response as an
    unknown skill — capabilities aren't probeable. The audit records truth."""
    from neurai.db import get_db

    signup(client, "admin")
    signup(client, "bob")
    bob = _ctx("bob", admin=False)

    denied = _execute("delete_meeting", {"meeting_id": 1}, bob)
    unknown = _execute("no_such_skill_xyz", {}, bob)
    assert denied == {"error": "unknown skill: delete_meeting"}
    assert set(denied.keys()) == set(unknown.keys())

    row = get_db().query_one(
        "SELECT error FROM audit_log WHERE skill='delete_meeting' ORDER BY id DESC")
    assert row["error"] == "admin required"

    # every admin skill is covered by the same gate
    for skill, params in [("get_status", {}),
                          ("set_setting", {"key": "connectivity_profile", "value": "auto"}),
                          ("trigger_backup", {})]:
        assert _execute(skill, params, bob) == {"error": f"unknown skill: {skill}"}


def test_admin_tools_hidden_from_non_admin_loop(client):
    from neurai.skills import get_skill_runtime

    signup(client, "admin")
    rt = get_skill_runtime()
    non_admin_tools = {t["function"]["name"] for t in rt.tool_schemas(include_admin=False)}
    admin_tools = {t["function"]["name"] for t in rt.tool_schemas(include_admin=True)}
    assert "delete_meeting" not in non_admin_tools
    assert "delete_meeting" in admin_tools
    assert "delete_document" in non_admin_tools  # owner-capable skill stays visible


def test_destructive_skill_requires_confirmation(client):
    """Rule 2: unconfirmed destructive skills return the confirmation card —
    for admins too; a transcript can never auto-trigger one."""
    signup(client, "admin")
    admin = _ctx("admin", admin=True)
    meeting_id = client.post("/api/meetings", json={"title": "برای حذف"}).json()["id"]

    result = _execute("delete_meeting", {"meeting_id": meeting_id}, admin)
    assert result["confirmation_required"] is True
    assert result["skill"] == "delete_meeting"
    # nothing happened
    assert client.get(f"/api/meetings/{meeting_id}").status_code == 200


def test_confirmed_delete_chains_to_d12(client):
    """Confirmed chat deletion goes through the SAME core as the REST admin
    endpoint: meeting truly deleted + admin-audit.jsonl record + chain intact."""
    signup(client, "admin")
    bob = signup(client, "bob")
    as_user(client, bob)
    meeting_id = client.post("/api/meetings", json={"title": "جلسه باب"}).json()["id"]

    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    chat_id = client.post("/api/chats", json={}).json()["id"]

    # via the chat confirm endpoint — the human click (rule 2)
    r = client.post(f"/api/chats/{chat_id}/confirm",
                    json={"skill": "delete_meeting", "params": {"meeting_id": meeting_id}})
    assert r.status_code == 200
    assert "حذف شد" in r.json()["content"]

    as_user(client, bob)
    assert client.get(f"/api/meetings/{meeting_id}").status_code == 404

    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    records = client.get("/api/admin/audit-file").json()
    removal = [x for x in records if x["action"] == "meeting_removed"]
    assert removal and removal[-1]["details"]["meeting_id"] == meeting_id
    assert removal[-1]["actor"] == "admin"
    assert client.get("/api/admin/audit-file/verify").json()["intact"] is True


def test_set_setting_via_confirm(client, monkeypatch):
    """Mutating settings through chat go through the same shared core: rule-2
    card first, D12 chain record on confirm (server_mode is D12-listed and
    probe-gated even through the skill path — one source of truth)."""
    from neurai.harness import connectivity

    signup(client, "admin")
    chat_id = client.post("/api/chats", json={}).json()["id"]

    # probe fails → the skill path is blocked exactly like REST
    monkeypatch.setattr(connectivity, "probe_internet", lambda *a, **k: False)
    r = client.post(
        f"/api/chats/{chat_id}/confirm",
        json={"skill": "set_setting", "params": {"key": "server_mode", "value": "online"}},
    ).json()
    assert "اینترنت" in r["content"]

    monkeypatch.setattr(connectivity, "probe_internet", lambda *a, **k: True)
    r = client.post(
        f"/api/chats/{chat_id}/confirm",
        json={"skill": "set_setting", "params": {"key": "server_mode", "value": "online"}},
    ).json()
    assert "server_mode" in r["content"]
    assert client.get("/api/admin/settings").json()["server_mode"] == "online"
    records = client.get("/api/admin/audit-file").json()
    changed = [x for x in records if x["action"] == "settings_changed"]
    assert changed and changed[-1]["details"].get("server_mode") == "online"


def test_get_status_readonly_no_confirmation(client):
    signup(client, "admin")
    chat_id = client.post("/api/chats", json={}).json()["id"]
    r = client.post(f"/api/chats/{chat_id}/messages",
                    json={"content": "وضعیت سیستم چطوره؟"}).json()
    assert r["type"] == "message"          # read-only: no confirmation card
    assert r["via"] == "intent:get_status"
    assert "پروفایل اتصال" in r["content"]


def test_trigger_backup_air_gapped_refused(client):
    signup(client, "admin")
    client.put("/api/admin/settings", json={
        "supabase_url": "https://example.supabase.co", "supabase_key": "sb-secret",
        "connectivity_profile": "air_gapped",
    })
    admin = _ctx("admin", admin=True, confirmed=True)
    result = _execute("trigger_backup", {}, admin)
    assert "ایزوله" in result["error"]


def test_delete_document_owner_and_admin(client):
    from neurai.config import get_config
    from neurai.db import get_db

    signup(client, "admin")
    bob = signup(client, "bob")
    as_user(client, bob)

    # bob uploads a document
    doc_dir = get_config().documents_dir
    doc_dir.mkdir(parents=True, exist_ok=True)
    path = doc_dir / "note.txt"
    path.write_text("متن سند", encoding="utf-8")
    bob_id = get_db().query_one("SELECT id FROM users WHERE username='bob'")["id"]
    doc_id = get_db().insert(
        "INSERT INTO documents(owner_id, filename, path) VALUES(?, 'note.txt', ?)",
        (bob_id, str(path)),
    )

    # a third user can't delete it (identical not-found shape)
    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    signup(client, "carol")
    carol = _ctx("carol", admin=False, confirmed=True)
    result = _execute("delete_document", {"document_id": doc_id}, carol)
    assert "پیدا نشد" in result["error"]

    # unconfirmed owner → confirmation card; confirmed owner → deleted
    bob_ctx = _ctx("bob", admin=False)
    assert _execute("delete_document", {"document_id": doc_id}, bob_ctx)["confirmation_required"]
    bob_ctx = _ctx("bob", admin=False, confirmed=True)
    assert _execute("delete_document", {"document_id": doc_id}, bob_ctx)["deleted"]

    # admin deleting ANOTHER user's document → D12-chained
    path2 = doc_dir / "note2.txt"
    path2.write_text("متن دوم", encoding="utf-8")
    doc2 = get_db().insert(
        "INSERT INTO documents(owner_id, filename, path) VALUES(?, 'note2.txt', ?)",
        (bob_id, str(path2)),
    )
    admin_ctx = _ctx("admin", admin=True, confirmed=True)
    assert _execute("delete_document", {"document_id": doc2}, admin_ctx)["deleted"]
    from neurai.security import adminlog

    records = adminlog.read_all()
    assert any(x["action"] == "document_removed" and x["details"]["document_id"] == doc2
               for x in records)
    assert adminlog.verify()["intact"] is True


def test_intent_patterns_for_platform_control(client):
    from neurai.skills.intent import route

    signup(client, "admin")
    from neurai.db import get_db

    admin_id = get_db().query_one("SELECT id FROM users WHERE username='admin'")["id"]
    meeting_id = client.post("/api/meetings", json={"title": "جلسه"}).json()["id"]

    intent = route(f"جلسه {meeting_id} رو از دیتابیس حذف کن", admin_id)
    assert intent is not None
    assert (intent.skill, intent.params) == ("delete_meeting", {"meeting_id": meeting_id})

    assert route("وضعیت سرور چطوره", admin_id).skill == "get_status"
    assert route("یه بکاپ بگیر", admin_id).skill == "trigger_backup"

    # deletion phrasing without a resolvable meeting doesn't match
    assert route("حذف کن", admin_id) is None


def test_rest_equivalence_no_extra_capability(client):
    """The skill surface has no capability the REST API lacks: both go
    through platform_ops, and REST behavior is unchanged after the refactor."""
    signup(client, "admin")
    meeting_id = client.post("/api/meetings", json={"title": "REST"}).json()["id"]
    assert client.delete(f"/api/admin/meetings/{meeting_id}").json() == {"ok": True}
    records = client.get("/api/admin/audit-file").json()
    assert any(x["action"] == "meeting_removed" and x["details"]["meeting_id"] == meeting_id
               for x in records)
    # settings still validate through the shared core
    assert client.put("/api/admin/settings", json={"connectivity_profile": "auto"}).status_code == 200
    assert client.get("/api/admin/settings").json()["connectivity_profile"] == "auto"