from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ["NEURAI_ASR"] = "fake"

SESSION_COOKIE = "neurai_session"


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    """Fresh config + DB + singletons per test."""
    monkeypatch.setenv("NEURAI_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NEURAI_ASR", "fake")

    import neurai.audio.asr as asr_mod
    import neurai.audio.session as session_mod
    import neurai.config as config_mod
    import neurai.db.database as db_mod
    import neurai.harness.connectivity as conn_mod
    import neurai.harness.harness as harness_mod
    import neurai.jobs.queue as queue_mod
    import neurai.rag.embeddings as emb_mod
    import neurai.skills.runtime as skills_mod

    config_mod._config = None
    db_mod.set_db(None)
    harness_mod.set_harness(None)
    skills_mod.set_skill_runtime(None)
    emb_mod.set_embeddings(None)
    asr_mod.set_engines(None, None)
    session_mod._manager = None
    queue_mod._queue = None
    conn_mod.reset_probe_cache()
    yield
    db = db_mod._db
    if db is not None:
        db.close()
    db_mod.set_db(None)


@pytest.fixture()
def client(app_env):
    from fastapi.testclient import TestClient

    from neurai.main import create_app

    with TestClient(create_app()) as c:
        yield c


def signup(client, username: str, password: str = "secret123") -> str:
    """Create a user (setup for the first, admin-create after) and return a
    session token. The very first user becomes admin. NOTE: the admin-create
    path needs the current session to be an admin's."""
    status = client.get("/api/auth/status").json()
    if status["needs_setup"]:
        r = client.post("/api/auth/setup", json={"username": username, "password": password})
        assert r.status_code == 200, r.text
        return client.cookies.get(SESSION_COOKIE)
    r = client.post("/api/auth/users", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    client.cookies.clear()  # drop the admin session before logging in as the new user
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return client.cookies.get(SESSION_COOKIE)


def as_user(client, token: str) -> None:
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, token)
