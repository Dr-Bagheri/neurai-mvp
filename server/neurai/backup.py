"""Encrypted snapshot backup to Supabase storage (D4: backup, NOT sync).

The snapshot is the SQLCipher database written through the same codec — the
uploaded object is ciphertext and the key never leaves the server (DPAPI
store), so Supabase never sees plaintext (true E2E per D4). Off by default,
never required, hard-disabled under the air-gapped profile (§2.1).

Manual trigger: POST /api/admin/backup → 'backup_snapshot' job.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

log = logging.getLogger("neurai.backup")

BUCKET = "neurai-backups"


async def _upload(url: str, key: str, bucket: str, name: str, data: bytes) -> None:
    """Supabase Storage REST upload. Module-level so tests can stub it."""
    endpoint = f"{url.rstrip('/')}/storage/v1/object/{bucket}/{name}"
    async with httpx.AsyncClient(timeout=300.0) as client:
        r = await client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/octet-stream",
                "x-upsert": "true",
            },
            content=data,
        )
        r.raise_for_status()


async def backup_snapshot_job(payload: dict[str, Any]) -> None:
    from neurai.config import get_config
    from neurai.db import get_db
    from neurai.harness import connectivity
    from neurai.security import get_secret

    # Guards re-checked at run time — the profile may have changed since the
    # job was queued, and air-gapped means no network path, ever (§2.1).
    if connectivity.get_profile() == "air_gapped":
        raise RuntimeError("backup skipped: air-gapped profile")
    url, key = get_secret("supabase_url"), get_secret("supabase_key")
    if not (url and key):
        raise RuntimeError("backup skipped: Supabase not configured")

    cfg = get_config()
    backups_dir = cfg.data_dir / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot = backups_dir / f"neurai-{stamp}.db"

    get_db().backup_to(snapshot)
    try:
        await _upload(url, key, BUCKET, snapshot.name, snapshot.read_bytes())
        log.info("backup %s uploaded (%d bytes), actor=%s",
                 snapshot.name, snapshot.stat().st_size, payload.get("actor", "?"))
    finally:
        snapshot.unlink(missing_ok=True)  # ciphertext, but no reason to accumulate
