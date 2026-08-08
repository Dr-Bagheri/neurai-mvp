"""SQLite access layer.

Plain sqlite3 with WAL — no ORM. FastAPI routes that touch the DB are written
as sync `def` endpoints, so Starlette runs them on the threadpool; sqlite3
handles cross-thread use here because every call goes through a single
serialized connection guarded by a lock. A small team's write load is well
within what WAL-mode SQLite handles (D4).

Schema changes are versioned migrations from 001 (D4): numbered .sql files in
`migrations/`, applied in order, version tracked in schema_meta. On-premise
means we can never fix a customer's database by hand.

Encryption at rest (D4/D8): when the `sqlcipher3` driver is installed the
database is opened through SQLCipher with a key held in DPAPI (see
neurai/security). Without the driver the server still runs (dev/CI) but logs
that at-rest encryption is OFF — the check is at open time, day one, so real
deployments can't accumulate plaintext data unnoticed.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

log = logging.getLogger("neurai.db")

_MIGRATIONS_DIR = Path(__file__).with_name("migrations")

AT_REST_KEY_NAME = "db_at_rest_key"


def _connect(path: str | Path) -> tuple[Any, Any, bool]:
    """Returns (connection, row_type, encrypted). SQLCipher is a base
    dependency (D4: encryption default-on); the plain-sqlite3 fallback exists
    only for stripped environments and warns loudly."""
    try:
        import sqlcipher3

        from neurai.security import get_or_create_key

        conn = sqlcipher3.connect(str(path), check_same_thread=False)
        conn.execute(f"PRAGMA key = \"x'{get_or_create_key(AT_REST_KEY_NAME)}'\"")
        return conn, sqlcipher3.Row, True
    except ImportError:
        conn = sqlite3.connect(str(path), check_same_thread=False)
        return conn, sqlite3.Row, False


class Database:
    def __init__(self, path: str | Path):
        self._lock = threading.RLock()
        self._conn, row_type, self.encrypted = _connect(path)
        if not self.encrypted:
            log.warning(
                "sqlcipher3 not installed — database at-rest encryption is OFF "
                "(acceptable for dev/CI only; see D4/D8)"
            )
        self._conn.row_factory = row_type
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except Exception as e:
            if self.encrypted and "not a database" in str(e).lower():
                raise RuntimeError(
                    f"{path} exists but cannot be decrypted. Either it predates "
                    "at-rest encryption (a plaintext dev database — delete it or "
                    "move it aside) or the key in the secret store does not match "
                    "this database. Refusing to touch it. (D4)"
                ) from e
            raise
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self.migrate()

    # -- migrations ----------------------------------------------------------

    def _schema_version(self) -> int:
        row = self._conn.execute(
            "SELECT value FROM schema_meta WHERE key='version'"
        ).fetchone()
        return int(row["value"]) if row else 0

    def migrate(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            current = self._schema_version()
            for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
                m = re.match(r"^(\d+)_", path.name)
                if not m:
                    continue
                number = int(m.group(1))
                if number <= current:
                    continue
                log.info("applying migration %s", path.name)
                self._conn.executescript(path.read_text(encoding="utf-8"))
                self._conn.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(number),),
                )
                current = number

    # -- primitives ---------------------------------------------------------

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock, self._conn:
            return self._conn.execute(sql, tuple(params))

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchone()

    def insert(self, sql: str, params: Iterable[Any] = ()) -> int:
        with self._lock, self._conn:
            cur = self._conn.execute(sql, tuple(params))
            return int(cur.lastrowid)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def backup_to(self, dest_path: str | Path) -> None:
        """Consistent snapshot via the SQLite backup API. With SQLCipher the
        destination is written through the same codec/key, so the snapshot is
        as encrypted as the live DB — what gets uploaded is ciphertext whose
        key never leaves this machine (D4 backup, true E2E)."""
        dest_conn, _row, _enc = _connect(dest_path)
        try:
            with self._lock:
                self._conn.backup(dest_conn)
            dest_conn.commit()
        finally:
            dest_conn.close()

    # -- settings (runtime-mutable, non-secret config) -------------------------

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_json_setting(self, key: str, default: Any = None) -> Any:
        raw = self.get_setting(key)
        return json.loads(raw) if raw is not None else default


_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        from neurai.config import get_config

        cfg = get_config()
        cfg.ensure_dirs()
        _db = Database(cfg.db_path)
    return _db


def set_db(db: Database | None) -> None:
    """Test hook."""
    global _db
    _db = db
