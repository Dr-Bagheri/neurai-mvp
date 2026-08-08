"""Skill Runtime rules (D7): validation, confirmation gate, audit log."""
import anyio
import pytest

from conftest import signup


@pytest.fixture()
def user_ctx(client):
    signup(client, "admin")
    from neurai.db import get_db
    from neurai.skills import SkillContext

    row = get_db().query_one("SELECT id FROM users WHERE username='admin'")
    return SkillContext(user_id=row["id"], username="admin", is_admin=True)


def test_unknown_skill_rejected_and_audited(client, user_ctx):
    from neurai.db import get_db
    from neurai.skills import get_skill_runtime

    result = anyio.run(get_skill_runtime().execute, "delete_everything", {}, user_ctx)
    assert "error" in result
    row = get_db().query_one("SELECT * FROM audit_log ORDER BY id DESC")
    assert row["skill"] == "delete_everything" and row["ok"] == 0


def test_param_validation(client, user_ctx):
    from neurai.skills import get_skill_runtime

    rt = get_skill_runtime()
    # missing required param
    result = anyio.run(rt.execute, "get_transcript", {}, user_ctx)
    assert "invalid parameters" in result["error"]
    # wrong type
    result = anyio.run(rt.execute, "get_transcript", {"meeting_id": "yes"}, user_ctx)
    assert "invalid parameters" in result["error"]
    # unknown param (injection surface)
    result = anyio.run(rt.execute, "list_meetings", {"owner_id": 999}, user_ctx)
    assert "invalid parameters" in result["error"]


def test_side_effect_requires_confirmation(client, user_ctx):
    """export_minutes must not run without ctx.confirmed — rule 2."""
    from neurai.skills import get_skill_runtime

    result = anyio.run(
        get_skill_runtime().execute, "export_minutes", {"meeting_id": 1}, user_ctx,
    )
    assert result.get("confirmation_required") is True


def test_read_skill_audited_on_success(client, user_ctx):
    from neurai.db import get_db
    from neurai.skills import get_skill_runtime

    result = anyio.run(get_skill_runtime().execute, "list_meetings", {}, user_ctx)
    assert result == {"meetings": []}
    row = get_db().query_one(
        "SELECT * FROM audit_log WHERE skill='list_meetings' ORDER BY id DESC",
    )
    assert row["ok"] == 1 and row["user_id"] == user_ctx.user_id


def test_intent_router(client, user_ctx):
    from neurai.db import get_db
    from neurai.skills.intent import route

    db = get_db()
    meeting_id = db.insert(
        "INSERT INTO meetings(owner_id, title) VALUES(?, 'جلسه هفتگی')", (user_ctx.user_id,),
    )

    intent = route("جلسه آخرین رو خلاصه کن", user_ctx.user_id)
    assert intent is not None
    assert intent.skill == "summarize_meeting"
    assert intent.params == {"meeting_id": meeting_id}

    intent = route(f"اقدام های جلسه {meeting_id} چی بود؟", user_ctx.user_id)
    assert intent is not None and intent.skill == "extract_action_items"

    intent = route("چه کارهایی مانده؟", user_ctx.user_id)
    assert intent is not None and intent.skill == "list_open_action_items"

    assert route("سلام، حالت چطوره؟", user_ctx.user_id) is None
