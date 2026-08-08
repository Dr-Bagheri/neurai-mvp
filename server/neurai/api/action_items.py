"""Action-item tracker: live objects with assignee/due/status, plus the
"resurface open items when a recurring meeting starts" query."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from neurai.auth.deps import CurrentUser, current_user
from neurai.db import get_db

router = APIRouter(prefix="/api/action-items", tags=["action-items"])


class ActionItemCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    assignee: str = ""
    due_date: str | None = None
    meeting_id: int | None = None


class ActionItemUpdate(BaseModel):
    text: str | None = None
    assignee: str | None = None
    due_date: str | None = None
    status: str | None = Field(default=None, pattern="^(open|done|dropped)$")


def _own_item(user: CurrentUser, item_id: int):
    row = get_db().query_one(
        "SELECT * FROM action_items WHERE id=? AND owner_id=?", (item_id, user.id),
    )
    if row is None:
        raise HTTPException(404, "اقدام پیدا نشد")
    return row


@router.get("")
def list_items(status: str | None = None, user: CurrentUser = Depends(current_user)):
    db = get_db()
    if status:
        rows = db.query(
            "SELECT * FROM action_items WHERE owner_id=? AND status=? "
            "ORDER BY due_date IS NULL, due_date, id",
            (user.id, status),
        )
    else:
        rows = db.query(
            "SELECT * FROM action_items WHERE owner_id=? ORDER BY status='open' DESC, id DESC",
            (user.id,),
        )
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_item(body: ActionItemCreate, user: CurrentUser = Depends(current_user)):
    db = get_db()
    if body.meeting_id is not None:
        if db.query_one("SELECT 1 FROM meetings WHERE id=? AND owner_id=?",
                        (body.meeting_id, user.id)) is None:
            raise HTTPException(404, "جلسه پیدا نشد")
    item_id = db.insert(
        "INSERT INTO action_items(meeting_id, owner_id, assignee, text, due_date) VALUES(?,?,?,?,?)",
        (body.meeting_id, user.id, body.assignee, body.text, body.due_date),
    )
    return {"id": item_id}


@router.patch("/{item_id}")
def update_item(item_id: int, body: ActionItemUpdate, user: CurrentUser = Depends(current_user)):
    _own_item(user, item_id)
    fields, params = [], []
    for col in ("text", "assignee", "due_date", "status"):
        value = getattr(body, col)
        if value is not None:
            fields.append(f"{col}=?")
            params.append(value)
    if not fields:
        return {"ok": True}
    params.extend([item_id, user.id])
    get_db().execute(
        f"UPDATE action_items SET {', '.join(fields)}, updated_at=datetime('now') "
        "WHERE id=? AND owner_id=?",
        params,
    )
    return {"ok": True}


@router.get("/resurface/{series_id}")
def resurface(series_id: int, user: CurrentUser = Depends(current_user)):
    """Open items from earlier meetings of a series — shown when a recurring
    meeting starts."""
    db = get_db()
    if db.query_one("SELECT 1 FROM meeting_series WHERE id=? AND owner_id=?",
                    (series_id, user.id)) is None:
        raise HTTPException(404, "سری جلسات پیدا نشد")
    rows = db.query(
        """SELECT ai.* FROM action_items ai
           JOIN meetings m ON m.id = ai.meeting_id
           WHERE m.series_id=? AND ai.owner_id=? AND ai.status='open'
           ORDER BY ai.due_date IS NULL, ai.due_date, ai.id""",
        (series_id, user.id),
    )
    return [dict(r) for r in rows]
