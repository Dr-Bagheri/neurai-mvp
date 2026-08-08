"""FastAPI auth dependencies: session cookie → CurrentUser."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, WebSocket

from neurai.db import get_db

SESSION_COOKIE = "neurai_session"


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    display_name: str
    is_admin: bool


def _user_for_token(token: str | None) -> CurrentUser | None:
    if not token:
        return None
    db = get_db()
    row = db.query_one(
        """SELECT u.id, u.username, u.display_name, u.is_admin
           FROM auth_sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token = ? AND s.expires_at > datetime('now')""",
        (token,),
    )
    if not row:
        return None
    return CurrentUser(
        id=row["id"], username=row["username"],
        display_name=row["display_name"], is_admin=bool(row["is_admin"]),
    )


def current_user(request: Request) -> CurrentUser:
    user = _user_for_token(request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def current_admin(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def ws_current_user(websocket: WebSocket) -> CurrentUser | None:
    """Cookie auth on the WebSocket handshake (mic streaming, captions)."""
    return _user_for_token(websocket.cookies.get(SESSION_COOKIE))
