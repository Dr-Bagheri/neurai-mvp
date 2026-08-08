"""D4/D8 hardening: password hashing, login lockout, crash-safe recording
recovery, secret store, confidential-meeting exclusions."""
import anyio
import numpy as np

from conftest import signup


def test_password_hash_roundtrip(app_env):
    from neurai.auth.security import hash_password, verify_password

    h = hash_password("رمز عبور امن ۱۲۳")
    assert verify_password("رمز عبور امن ۱۲۳", h)
    assert not verify_password("wrong", h)
    # argon2 is installed in the base deps → production hashes are argon2id
    assert h.startswith("$argon2")


def test_scrypt_hashes_still_verify(app_env):
    from neurai.auth.security import _scrypt_hash, verify_password

    h = _scrypt_hash("legacy-pass")
    assert h.startswith("scrypt$")
    assert verify_password("legacy-pass", h)
    assert not verify_password("nope", h)


def test_login_lockout_backoff(client):
    signup(client, "admin")
    client.cookies.clear()
    for _ in range(5):
        r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-pass"})
    assert r.status_code == 401
    # 6th attempt hits the lockout — even with the right password
    r = client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0


def test_secret_store_roundtrip(app_env):
    from neurai.security import delete_secret, get_secret, set_secret

    assert get_secret("openrouter_key") is None
    set_secret("openrouter_key", "sk-or-test-123")
    assert get_secret("openrouter_key") == "sk-or-test-123"
    delete_secret("openrouter_key")
    assert get_secret("openrouter_key") is None


def test_crash_recovery_finalizes_orphaned_pcm(client):
    """A .pcm left by a crash becomes a playable WAV + queued quality pass."""
    from neurai.audio.session import recover_orphaned_recordings
    from neurai.config import get_config
    from neurai.db import get_db

    signup(client, "admin")
    meeting_id = client.post("/api/meetings", json={"title": "جلسه قطع برق"}).json()["id"]
    get_db().execute("UPDATE meetings SET status='live' WHERE id=?", (meeting_id,))

    cfg = get_config()
    pcm = (np.random.default_rng(1).standard_normal(16000 * 2) * 3000).astype(np.int16)
    (cfg.recordings_dir / f"meeting_{meeting_id}.pcm").write_bytes(pcm.tobytes())

    recovered = recover_orphaned_recordings()
    assert recovered == [meeting_id]

    meeting = get_db().query_one("SELECT * FROM meetings WHERE id=?", (meeting_id,))
    assert meeting["status"] == "processing"
    wav = cfg.recordings_dir / f"meeting_{meeting_id}.wav"
    assert wav.exists()
    import wave

    with wave.open(str(wav), "rb") as w:
        assert w.getframerate() == 16000
        assert w.getnframes() == len(pcm)
    job = get_db().query_one("SELECT * FROM jobs WHERE kind='quality_pass' ORDER BY id DESC")
    assert job is not None


def test_confidential_meeting_forced_local_and_unindexed(client):
    signup(client, "admin")
    r = client.post("/api/meetings", json={
        "title": "جلسه محرمانه", "sensitivity": "confidential", "allow_cloud": True,
    }).json()
    assert r["sensitivity"] == "confidential"
    assert r["allow_cloud"] is False  # forced off (D4)

    from neurai.db import get_db
    from neurai.rag.ingest import index_transcript_job

    meeting_id = r["id"]
    db = get_db()
    db.insert(
        "INSERT INTO transcript_segments(meeting_id, pass, start_ms, end_ms, text) "
        "VALUES(?, 'quality', 0, 1000, 'راز بزرگ شرکت')",
        (meeting_id,),
    )
    anyio.run(index_transcript_job, {"meeting_id": meeting_id})
    assert db.query("SELECT * FROM rag_chunks WHERE kind='transcript' AND ref_id=?",
                    (meeting_id,)) == []


def test_true_deletion_removes_everything(client):
    """D4: deleting a meeting removes transcript, audio, embeddings, and
    search-index entries together — not just the DB row."""
    from neurai.config import get_config
    from neurai.db import get_db
    from neurai.rag import index_text, search_chunks

    signup(client, "admin")
    meeting_id = client.post("/api/meetings", json={"title": "برای حذف"}).json()["id"]
    db = get_db()
    admin_id = db.query_one("SELECT id FROM users WHERE username='admin'")["id"]

    db.insert(
        "INSERT INTO transcript_segments(meeting_id, pass, start_ms, end_ms, text) "
        "VALUES(?, 'quality', 0, 1000, 'محتوای حساس جلسه')",
        (meeting_id,),
    )
    anyio.run(index_text, admin_id, "transcript", meeting_id, "محتوای حساس جلسه")
    cfg = get_config()
    wav = cfg.recordings_dir / f"meeting_{meeting_id}.wav"
    wav.write_bytes(b"RIFF....fakewav")
    db.execute("UPDATE meetings SET audio_path=? WHERE id=?", (str(wav), meeting_id))
    client.post(f"/api/meetings/{meeting_id}/bookmarks", json={"t_ms": 10})

    assert client.delete(f"/api/meetings/{meeting_id}").json() == {"ok": True}

    assert client.get(f"/api/meetings/{meeting_id}").status_code == 404
    assert not wav.exists()
    assert db.query("SELECT * FROM transcript_segments WHERE meeting_id=?", (meeting_id,)) == []
    assert db.query("SELECT * FROM bookmarks WHERE meeting_id=?", (meeting_id,)) == []
    assert db.query("SELECT * FROM rag_chunks WHERE kind='transcript' AND ref_id=?", (meeting_id,)) == []
    hits = anyio.run(search_chunks, admin_id, "محتوای حساس")
    assert hits == []


def test_migrations_are_versioned(app_env):
    from neurai.db import get_db

    db = get_db()
    version = db.query_one("SELECT value FROM schema_meta WHERE key='version'")
    assert int(version["value"]) >= 2
    # migration 002 applied: the sensitivity column exists
    cols = [r["name"] for r in db.query("PRAGMA table_info(meetings)")]
    assert "sensitivity" in cols
