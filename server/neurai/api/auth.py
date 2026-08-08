"""Auth API: local accounts, session cookies (D1). First run: /api/auth/setup
creates the admin account; afterwards only admins create users."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from neurai.auth.deps import SESSION_COOKIE, CurrentUser, current_admin, current_user
from neurai.auth.security import hash_password, login_limiter, new_session_token, verify_password
from neurai.config import get_config
from neurai.db import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=256)
    display_name: str = ""


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    is_admin: bool


def _needs_setup() -> bool:
    return get_db().query_one("SELECT 1 FROM users LIMIT 1") is None


def _set_cookie(response: Response, token: str) -> None:
    cfg = get_config()
    response.set_cookie(
        SESSION_COOKIE, token,
        httponly=True, samesite="lax",
        max_age=cfg.session_ttl_hours * 3600,
        # LAN deployment behind the self-signed cert (D1); secure flag kept off
        # so plain-http localhost dev works. The installer fronts HTTPS.
    )


def _create_session(user_id: int) -> str:
    cfg = get_config()
    token = new_session_token()
    expires = datetime.now(timezone.utc) + timedelta(hours=cfg.session_ttl_hours)
    get_db().execute(
        "INSERT INTO auth_sessions(token, user_id, expires_at) VALUES(?,?,?)",
        (token, user_id, expires.strftime("%Y-%m-%d %H:%M:%S")),
    )
    return token


@router.get("/status")
def status():
    return {"needs_setup": _needs_setup()}


@router.post("/setup", response_model=UserOut)
def setup(body: Credentials, response: Response):
    """Create the first (admin) account. Only works on an empty user table."""
    if not _needs_setup():
        raise HTTPException(409, "Setup already completed")
    db = get_db()
    user_id = db.insert(
        "INSERT INTO users(username, password_hash, display_name, is_admin) VALUES(?,?,?,1)",
        (body.username.lower(), hash_password(body.password), body.display_name or body.username),
    )
    _set_cookie(response, _create_session(user_id))
    return UserOut(id=user_id, username=body.username.lower(),
                   display_name=body.display_name or body.username, is_admin=True)


@router.post("/login", response_model=UserOut)
def login(body: Credentials, response: Response):
    username = body.username.lower()
    retry_after = login_limiter.retry_after(username)
    if retry_after:
        raise HTTPException(
            429, "به دلیل تلاش‌های ناموفق، ورود موقتاً قفل شده است",
            headers={"Retry-After": str(retry_after)},
        )
    db = get_db()
    row = db.query_one("SELECT * FROM users WHERE username=?", (username,))
    if row is None or not verify_password(body.password, row["password_hash"]):
        login_limiter.record_failure(username)
        raise HTTPException(401, "نام کاربری یا رمز عبور نادرست است")
    login_limiter.record_success(username)
    _set_cookie(response, _create_session(row["id"]))
    return UserOut(id=row["id"], username=row["username"],
                   display_name=row["display_name"], is_admin=bool(row["is_admin"]))


@router.post("/logout")
def logout(response: Response, user: CurrentUser = Depends(current_user)):
    get_db().execute("DELETE FROM auth_sessions WHERE user_id=?", (user.id,))
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser = Depends(current_user)):
    return UserOut(id=user.id, username=user.username,
                   display_name=user.display_name, is_admin=user.is_admin)


@router.post("/users", response_model=UserOut)
def create_user(body: Credentials, admin: CurrentUser = Depends(current_admin)):
    db = get_db()
    if db.query_one("SELECT 1 FROM users WHERE username=?", (body.username.lower(),)):
        raise HTTPException(409, "این نام کاربری قبلاً ثبت شده است")
    user_id = db.insert(
        "INSERT INTO users(username, password_hash, display_name, is_admin) VALUES(?,?,?,0)",
        (body.username.lower(), hash_password(body.password), body.display_name or body.username),
    )
    return UserOut(id=user_id, username=body.username.lower(),
                   display_name=body.display_name or body.username, is_admin=False)
