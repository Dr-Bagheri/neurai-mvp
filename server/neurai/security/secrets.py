"""Secret storage (D8): the OpenRouter API key and the at-rest encryption key
live under **Windows DPAPI** for the service account — never in config files,
never in the settings table, never in the repo.

Secrets are stored as DPAPI-protected blobs in <data_dir>/secrets/<name>.bin.
On non-Windows hosts (D10: Linux via Docker) DPAPI does not exist; the
fallback stores the blob with owner-only file permissions and relies on the
container/OS boundary — the interface stays identical so packaging decides
the mechanism, not the callers.
"""
from __future__ import annotations

import logging
import os
import secrets as _secrets
import sys
from pathlib import Path

log = logging.getLogger("neurai.secrets")

_ENTROPY = b"neurai-v1"  # binds blobs to this application


def _secrets_dir() -> Path:
    from neurai.config import get_config

    d = get_config().data_dir / "secrets"
    d.mkdir(parents=True, exist_ok=True)
    return d


# -- DPAPI via ctypes (no extra dependency) -------------------------------------

def _dpapi_protect(data: bytes) -> bytes:
    import ctypes
    import ctypes.wintypes as wt

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _blob(b: bytes) -> DATA_BLOB:
        buf = ctypes.create_string_buffer(b, len(b))
        return DATA_BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    in_blob, entropy_blob, out_blob = _blob(data), _blob(_ENTROPY), DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob), None, ctypes.byref(entropy_blob), None, None, 0,
        ctypes.byref(out_blob),
    ):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    import ctypes
    import ctypes.wintypes as wt

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _blob(b: bytes) -> DATA_BLOB:
        buf = ctypes.create_string_buffer(b, len(b))
        return DATA_BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    in_blob, entropy_blob, out_blob = _blob(data), _blob(_ENTROPY), DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, ctypes.byref(entropy_blob), None, None, 0,
        ctypes.byref(out_blob),
    ):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


_IS_WINDOWS = sys.platform == "win32"


def set_secret(name: str, value: str) -> None:
    raw = value.encode("utf-8")
    blob = _dpapi_protect(raw) if _IS_WINDOWS else raw
    path = _secrets_dir() / f"{name}.bin"
    path.write_bytes(blob)
    if not _IS_WINDOWS:
        os.chmod(path, 0o600)
        log.warning("DPAPI unavailable on this platform; secret %r stored with "
                    "file permissions only (containerize accordingly, D10)", name)


def get_secret(name: str) -> str | None:
    path = _secrets_dir() / f"{name}.bin"
    if not path.exists():
        return None
    blob = path.read_bytes()
    raw = _dpapi_unprotect(blob) if _IS_WINDOWS else blob
    return raw.decode("utf-8")


def delete_secret(name: str) -> None:
    (_secrets_dir() / f"{name}.bin").unlink(missing_ok=True)


def get_or_create_key(name: str, nbytes: int = 32) -> str:
    """Stable random key (hex) — e.g. the at-rest DB encryption key (D4)."""
    existing = get_secret(name)
    if existing:
        return existing
    key = _secrets.token_hex(nbytes)
    set_secret(name, key)
    return key
