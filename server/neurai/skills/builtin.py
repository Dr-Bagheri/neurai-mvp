"""First-party skills (D7). MVP ships these only; third-party skills are a
later phase with their own design review.

Every data access is scoped to ctx.user_id — a "not found" is returned
identically whether the resource doesn't exist or belongs to someone else,
so ownership can't be probed through the assistant.
"""
from __future__ import annotations

import json
from typing import Any

from neurai.db import get_db
from neurai.fa import fa_normalize
from neurai.harness import get_harness
from neurai.harness.harness import Constraints
from neurai.rag import search_chunks
from neurai.rag.ingest import transcript_text

from .runtime import SkillContext, SkillError, SkillManifest, SkillRuntime

_NOT_FOUND_FA = "جلسه پیدا نشد"


def _own_meeting(ctx: SkillContext, meeting_id: int):
    row = get_db().query_one(
        "SELECT * FROM meetings WHERE id=? AND owner_id=?",  # ACL = WHERE clause (D7 rule 1)
        (meeting_id, ctx.user_id),
    )
    if row is None:
        raise SkillError(_NOT_FOUND_FA)
    return row


def _constraints(ctx: SkillContext) -> Constraints:
    return Constraints(allow_cloud=ctx.allow_cloud)  # rule 4: consent propagates


def _meeting_constraints(ctx: SkillContext, meeting) -> Constraints:
    # D3: cloud needs BOTH the caller's consent and the meeting's own opt-in;
    # confidential meetings always carry allow_cloud=0 (D4).
    return Constraints(allow_cloud=ctx.allow_cloud and bool(meeting["allow_cloud"]))


# -- read skills ---------------------------------------------------------------

async def list_meetings(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    limit = min(int(params.get("limit", 20)), 100)
    rows = get_db().query(
        "SELECT id, title, status, started_at, created_at FROM meetings "
        "WHERE owner_id=? ORDER BY created_at DESC LIMIT ?",
        (ctx.user_id, limit),
    )
    return {"meetings": [dict(r) for r in rows]}


async def get_transcript(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    meeting = _own_meeting(ctx, int(params["meeting_id"]))
    text = transcript_text(meeting["id"])
    if not text:
        raise SkillError("رونوشتی برای این جلسه موجود نیست")
    return {"meeting_id": meeting["id"], "title": meeting["title"],
            "transcript": text, "resource": f"meeting:{meeting['id']}"}


async def search_transcripts(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    hits = await search_chunks(ctx.user_id, params["query"], kind="transcript",
                               top_k=min(int(params.get("top_k", 6)), 20))
    return {
        "results": [
            {"meeting_id": h.ref_id, "text": h.text, "score": round(h.score, 4)}
            for h in hits
        ],
        "resource": "transcripts",
    }


async def search_documents(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    hits = await search_chunks(ctx.user_id, params["query"], kind="document",
                               top_k=min(int(params.get("top_k", 6)), 20))
    return {
        "results": [
            {"document_id": h.ref_id, "text": h.text, "score": round(h.score, 4)}
            for h in hits
        ],
        "resource": "documents",
    }


async def list_open_action_items(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    rows = get_db().query(
        "SELECT id, meeting_id, assignee, text, due_date, status FROM action_items "
        "WHERE owner_id=? AND status='open' ORDER BY due_date IS NULL, due_date, id",
        (ctx.user_id,),
    )
    return {"action_items": [dict(r) for r in rows], "resource": "action_items"}


# -- LLM skills ------------------------------------------------------------------

_SUMMARY_PROMPT = (
    "تو دستیار جلسات هستی. از رونوشت جلسه یک خلاصه‌ی ساخت‌یافته به فارسی رسمی بنویس: "
    "موضوعات اصلی، تصمیم‌ها، و نکات مهم. کوتاه و دقیق."
)


async def summarize_meeting(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    meeting = _own_meeting(ctx, int(params["meeting_id"]))
    text = transcript_text(meeting["id"])
    if not text:
        raise SkillError("رونوشتی برای این جلسه موجود نیست")
    result = await get_harness().summarize_long(
        "summarize", _SUMMARY_PROMPT, text, _meeting_constraints(ctx, meeting),
    )
    summary = fa_normalize(result.text)
    get_db().insert(
        "INSERT INTO summaries(meeting_id, kind, content, source, model) VALUES(?,?,?,?,?)",
        (meeting["id"], "summary", summary, result.source, result.model),
    )
    return {"meeting_id": meeting["id"], "summary": summary,
            "source": result.source, "resource": f"meeting:{meeting['id']}"}


_ACTION_ITEMS_PROMPT = (
    "از رونوشت جلسه فقط اقدام‌ها (کارهایی که باید انجام شود) را استخراج کن. "
    "خروجی را فقط به صورت JSON آرایه بده: "
    '[{"text": "...", "assignee": "...", "due": null}] '
    "اگر مسئول یا مهلت مشخص نیست، مقدار را خالی بگذار."
)


def _parse_json_array(text: str) -> list[dict[str, Any]]:
    """Extract the first JSON array from model output (models wrap in prose)."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(text[start:end + 1])
        return [d for d in data if isinstance(d, dict)]
    except json.JSONDecodeError:
        return []


async def extract_action_items(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    meeting = _own_meeting(ctx, int(params["meeting_id"]))
    text = transcript_text(meeting["id"])
    if not text:
        raise SkillError("رونوشتی برای این جلسه موجود نیست")
    result = await get_harness().summarize_long(
        "summarize", _ACTION_ITEMS_PROMPT, text, _meeting_constraints(ctx, meeting),
        reduce_prompt="فهرست‌های اقدام زیر را ادغام کن و موارد تکراری را حذف کن. فقط JSON آرایه بده.",
    )
    items = _parse_json_array(result.text)
    db = get_db()
    stored = []
    for item in items:
        item_text = str(item.get("text", "")).strip()
        if not item_text:
            continue
        item_id = db.insert(
            "INSERT INTO action_items(meeting_id, owner_id, assignee, text, due_date) "
            "VALUES(?,?,?,?,?)",
            (meeting["id"], ctx.user_id, str(item.get("assignee") or ""),
             fa_normalize(item_text), item.get("due")),
        )
        stored.append({"id": item_id, "text": item_text,
                       "assignee": item.get("assignee") or ""})
    return {"meeting_id": meeting["id"], "action_items": stored,
            "source": result.source, "resource": f"meeting:{meeting['id']}"}


async def translate(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    direction = params.get("direction", "fa-en")
    target = "انگلیسی" if direction == "fa-en" else "فارسی"
    result = await get_harness().complete(
        "translate",
        [{"role": "system", "content": f"متن زیر را به {target} ترجمه کن. فقط ترجمه را بنویس."},
         {"role": "user", "content": params["text"]}],
        _constraints(ctx),
    )
    return {"translation": result.text.strip(), "source": result.source}


async def formalize_text(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    """Register conversion گفتاری → نوشتاری (D5)."""
    result = await get_harness().complete(
        "formalize",
        [{"role": "system", "content":
            "متن فارسی گفتاری زیر را به فارسی رسمی و نوشتاری بازنویسی کن. "
            "معنا را تغییر نده، فقط سبک را رسمی کن (مثلاً «می‌خوایم» → «می‌خواهیم»)."},
         {"role": "user", "content": params["text"]}],
        _constraints(ctx),
    )
    return {"formal_text": fa_normalize(result.text.strip()), "source": result.source}


async def merge_notes(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    """Merge the user's in-meeting notepad with the transcript (D2 UX)."""
    meeting = _own_meeting(ctx, int(params["meeting_id"]))
    notes = get_db().query(
        "SELECT t_ms, text FROM meeting_notes WHERE meeting_id=? AND user_id=? ORDER BY id",
        (meeting["id"], ctx.user_id),
    )
    if not notes:
        raise SkillError("یادداشتی برای این جلسه ثبت نشده است")
    text = transcript_text(meeting["id"])
    notes_text = "\n".join(f"- {n['text']}" for n in notes)
    result = await get_harness().summarize_long(
        "merge_notes",
        "یادداشت‌های شخصی کاربر و رونوشت جلسه را در صورت‌جلسه‌ای ساخت‌یافته و رسمی ادغام کن. "
        f"یادداشت‌های کاربر:\n{notes_text}\n\nرونوشت جلسه در پیام کاربر می‌آید.",
        text or "(رونوشت در دسترس نیست)",
        _meeting_constraints(ctx, meeting),
    )
    merged = fa_normalize(result.text)
    get_db().insert(
        "INSERT INTO summaries(meeting_id, kind, content, source, model) VALUES(?,?,?,?,?)",
        (meeting["id"], "minutes", merged, result.source, result.model),
    )
    return {"meeting_id": meeting["id"], "minutes": merged,
            "source": result.source, "resource": f"meeting:{meeting['id']}"}


async def recap_meeting_series(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    """'What happened since last time' for a meeting series (cross-meeting)."""
    series_id = int(params["series_id"])
    db = get_db()
    series = db.query_one(
        "SELECT * FROM meeting_series WHERE id=? AND owner_id=?", (series_id, ctx.user_id),
    )
    if series is None:
        raise SkillError("سری جلسات پیدا نشد")
    meetings = db.query(
        "SELECT id, title, started_at FROM meetings "
        "WHERE series_id=? AND owner_id=? AND status='done' "
        "ORDER BY started_at DESC LIMIT ?",
        (series_id, ctx.user_id, min(int(params.get("last_n", 3)), 10)),
    )
    if not meetings:
        raise SkillError("جلسه‌ی تمام‌شده‌ای در این سری نیست")
    parts = []
    for m in meetings:
        summary = db.query_one(
            "SELECT content FROM summaries WHERE meeting_id=? AND kind='summary' "
            "ORDER BY id DESC LIMIT 1", (m["id"],),
        )
        body = summary["content"] if summary else transcript_text(m["id"])[:4000]
        parts.append(f"## {m['title']} ({m['started_at']})\n{body}")
    result = await get_harness().summarize_long(
        "summarize",
        "خلاصه‌های چند جلسه از یک سری جلسات در ادامه می‌آید. یک بازخوانی «از جلسه قبل تاکنون» "
        "بنویس: روند تصمیم‌ها، موضوعات تکرارشونده، و کارهای باز.",
        "\n\n".join(parts),
        _constraints(ctx),
    )
    return {"series_id": series_id, "recap": fa_normalize(result.text),
            "source": result.source,
            "meetings_consulted": [m["id"] for m in meetings],
            "resource": f"series:{series_id}"}


# -- side-effectful skills ---------------------------------------------------------

async def export_minutes(ctx: SkillContext, params: dict[str, Any]) -> dict[str, Any]:
    """Export minutes/صورتجلسه/SRT. side_effect=True → needs a UI confirmation."""
    from neurai.minutes.export import export_meeting

    meeting = _own_meeting(ctx, int(params["meeting_id"]))
    fmt = params.get("format", "docx")
    template = params.get("template", "soorat_jalase")
    path = await export_meeting(meeting["id"], ctx, fmt=fmt, template=template)
    return {"meeting_id": meeting["id"], "file": path.name,
            "download": f"/api/meetings/{meeting['id']}/exports/{path.name}",
            "resource": f"meeting:{meeting['id']}"}


# -- registration -------------------------------------------------------------------

def register_builtin_skills(rt: SkillRuntime) -> None:
    def obj(props: dict[str, Any], required: list[str]) -> dict[str, Any]:
        return {"type": "object", "properties": props, "required": required}

    meeting_id = {"meeting_id": {"type": "integer", "description": "شناسه جلسه"}}
    query = {"query": {"type": "string", "description": "عبارت جستجو"},
             "top_k": {"type": "integer"}}

    rt.register(SkillManifest(
        "list_meetings", "فهرست جلسات کاربر",
        obj({"limit": {"type": "integer"}}, []),
        frozenset({"read:meetings"})), list_meetings)
    rt.register(SkillManifest(
        "get_transcript", "دریافت رونوشت کامل یک جلسه",
        obj(dict(meeting_id), ["meeting_id"]),
        frozenset({"read:transcripts"})), get_transcript)
    rt.register(SkillManifest(
        "search_transcripts", "جستجوی معنایی در رونوشت همه جلسات کاربر",
        obj(dict(query), ["query"]),
        frozenset({"read:transcripts"})), search_transcripts)
    rt.register(SkillManifest(
        "search_documents", "جستجو در اسناد بارگذاری‌شده کاربر",
        obj(dict(query), ["query"]),
        frozenset({"read:documents"})), search_documents)
    rt.register(SkillManifest(
        "list_open_action_items", "فهرست اقدام‌های باز کاربر",
        obj({}, []),
        frozenset({"read:action_items"})), list_open_action_items)
    rt.register(SkillManifest(
        "summarize_meeting", "خلاصه‌سازی یک جلسه از روی رونوشت",
        obj(dict(meeting_id), ["meeting_id"]),
        frozenset({"read:transcripts", "llm:local", "llm:cloud"})), summarize_meeting)
    rt.register(SkillManifest(
        "extract_action_items", "استخراج اقدام‌ها از رونوشت جلسه",
        obj(dict(meeting_id), ["meeting_id"]),
        frozenset({"read:transcripts", "write:action_items", "llm:local", "llm:cloud"})),
        extract_action_items)
    rt.register(SkillManifest(
        "translate", "ترجمه فارسی↔انگلیسی",
        obj({"text": {"type": "string"},
             "direction": {"type": "string", "enum": ["fa-en", "en-fa"]}}, ["text"]),
        frozenset({"llm:local", "llm:cloud"})), translate)
    rt.register(SkillManifest(
        "formalize_text", "تبدیل فارسی گفتاری به نوشتاری رسمی",
        obj({"text": {"type": "string"}}, ["text"]),
        frozenset({"llm:local", "llm:cloud"})), formalize_text)
    rt.register(SkillManifest(
        "merge_notes", "ادغام یادداشت‌های کاربر با رونوشت جلسه",
        obj(dict(meeting_id), ["meeting_id"]),
        frozenset({"read:transcripts", "read:notes", "llm:local", "llm:cloud"})), merge_notes)
    rt.register(SkillManifest(
        "recap_meeting_series", "بازخوانی «از جلسه قبل تاکنون» برای سری جلسات",
        obj({"series_id": {"type": "integer"}, "last_n": {"type": "integer"}}, ["series_id"]),
        frozenset({"read:meetings", "read:transcripts", "llm:local", "llm:cloud"})),
        recap_meeting_series)
    rt.register(SkillManifest(
        "export_minutes", "خروجی گرفتن صورت‌جلسه (Word/SRT)",
        obj({**meeting_id,
             "format": {"type": "string", "enum": ["docx", "srt", "txt"]},
             "template": {"type": "string", "enum": ["soorat_jalase", "standup", "plain"]}},
            ["meeting_id"]),
        frozenset({"read:transcripts", "export:files", "llm:local", "llm:cloud"}),
        side_effect=True), export_minutes)
