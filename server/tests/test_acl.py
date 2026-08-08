"""The D7 rule-1 proof: a user provably cannot reach another user's meetings —
neither over REST nor through the assistant's skills."""
import pytest

from conftest import as_user, signup


@pytest.fixture()
def two_users(client):
    admin_token = signup(client, "alice")  # admin
    as_user(client, admin_token)
    r = client.post("/api/meetings", json={"title": "جلسه محرمانه علیرضا"})
    meeting_id = r.json()["id"]
    bob_token = signup(client, "bob")
    return admin_token, bob_token, meeting_id


def test_rest_isolation(client, two_users):
    _alice, bob, meeting_id = two_users
    as_user(client, bob)
    assert client.get(f"/api/meetings/{meeting_id}").status_code == 404
    assert client.get(f"/api/meetings/{meeting_id}/transcript").status_code == 404
    assert client.get(f"/api/meetings/{meeting_id}/audio").status_code == 404
    assert client.get("/api/meetings").json() == []


def test_skill_isolation(client, two_users):
    """Even asking the assistant directly for the other user's meeting id
    returns 'not found' — the ACL is a WHERE clause, not a prompt rule."""
    import anyio

    from neurai.skills import SkillContext, get_skill_runtime
    from neurai.db import get_db

    _alice, bob, meeting_id = two_users
    bob_row = get_db().query_one("SELECT id FROM users WHERE username='bob'")
    ctx = SkillContext(user_id=bob_row["id"], username="bob")

    async def attempt():
        rt = get_skill_runtime()
        return await rt.execute("get_transcript", {"meeting_id": meeting_id}, ctx)

    result = anyio.run(attempt)
    assert "error" in result
    assert "transcript" not in result

    # and the attempt is audited
    row = get_db().query_one(
        "SELECT * FROM audit_log WHERE user_id=? AND skill='get_transcript' ORDER BY id DESC",
        (bob_row["id"],),
    )
    assert row is not None
    assert row["ok"] == 0
