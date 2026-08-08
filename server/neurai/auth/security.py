"""Password hashing (D8): argon2id via argon2-cffi when installed (the
production default — it's in the base dependencies), with a stdlib scrypt
fallback so a stripped-down environment still boots. Hashes are self-tagged,
so both formats verify regardless of which library is present later."""
from __future__ import annotations

import hashlib
import hmac
import secrets

_N, _R, _P = 2**14, 8, 1

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

    _argon2: PasswordHasher | None = PasswordHasher()
except ImportError:  # pragma: no cover
    _argon2 = None


def _scrypt_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def hash_password(password: str) -> str:
    if _argon2 is not None:
        return _argon2.hash(password)  # "$argon2id$..."
    return _scrypt_hash(password)


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("$argon2"):
        if _argon2 is None:
            return False
        try:
            return _argon2.verify(stored, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
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


# -- login rate limiting with lockout backoff (D8) --------------------------------

import threading
import time as _time


class LoginLimiter:
    """Per-username failure tracking: after `threshold` consecutive failures,
    lock out with exponential backoff (base_lock_s * 2^(extra failures))."""

    def __init__(self, threshold: int = 5, base_lock_s: float = 30.0, max_lock_s: float = 3600.0):
        self._failures: dict[str, tuple[int, float]] = {}  # username -> (count, locked_until)
        self._lock = threading.Lock()
        self.threshold = threshold
        self.base_lock_s = base_lock_s
        self.max_lock_s = max_lock_s

    def retry_after(self, username: str) -> int:
        """Seconds until this username may try again (0 = allowed)."""
        with self._lock:
            entry = self._failures.get(username)
            if not entry:
                return 0
            _, locked_until = entry
            remaining = locked_until - _time.monotonic()
            return max(0, int(remaining) + 1) if remaining > 0 else 0

    def record_failure(self, username: str) -> None:
        with self._lock:
            count = self._failures.get(username, (0, 0.0))[0] + 1
            locked_until = 0.0
            if count >= self.threshold:
                lock_s = min(self.base_lock_s * (2 ** (count - self.threshold)), self.max_lock_s)
                locked_until = _time.monotonic() + lock_s
            self._failures[username] = (count, locked_until)

    def record_success(self, username: str) -> None:
        with self._lock:
            self._failures.pop(username, None)


login_limiter = LoginLimiter()
