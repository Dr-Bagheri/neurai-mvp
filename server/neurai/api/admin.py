"""Admin API: connectivity profile, cloud switch, model settings, job queue
visibility (§4 dashboard), audit log review (D7 rule 5), user list."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from neurai.auth.deps import CurrentUser, current_admin
from neurai.config import get_config
from neurai.db import get_db
from neurai.harness import connectivity

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Settings the admin may change at runtime; anything else stays env/installer-owned.
_MUTABLE_SETTINGS = {
    "connectivity_profile",   # air_gapped | auto
    "cloud_enabled",          # "0" | "1"
    "openrouter_key",
    "cloud_chat_model",
    "local_chat_model",
    "embed_model",
}
_SECRET_SETTINGS = {"openrouter_key"}


class SettingsUpdate(BaseModel):
    connectivity_profile: str | None = Field(default=None, pattern="^(air_gapped|auto)$")
    cloud_enabled: bool | None = None
    openrouter_key: str | None = None
    cloud_chat_model: str | None = None
    local_chat_model: str | None = None
    embed_model: str | None = None


@router.get("/settings")
def get_settings(admin: CurrentUser = Depends(current_admin)):
    db = get_db()
    cfg = get_config()
    out = {
        "connectivity_profile": db.get_setting("connectivity_profile") or cfg.connectivity_profile,
        "cloud_enabled": db.get_setting("cloud_enabled", "0") == "1",
        "local_chat_model": db.get_setting("local_chat_model") or cfg.local_chat_model,
        "cloud_chat_model": db.get_setting("cloud_chat_model") or cfg.cloud_chat_model,
        "embed_model": db.get_setting("embed_model") or cfg.embed_model,
        "openrouter_key_set": bool(db.get_setting("openrouter_key") or cfg.openrouter_key),
    }
    return out


@router.put("/settings")
def update_settings(body: SettingsUpdate, admin: CurrentUser = Depends(current_admin)):
    db = get_db()
    data = body.model_dump(exclude_none=True)
    for key, value in data.items():
        if key not in _MUTABLE_SETTINGS:
            continue
        if key == "cloud_enabled":
            value = "1" if value else "0"
        db.set_setting(key, str(value))
    connectivity.reset_probe_cache()
    return get_settings(admin)


@router.get("/status")
def system_status(admin: CurrentUser = Depends(current_admin)):
    from neurai.audio import get_session_manager

    db = get_db()
    return {
        "profile": connectivity.get_profile(),
        "cloud_allowed": connectivity.cloud_allowed(),
        "live_meeting_active": get_session_manager().any_live(),
        "jobs": {
            row["status"]: row["n"]
            for row in db.query("SELECT status, COUNT(*) n FROM jobs GROUP BY status")
        },
        "users": db.query_one("SELECT COUNT(*) n FROM users")["n"],
        "meetings": db.query_one("SELECT COUNT(*) n FROM meetings")["n"],
    }


@router.get("/jobs")
def list_jobs(limit: int = 50, admin: CurrentUser = Depends(current_admin)):
    rows = get_db().query(
        "SELECT id, kind, status, priority, error, created_at, started_at, finished_at "
        "FROM jobs ORDER BY id DESC LIMIT ?",
        (min(limit, 500),),
    )
    return [dict(r) for r in rows]


@router.get("/audit")
def audit_log(limit: int = 100, admin: CurrentUser = Depends(current_admin)):
    """Append-only skill audit (who, which skill, which resource, local/cloud)."""
    rows = get_db().query(
        """SELECT a.id, a.user_id, u.username, a.skill, a.params, a.resource,
                  a.source, a.ok, a.error, a.created_at
           FROM audit_log a LEFT JOIN users u ON u.id = a.user_id
           ORDER BY a.id DESC LIMIT ?""",
        (min(limit, 1000),),
    )
    return [dict(r) for r in rows]


@router.get("/users")
def list_users(admin: CurrentUser = Depends(current_admin)):
    rows = get_db().query(
        "SELECT id, username, display_name, is_admin, created_at FROM users ORDER BY id",
    )
    return [dict(r) for r in rows]
