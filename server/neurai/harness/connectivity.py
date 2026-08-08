"""Connectivity profiles (§2.1) — the one place mode semantics are encoded.

- air_gapped: cloud code paths disabled outright. No probes, no telemetry,
  nothing ever attempts the network. `cloud_allowed()` is False before any
  other check runs.
- auto: cloud is used only where consent allows it, and degrades silently to
  local when unreachable.

Per-workspace/per-meeting local-only flags are enforced in Harness.complete()
on top of this.
"""
from __future__ import annotations

import time

import httpx

from neurai.config import get_config
from neurai.db import get_db

PROFILE_KEY = "connectivity_profile"       # air_gapped | auto
CLOUD_ENABLED_KEY = "cloud_enabled"        # "1" once the admin turns cloud on

_PROBE_CACHE: dict[str, tuple[float, bool]] = {}
_PROBE_TTL_S = 30.0


def get_profile() -> str:
    db = get_db()
    return db.get_setting(PROFILE_KEY) or get_config().connectivity_profile


def cloud_enabled_globally() -> bool:
    return get_db().get_setting(CLOUD_ENABLED_KEY, "0") == "1"


def cloud_allowed() -> bool:
    """Profile + admin switch. This gate runs before any network code."""
    if get_profile() == "air_gapped":
        return False
    return cloud_enabled_globally()


def probe_cloud(url: str | None = None, timeout: float = 3.0) -> bool:
    """Reachability probe, cached. Never called under air_gapped."""
    if not cloud_allowed():
        return False
    cfg = get_config()
    target = url or cfg.openrouter_url
    now = time.monotonic()
    cached = _PROBE_CACHE.get(target)
    if cached and now - cached[0] < _PROBE_TTL_S:
        return cached[1]
    ok = False
    try:
        httpx.head(target, timeout=timeout)
        ok = True
    except Exception:
        ok = False
    _PROBE_CACHE[target] = (now, ok)
    return ok


def reset_probe_cache() -> None:
    _PROBE_CACHE.clear()
