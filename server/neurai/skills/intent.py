"""Intent router (D7 two-tier invocation).

8B local models are unreliable agentic drivers, so common asks are matched
deterministically and invoke the skill directly — no agent loop. Anything
unmatched falls through to the harness tool-use loop.

Matching is normalization-first (fa_normalize) + keyword/regex. This is
intentionally simple; precision matters more than recall because the
fallthrough path still works.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from neurai.db import get_db
from neurai.fa import fa_normalize


@dataclass
class Intent:
    skill: str
    params: dict[str, Any]


def _latest_meeting_id(user_id: int, day: date | None = None) -> int | None:
    db = get_db()
    if day is not None:
        row = db.query_one(
            "SELECT id FROM meetings WHERE owner_id=? AND date(created_at)=? "
            "ORDER BY id DESC LIMIT 1",
            (user_id, day.isoformat()),
        )
        if row:
            return row["id"]
        return None
    row = db.query_one(
        "SELECT id FROM meetings WHERE owner_id=? ORDER BY id DESC LIMIT 1",
        (user_id,),
    )
    return row["id"] if row else None


def _resolve_meeting(text: str, user_id: int) -> int | None:
    m = re.search(r"جلسه[\s‌]*(?:شماره\s*)?(\d+)", text)
    if m:
        return int(m.group(1))
    if "دیروز" in text:
        return _latest_meeting_id(user_id, date.today() - timedelta(days=1))
    if "امروز" in text:
        return _latest_meeting_id(user_id, date.today())
    if re.search(r"آخرین|قبلی|اخیر", text):
        return _latest_meeting_id(user_id)
    return None


_SUMMARIZE = re.compile(r"خلاصه|جمع[\s‌]?بندی|summar", re.IGNORECASE)
_ACTIONS = re.compile(r"اقدام|کارها|وظایف|action", re.IGNORECASE)
_OPEN_ACTIONS = re.compile(r"(اقدام|کار|وظیفه)[^.]*باز|چه کارهایی مانده", re.IGNORECASE)
_SEARCH = re.compile(r"کجا (گفتیم|بحث|صحبت)|پیدا کن|جستجو|search", re.IGNORECASE)
_MEETING_WORD = re.compile(r"جلسه|میتینگ|meeting", re.IGNORECASE)


def route(text: str, user_id: int) -> Intent | None:
    """Return a direct skill invocation for common asks, else None."""
    t = fa_normalize(text)

    if _OPEN_ACTIONS.search(t):
        return Intent("list_open_action_items", {})

    if _MEETING_WORD.search(t):
        meeting_id = _resolve_meeting(t, user_id)
        if meeting_id is not None:
            if _SUMMARIZE.search(t):
                return Intent("summarize_meeting", {"meeting_id": meeting_id})
            if _ACTIONS.search(t):
                return Intent("extract_action_items", {"meeting_id": meeting_id})

    if _SEARCH.search(t):
        # strip the trigger phrase; the residue is the query
        query = _SEARCH.sub("", t).strip(" ؟?،.")
        if len(query) >= 2:
            return Intent("search_transcripts", {"query": query})

    return None
