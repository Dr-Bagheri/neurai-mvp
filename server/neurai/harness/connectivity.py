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
SERVER_MODE_KEY = "server_mode"            # offline | online (D15, default offline)

_PROBE_CACHE: dict[str, tuple[float, bool]] = {}
_PROBE_TTL_S = 30.0


def get_profile() -> str:
    db = get_db()
    return db.get_setting(PROFILE_KEY) or get_config().connectivity_profile


def get_server_mode() -> str:
    """D15: the ONE admin-facing switch. Air-gapped is locked offline."""
    if get_profile() == "air_gapped":
        return "offline"
    return get_db().get_setting(SERVER_MODE_KEY, "offline") or "offline"


def is_online_mode() -> bool:
    return get_server_mode() == "online"


def cloud_allowed() -> bool:
    """Profile + server mode — the single source of truth for the harness
    gate (D15 replaced the old cloud_enabled toggle; migration 004 mapped
    stored intent). This runs before any network code."""
    if get_profile() == "air_gapped":
        return False
    return is_online_mode()


def _probe(target: str, timeout: float = 3.0) -> bool:
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


def probe_internet(url: str | None = None, timeout: float = 3.0) -> bool:
    """Raw reachability (D15 mode gate + the UI's online_available flag).
    NOT gated on the current mode — you must be able to probe while offline
    to know whether Online can be offered. Air-gapped never probes."""
    if get_profile() == "air_gapped":
        return False
    return _probe(url or get_config().openrouter_url, timeout)


def probe_cloud(url: str | None = None, timeout: float = 3.0) -> bool:
    """Reachability probe for the harness gate: policy first, then network.
    Never called under air_gapped."""
    if not cloud_allowed():
        return False
    return _probe(url or get_config().openrouter_url, timeout)


def reset_probe_cache() -> None:
    _PROBE_CACHE.clear()
