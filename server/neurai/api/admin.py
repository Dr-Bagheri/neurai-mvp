"""Admin API: connectivity profile, cloud switch, model settings, job queue
visibility (§4 dashboard), audit log review (D7 rule 5), user list."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from neurai.auth.deps import CurrentUser, current_admin
from neurai.config import get_config
from neurai.db import get_db
from neurai.harness import connectivity

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Setting whitelists/validation and the D12 chain logging live in
# neurai/platform_ops.py — the shared core the platform-control skills use
# too, so both surfaces have identical checks (D7 amendment).


class SettingsUpdate(BaseModel):
    connectivity_profile: str | None = Field(default=None, pattern="^(air_gapped|auto)$")
    server_mode: str | None = Field(default=None, pattern="^(offline|online)$")
    openrouter_key: str | None = None
    supabase_url: str | None = None
    supabase_key: str | None = None
    cloud_asr_url: str | None = None
    cloud_asr_key: str | None = None
    cloud_chat_model: str | None = None
    cloud_heavy_model: str | None = None
    cloud_asr_model: str | None = None
    local_chat_model: str | None = None
    embed_model: str | None = None


class ModeUpdate(BaseModel):
    mode: str = Field(pattern="^(offline|online)$")


@router.get("/settings")
def get_settings(admin: CurrentUser = Depends(current_admin)):
    from neurai.security import get_secret

    db = get_db()
    cfg = get_config()
    from neurai.audio.cloud_asr import provider_config

    out = {
        "connectivity_profile": db.get_setting("connectivity_profile") or cfg.connectivity_profile,
        "server_mode": connectivity.get_server_mode(),
        "local_chat_model": db.get_setting("local_chat_model") or cfg.local_chat_model,
        "cloud_chat_model": db.get_setting("cloud_chat_model") or cfg.cloud_chat_model,
        "cloud_heavy_model": db.get_setting("cloud_heavy_model") or cfg.cloud_heavy_model,
        "cloud_asr_model": db.get_setting("cloud_asr_model") or cfg.cloud_asr_model,
        "embed_model": db.get_setting("embed_model") or cfg.embed_model,
        "openrouter_key_set": bool(get_secret("openrouter_key") or cfg.openrouter_key),
        "supabase_configured": bool(get_secret("supabase_url") and get_secret("supabase_key")),
        "cloud_asr_configured": provider_config() is not None,
    }
    return out


@router.get("/mode")
def get_mode(admin: CurrentUser = Depends(current_admin)):
    """D15: {mode, online_available} — the UI disables the Online button when
    the internet is unreachable; air-gapped has no online option at all."""
    from neurai.platform_ops import mode_status

    return mode_status()


@router.put("/mode")
def set_mode(body: ModeUpdate, admin: CurrentUser = Depends(current_admin)):
    """Switch offline/online. Going online is probe-gated (D15) and every
    change is D12-chained via the shared settings path."""
    from neurai.platform_ops import OperationError, apply_settings, mode_status

    try:
        apply_settings({"server_mode": body.mode}, actor=admin.username)
    except OperationError as e:
        raise HTTPException(409, str(e))
    return mode_status()


@router.put("/settings")
def update_settings(body: SettingsUpdate, admin: CurrentUser = Depends(current_admin)):
    from neurai.platform_ops import OperationError, apply_settings

    try:
        apply_settings(body.model_dump(exclude_none=True), actor=admin.username)
    except OperationError as e:
        raise HTTPException(400, str(e))
    return get_settings(admin)


@router.get("/cloud-status")
def cloud_status(admin: CurrentUser = Depends(current_admin)):
    """Booleans only — the UI renders enabled/disabled cloud buttons off this;
    secret values never leave the store."""
    from neurai.security import get_secret

    cfg = get_config()
    return {
        "profile": connectivity.get_profile(),
        "openrouter_configured": bool(get_secret("openrouter_key") or cfg.openrouter_key),
        "supabase_configured": bool(get_secret("supabase_url") and get_secret("supabase_key")),
    }


@router.post("/backup")
def trigger_backup(admin: CurrentUser = Depends(current_admin)):
    """Manual snapshot backup to Supabase storage (D4: backup, not sync).
    Guards live in the shared core (air-gapped hard-disabled)."""
    from neurai import platform_ops

    try:
        job_id = platform_ops.trigger_backup(actor=admin.username)
    except platform_ops.OperationError as e:
        status = 403 if "ایزوله" in str(e) else 400
        raise HTTPException(status, str(e))
    return {"job_id": job_id}


@router.get("/status")
def system_status(admin: CurrentUser = Depends(current_admin)):
    from neurai.platform_ops import platform_status

    return platform_status()


@router.get("/jobs")
def list_jobs(limit: int = 50, admin: CurrentUser = Depends(current_admin)):
    rows = get_db().query(
        "SELECT id, kind, status, priority, progress, error, created_at, started_at, finished_at "
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


# -- admin archive management + D12 tamper-evident log ---------------------------

@router.get("/meetings")
def list_all_meetings(admin: CurrentUser = Depends(current_admin)):
    """Archive view across all users (admin role)."""
    rows = get_db().query(
        """SELECT m.id, m.title, m.status, m.owner_id, u.username AS owner,
                  m.sensitivity, m.started_at, m.created_at
           FROM meetings m JOIN users u ON u.id = m.owner_id
           ORDER BY m.created_at DESC, m.id DESC""",
    )
    return [dict(r) for r in rows]


@router.delete("/meetings/{meeting_id}")
def admin_remove_meeting(meeting_id: int, admin: CurrentUser = Depends(current_admin)):
    """Admin-scoped removal (any owner). True deletion (D4) + D12 chain, via
    the shared core (platform_ops) the delete_meeting skill also calls."""
    from neurai.platform_ops import OperationError, remove_meeting

    try:
        remove_meeting(meeting_id, actor=admin.username)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except OperationError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@router.get("/audit-file")
def read_audit_file(limit: int = 200, admin: CurrentUser = Depends(current_admin)):
    """The hash-chained admin audit log (D12). Read-only — no API modifies it."""
    from neurai.security import adminlog

    records = adminlog.read_all()
    return records[-min(limit, 2000):]


@router.get("/audit-file/verify")
def verify_audit_file(admin: CurrentUser = Depends(current_admin)):
    from neurai.security import adminlog

    return adminlog.verify()
