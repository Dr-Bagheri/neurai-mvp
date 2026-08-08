"""User-scope system info.

GET /api/cloud: cloud readiness for ANY authenticated user, so the chat's
allow-cloud toggle can render (and explain) its state to everyone — the
admin-only /api/admin/cloud-status stays the admin's detailed view. Same
no-secret-leak rule: booleans + a reason enum, never values.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from neurai.auth.deps import CurrentUser, current_user
from neurai.config import get_config
from neurai.harness import connectivity

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/cloud")
def cloud_readiness(user: CurrentUser = Depends(current_user)):
    """cloud_ready = the harness COULD route to cloud for a consented request
    (profile allows it, admin enabled it, a key is configured). Reachability
    is not probed here — the harness degrades to local at request time anyway."""
    from neurai.security import get_secret

    cfg = get_config()
    profile = connectivity.get_profile()
    if profile == "air_gapped":
        reason = "air_gapped"
    elif not connectivity.is_online_mode():
        reason = "offline_mode"          # D15: the ONE admin switch is off
    elif not (get_secret("openrouter_key") or cfg.openrouter_key):
        reason = "no_api_key"
    else:
        reason = "ready"
    return {"cloud_ready": reason == "ready", "reason": reason}
