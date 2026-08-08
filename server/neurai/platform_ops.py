"""Platform operations shared by the REST admin API and the platform-control
skills (D7 amendment).

This module exists for one architectural reason: the assistant must get no
capability the REST API doesn't already have, with identical checks — so
both surfaces call these functions, and the D12 chain logging happens HERE,
in the one shared path. No duplicated deletion logic anywhere.

Callers are responsible for authentication/authorization context (REST deps
or Skill Runtime admin enforcement); these functions do the operation, its
operational guards, and the D12 chain record.
"""
from __future__ import annotations

from typing import Any

from neurai.config import get_config
from neurai.db import get_db
from neurai.harness import connectivity
from neurai.security import adminlog

# Runtime-mutable, non-secret settings (the REST PUT /settings whitelist).
MUTABLE_SETTINGS = {
    "connectivity_profile",   # air_gapped | auto
    "server_mode",            # offline | online (D15 — the ONE cloud switch)
    "cloud_chat_model",       # chat/skills/translation (D15)
    "cloud_heavy_model",      # summaries/action items/minutes (D15)
    "cloud_asr_model",        # cloud transcription model (D15)
    "local_chat_model",
    "embed_model",
}
SECRET_KEYS = {"openrouter_key", "supabase_url", "supabase_key",
               "cloud_asr_url", "cloud_asr_key"}
# security-relevant changes get a D12 chain record (never secret values)
D12_LOGGED = {"connectivity_profile", "server_mode"} | SECRET_KEYS

_SETTING_VALIDATORS = {
    "connectivity_profile": ("air_gapped", "auto"),
    "server_mode": ("offline", "online"),
}


class OperationError(Exception):
    """User-facing operational failure (Persian message)."""


def _check_mode_switch(mode: str) -> None:
    """D15 gate for server_mode changes. Going online requires the internet
    to actually be reachable; the air-gapped profile has no online option."""
    if connectivity.get_profile() == "air_gapped":
        raise OperationError("در پروفایل ایزوله، حالت آنلاین وجود ندارد")
    if mode == "online" and not connectivity.probe_internet():
        raise OperationError("اینترنت در دسترس نیست؛ سرور نمی‌تواند آنلاین شود")


def mode_status() -> dict:
    """{mode, online_available} — the UI disables the Online button when the
    server has no internet (air-gapped: always unavailable)."""
    profile = connectivity.get_profile()
    if profile == "air_gapped":
        return {"mode": "offline", "online_available": False}
    return {
        "mode": connectivity.get_server_mode(),
        "online_available": connectivity.probe_internet(),
    }


def apply_settings(changes: dict[str, Any], actor: str) -> dict[str, str]:
    """Apply mutable settings + secrets; one D12 record for the whole change
    set. Returns the change kinds that were applied. Raises OperationError on
    an invalid key/value (nothing partially applied before validation)."""
    db = get_db()

    # validate everything before applying anything
    normalized: dict[str, Any] = {}
    for key, value in changes.items():
        if key in SECRET_KEYS:
            normalized[key] = value
            continue
        if key not in MUTABLE_SETTINGS:
            raise OperationError(f"تنظیم «{key}» قابل تغییر نیست")
        if isinstance(value, bool):
            value = "1" if value else "0"
        value = str(value)
        allowed = _SETTING_VALIDATORS.get(key)
        if allowed and value not in allowed:
            raise OperationError(f"مقدار «{value}» برای «{key}» معتبر نیست")
        if key == "server_mode":
            _check_mode_switch(value)  # D15: probe-gated, air-gapped locked
        normalized[key] = value

    logged: dict[str, str] = {}
    for key, value in normalized.items():
        if key in SECRET_KEYS:
            from neurai.security import delete_secret, set_secret

            if value:
                set_secret(key, str(value))
            else:
                delete_secret(key)
            logged[key] = "set" if value else "cleared"
            continue
        db.set_setting(key, value)
        if key in D12_LOGGED:
            logged[key] = value
    if logged:
        adminlog.append(actor, "settings_changed", logged)
    connectivity.reset_probe_cache()
    return logged


def remove_meeting(meeting_id: int, actor: str) -> dict[str, Any]:
    """Admin removal, any owner: true deletion (D4) + D12 chain record.
    Raises LookupError (not found) / OperationError (recording live)."""
    from neurai.api.meetings import purge_meeting_data
    from neurai.audio import get_session_manager

    meeting = get_db().query_one("SELECT * FROM meetings WHERE id=?", (meeting_id,))
    if meeting is None:
        raise LookupError("جلسه پیدا نشد")
    if get_session_manager().get(meeting_id) is not None:
        raise OperationError("جلسه در حال ضبط است؛ ابتدا آن را متوقف کنید")
    purge_meeting_data(meeting)
    adminlog.append(
        actor=actor,
        action="meeting_removed",
        details={"meeting_id": meeting_id, "owner_id": meeting["owner_id"],
                 "title": meeting["title"]},
    )
    return {"meeting_id": meeting_id, "title": meeting["title"]}


def remove_document(doc_id: int, actor: str, *, requester_user_id: int,
                    is_admin: bool) -> dict[str, Any]:
    """Delete a document + its index entries. Owners may delete their own;
    admins may delete any (that cross-owner case is a destructive admin
    action → D12 chain record). Raises LookupError when not found or not
    permitted (identical shape — ownership isn't probeable)."""
    from pathlib import Path

    db = get_db()
    doc = db.query_one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if doc is None or (doc["owner_id"] != requester_user_id and not is_admin):
        raise LookupError("سند پیدا نشد")
    db.execute("DELETE FROM rag_chunks WHERE owner_id=? AND kind='document' AND ref_id=?",
               (doc["owner_id"], doc_id))
    db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    try:
        Path(doc["path"]).unlink(missing_ok=True)
    except OSError:
        pass
    if doc["owner_id"] != requester_user_id:
        adminlog.append(actor, "document_removed",
                        {"document_id": doc_id, "owner_id": doc["owner_id"],
                         "filename": doc["filename"]})
    return {"document_id": doc_id, "filename": doc["filename"]}


def trigger_backup(actor: str) -> int:
    """Queue a snapshot backup (D4). Guards: air-gapped hard-disabled,
    Supabase must be configured. Returns the job id."""
    from neurai.jobs import get_job_queue
    from neurai.security import get_secret

    if connectivity.get_profile() == "air_gapped":
        raise OperationError("در پروفایل ایزوله، پشتیبان‌گیری ابری غیرفعال است")
    if not (get_secret("supabase_url") and get_secret("supabase_key")):
        raise OperationError("Supabase پیکربندی نشده است")
    return get_job_queue().enqueue("backup_snapshot", {"actor": actor}, priority=7)


def platform_status() -> dict[str, Any]:
    """Operational snapshot: profile, cloud readiness, live meeting, jobs."""
    from neurai.audio import get_session_manager
    from neurai.security import get_secret

    cfg = get_config()
    db = get_db()
    return {
        "profile": connectivity.get_profile(),
        "cloud_allowed": connectivity.cloud_allowed(),
        "openrouter_configured": bool(get_secret("openrouter_key") or cfg.openrouter_key),
        "supabase_configured": bool(get_secret("supabase_url") and get_secret("supabase_key")),
        "live_meeting_active": get_session_manager().any_live(),
        "jobs": {
            row["status"]: row["n"]
            for row in db.query("SELECT status, COUNT(*) n FROM jobs GROUP BY status")
        },
        "users": db.query_one("SELECT COUNT(*) n FROM users")["n"],
        "meetings": db.query_one("SELECT COUNT(*) n FROM meetings")["n"],
    }
