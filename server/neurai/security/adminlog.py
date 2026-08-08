"""Tamper-evident admin audit file (D12): hash-chained JSONL.

Every security-relevant admin event — above all destructive ones — appends a
record to <data_dir>/admin-audit.jsonl:

    {"ts", "actor", "action", "details", "prev_hash", "hash"}

where hash = SHA256(prev_hash || canonical_json(record-without-hash)) and the
first line is a genesis record with a random anchor. Any edit, deletion, or
reorder of a line breaks the chain; verify() walks it and reports the first
broken line. Written by the engine only; the API exposes read + verify to
admins and nothing that can modify or truncate it.

Guarantee scope (per D12): tamper-EVIDENCE against in-app/DB-level
manipulation and accidental edits — an attacker with full write access to
the data directory is out of MVP scope (D8/D11 consistent).

D12 rule: any new destructive admin capability MUST call append() in the
same code path that performs the action.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
FILE_NAME = "admin-audit.jsonl"


def _path() -> Path:
    from neurai.config import get_config

    cfg = get_config()
    cfg.ensure_dirs()
    return cfg.data_dir / FILE_NAME


def _canonical(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(prev_hash: str, record_without_hash: dict[str, Any]) -> str:
    return hashlib.sha256(
        (prev_hash + _canonical(record_without_hash)).encode("utf-8")
    ).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _last_hash(path: Path) -> str | None:
    """Hash of the last line, or None if the file doesn't exist/is empty."""
    if not path.exists():
        return None
    last = None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                last = line
    if last is None:
        return None
    return json.loads(last)["hash"]


def _append_line(path: Path, record: dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(_canonical(record) + "\n")
        f.flush()


def _ensure_genesis(path: Path) -> str:
    """Create the genesis record if the file is new; returns the last hash."""
    last = _last_hash(path)
    if last is not None:
        return last
    genesis: dict[str, Any] = {
        "ts": _now(),
        "actor": "system",
        "action": "genesis",
        "details": {"anchor": secrets.token_hex(16)},  # random anchor (D12)
        "prev_hash": "",
    }
    genesis["hash"] = _hash("", genesis)
    _append_line(path, genesis)
    return genesis["hash"]


def append(actor: str, action: str, details: dict[str, Any]) -> dict[str, Any]:
    """Append one admin event to the chain. Thread-safe."""
    with _LOCK:
        path = _path()
        prev = _ensure_genesis(path)
        record: dict[str, Any] = {
            "ts": _now(),
            "actor": actor,
            "action": action,
            "details": details,
            "prev_hash": prev,
        }
        record["hash"] = _hash(prev, record)
        _append_line(path, record)
        return record


def read_all() -> list[dict[str, Any]]:
    with _LOCK:
        path = _path()
        if not path.exists():
            return []
        out = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    out.append(json.loads(line))
        return out


def verify() -> dict[str, Any]:
    """Walk the chain: {'intact': bool, 'records': n, 'broken_at_line': int|None}."""
    with _LOCK:
        path = _path()
        if not path.exists():
            return {"intact": True, "records": 0, "broken_at_line": None}
        prev = ""
        count = 0
        with open(path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    claimed = record.pop("hash")
                except (json.JSONDecodeError, KeyError):
                    return {"intact": False, "records": count, "broken_at_line": lineno}
                if record.get("prev_hash") != prev or _hash(prev, record) != claimed:
                    return {"intact": False, "records": count, "broken_at_line": lineno}
                prev = claimed
                count += 1
        return {"intact": True, "records": count, "broken_at_line": None}
