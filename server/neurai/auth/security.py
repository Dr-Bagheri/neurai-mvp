"""Password hashing (stdlib scrypt — no external deps, works air-gapped)."""
from __future__ import annotations

import hashlib
import hmac
import secrets

_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=32,
        )
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, TypeError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)
