"""RAG scoping + chat flows (intent tier and provenance)."""
import anyio

from conftest import as_user, signup


def test_rag_owner_scoping(client):
    """Vector search candidates are WHERE owner_id=? — B never sees A's chunks."""
    signup(client, "alice")
    from neurai.db import get_db
    from neurai.rag import index_text, search_chunks

    db = get_db()
    alice = db.query_one("SELECT id FROM users WHERE username='alice'")["id"]
    signup(client, "bob")
    bob = db.query_one("SELECT id FROM users WHERE username='bob'")["id"]

    async def scenario():
        await index_text(alice, "transcript", 1, "بودجه پروژه نورای تصویب شد و مهلت تحویل مشخص شد")
        hits_alice = await search_chunks(alice, "بودجه پروژه")
        hits_bob = await search_chunks(bob, "بودجه پروژه")
        return hits_alice, hits_bob

    hits_alice, hits_bob = anyio.run(scenario)
    assert hits_alice and "بودجه" in hits_alice[0].text
    assert hits_bob == []


def _stub_harness():
    """Harness whose local backend echoes a canned answer."""
    from neurai.harness.backends import BackendReply
    from neurai.harness.harness import Harness
    import neurai.harness.harness as harness_mod

    class StubLocal:
        source = "local"

        async def chat(self, messages, tools=None, timeout=None, options=None):
            return BackendReply(text="خلاصه: بودجه تصویب شد.", model="stub-8b")

    h = Harness()
    h.set_backends(StubLocal, StubLocal)
    harness_mod.set_harness(h)
    return h


def test_chat_intent_tier_summarizes_with_provenance(client):
    signup(client, "admin")
    _stub_harness()
    from neurai.db import get_db

    meeting_id = client.post("/api/meetings", json={"title": "جلسه بودجه"}).json()["id"]
    db = get_db()
    db.insert(
        "INSERT INTO transcript_segments(meeting_id, pass, start_ms, end_ms, text) "
        "VALUES(?, 'quality', 0, 5000, "
        "'بودجه پروژه تصویب شد و قرار شد تیم فنی تا پایان ماه گزارش پیشرفت را ارائه کند')",
        (meeting_id,),
    )

    chat_id = client.post("/api/chats", json={"title": "گفتگو"}).json()["id"]
    r = client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": f"جلسه {meeting_id} رو خلاصه کن"},
    ).json()
    assert r["type"] == "message"
    assert r["via"] == "intent:summarize_meeting"
    assert r["source"] == "local"                       # 🏠 badge
    assert f"meeting:{meeting_id}" in r["provenance"]    # cites its source
    assert "خلاصه" in r["content"]

    # summary was persisted
    summaries = client.get(f"/api/meetings/{meeting_id}/summaries").json()
    assert summaries and summaries[0]["kind"] == "summary"

    # audited
    audit = client.get("/api/admin/audit").json()
    assert any(a["skill"] == "summarize_meeting" and a["ok"] for a in audit)


def test_chat_isolation_via_intent(client):
    """Bob asks the assistant to summarize Alice's meeting by id → not found."""
    signup(client, "alice")
    _stub_harness()
    meeting_id = client.post("/api/meetings", json={"title": "محرمانه"}).json()["id"]

    bob = signup(client, "bob")
    as_user(client, bob)
    chat_id = client.post("/api/chats", json={}).json()["id"]
    r = client.post(
        f"/api/chats/{chat_id}/messages",
        json={"content": f"جلسه {meeting_id} رو خلاصه کن"},
    ).json()
    assert r["type"] == "message"
    assert "پیدا نشد" in r["content"]


def test_action_items_crud_and_resurface(client):
    signup(client, "admin")
    series_id = client.post("/api/series", json={"title": "استندآپ هفتگی"}).json()["id"]
    meeting_id = client.post(
        "/api/meetings", json={"title": "استندآپ ۱", "series_id": series_id},
    ).json()["id"]

    item_id = client.post("/api/action-items", json={
        "text": "گزارش را آماده کن", "assignee": "sara", "meeting_id": meeting_id,
    }).json()["id"]

    open_items = client.get("/api/action-items", params={"status": "open"}).json()
    assert len(open_items) == 1

    # resurfacing: open items from the series show up for the next meeting
    resurfaced = client.get(f"/api/action-items/resurface/{series_id}").json()
    assert [i["id"] for i in resurfaced] == [item_id]

    client.patch(f"/api/action-items/{item_id}", json={"status": "done"})
    assert client.get(f"/api/action-items/resurface/{series_id}").json() == []
