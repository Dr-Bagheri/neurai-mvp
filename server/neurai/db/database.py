"""SQLite access layer.

Plain sqlite3 with WAL — no ORM. FastAPI routes that touch the DB are written
as sync `def` endpoints, so Starlette runs them on the threadpool; sqlite3
handles cross-thread use here because every call goes through a single
serialized connection guarded by a lock. A small team's write load is well
within what WAL-mode SQLite handles (D4).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

_SCHEMA = Path(__file__).with_name("schema.sql")


class Database:
    def __init__(self, path: str | Path):
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self.migrate()

    def migrate(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
            self._conn.execute(
                "INSERT OR IGNORE INTO schema_meta(key, value) VALUES('version', '1')"
            )

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

    # -- settings (runtime-mutable config) -----------------------------------

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
