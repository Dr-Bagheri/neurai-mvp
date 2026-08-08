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


def test_audio_encryption_roundtrip_and_resume(app_env):
    """Recordings are AES-CTR at rest: ciphertext on disk, lossless decrypt,
    and append-resume continues the keystream correctly (dropped-WS case)."""
    from neurai.config import get_config
    from neurai.security.audiocrypt import EncryptedAudioWriter, pcm_size, read_pcm, read_pcm_range

    get_config().ensure_dirs()
    path = get_config().recordings_dir / "meeting_99.neura"
    part1 = (np.random.default_rng(1).standard_normal(16000) * 3000).astype(np.int16).tobytes()
    part2 = (np.random.default_rng(2).standard_normal(7001) * 3000).astype(np.int16).tobytes()

    w = EncryptedAudioWriter(path)
    w.write(part1)
    w.close()
    w = EncryptedAudioWriter(path)  # resume (reconnect after crash/drop)
    w.write(part2)
    w.close()

    plain = part1 + part2
    assert pcm_size(path) == len(plain)
    assert read_pcm(path) == plain
    # random access from an odd offset (Range playback path)
    assert read_pcm_range(path, 12345, 999) == plain[12345:12345 + 999]
    # the file on disk is not plaintext
    on_disk = path.read_bytes()
    assert plain[:64] not in on_disk


def test_audio_nonce_uniqueness_per_file(app_env, monkeypatch):
    """D11 hard requirement: CTR nonce reuse across files under one master
    key is a two-time pad. Every file must get its own 16-byte CSPRNG nonce."""
    from neurai.config import get_config
    from neurai.security import audiocrypt
    from neurai.security.audiocrypt import HEADER_LEN, MAGIC, EncryptedAudioWriter

    get_config().ensure_dirs()
    rec_dir = get_config().recordings_dir
    plain = bytes(range(256)) * 64  # identical plaintext in every file

    nonces, ciphertexts = set(), set()
    for i in range(20):
        path = rec_dir / f"nonce_test_{i}.neura"
        w = EncryptedAudioWriter(path)
        w.write(plain)
        w.close()
        data = path.read_bytes()
        assert data[:len(MAGIC)] == MAGIC
        nonce = data[len(MAGIC):HEADER_LEN]
        assert len(nonce) == 16                    # 128-bit, as D11 specifies
        nonces.add(nonce)
        ciphertexts.add(data[HEADER_LEN:])
    assert len(nonces) == 20                       # unique per file
    assert len(ciphertexts) == 20                  # same plaintext+key ≠ same ciphertext

    # nonce source is the stdlib CSPRNG (secrets.token_bytes), not derived/counter
    sentinel = bytes(range(16))
    monkeypatch.setattr(audiocrypt.secrets, "token_bytes", lambda n: sentinel[:n])
    path = rec_dir / "nonce_source_probe.neura"
    EncryptedAudioWriter(path).close()
    assert path.read_bytes()[len(MAGIC):HEADER_LEN] == sentinel

    # resume never restarts the keystream: appending to an existing file keeps
    # its nonce and continues at the ciphertext-length offset
    w = EncryptedAudioWriter(rec_dir / "nonce_test_0.neura")
    w.write(plain)
    w.close()
    data = (rec_dir / "nonce_test_0.neura").read_bytes()
    first, second = data[HEADER_LEN:HEADER_LEN + len(plain)], data[HEADER_LEN + len(plain):]
    assert first != second                         # same plaintext, disjoint keystream


def test_crash_recovery_resumes_live_meeting(client):
    """A meeting still 'live' at startup (crash) is flipped to processing and
    its quality pass queued — the sealed recording needs no finalization."""
    from neurai.audio.session import recover_crashed_meetings
    from neurai.config import get_config
    from neurai.db import get_db
    from neurai.security.audiocrypt import EncryptedAudioWriter

    signup(client, "admin")
    meeting_id = client.post("/api/meetings", json={"title": "جلسه قطع برق"}).json()["id"]
    cfg = get_config()
    path = cfg.recordings_dir / f"meeting_{meeting_id}.neura"
    w = EncryptedAudioWriter(path)
    w.write((np.random.default_rng(1).standard_normal(16000 * 2) * 3000).astype(np.int16).tobytes())
    w.close()
    get_db().execute("UPDATE meetings SET status='live', audio_path=? WHERE id=?",
                     (str(path), meeting_id))

    assert recover_crashed_meetings() == [meeting_id]
    meeting = get_db().query_one("SELECT * FROM meetings WHERE id=?", (meeting_id,))
    assert meeting["status"] == "processing"
    job = get_db().query_one("SELECT * FROM jobs WHERE kind='quality_pass' ORDER BY id DESC")
    assert job is not None


def test_database_is_encrypted_at_rest(app_env):
    """With the bundled SQLCipher driver, the DB file is unreadable as plain
    SQLite (D4: default-on, day one)."""
    import sqlite3

    import pytest

    from neurai.config import get_config
    from neurai.db import get_db

    db = get_db()
    assert db.encrypted is True
    db.execute("INSERT INTO settings(key, value) VALUES('probe', 'x')")
    plain = sqlite3.connect(str(get_config().db_path))
    with pytest.raises(sqlite3.DatabaseError):
        plain.execute("SELECT * FROM settings").fetchall()
    plain.close()


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
    audio = cfg.recordings_dir / f"meeting_{meeting_id}.neura"
    audio.write_bytes(b"NRAI1\x00" + b"\x00" * 16 + b"ciphertext")
    db.execute("UPDATE meetings SET audio_path=? WHERE id=?", (str(audio), meeting_id))
    client.post(f"/api/meetings/{meeting_id}/bookmarks", json={"t_ms": 10})

    assert client.delete(f"/api/meetings/{meeting_id}").json() == {"ok": True}

    assert client.get(f"/api/meetings/{meeting_id}").status_code == 404
    assert not audio.exists()
    assert db.query("SELECT * FROM transcript_segments WHERE meeting_id=?", (meeting_id,)) == []
    assert db.query("SELECT * FROM bookmarks WHERE meeting_id=?", (meeting_id,)) == []
    assert db.query("SELECT * FROM rag_chunks WHERE kind='transcript' AND ref_id=?", (meeting_id,)) == []
    hits = anyio.run(search_chunks, admin_id, "محتوای حساس")
    assert hits == []


def test_password_change_revokes_all_sessions(client):
    """D8: password change invalidates every other session; the changing
    client gets a fresh one; the old password stops working."""
    from conftest import SESSION_COOKIE, as_user

    signup(client, "admin")
    token_a = client.cookies.get(SESSION_COOKIE)
    client.cookies.clear()
    client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    token_b = client.cookies.get(SESSION_COOKIE)
    assert token_a != token_b

    # change the password from session B
    r = client.post("/api/auth/change-password",
                    json={"current_password": "secret123", "new_password": "newpass456"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 200  # B re-issued, still signed in

    as_user(client, token_a)                               # A is revoked
    assert client.get("/api/auth/me").status_code == 401

    client.cookies.clear()
    r = client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    assert r.status_code == 401                            # old password dead
    r = client.post("/api/auth/login", json={"username": "admin", "password": "newpass456"})
    assert r.status_code == 200

    # wrong current password is rejected (and doesn't revoke anything)
    r = client.post("/api/auth/change-password",
                    json={"current_password": "wrong-one", "new_password": "whatever789"})
    assert r.status_code == 403


def test_runtime_strips_cloud_without_manifest_permission(client):
    """D7 rule 3 (enforced part): a skill whose manifest lacks llm:cloud runs
    with ctx.allow_cloud stripped, even when the caller consented."""
    from neurai.skills import get_skill_runtime
    from neurai.skills.runtime import SkillContext, SkillManifest

    signup(client, "admin")
    rt = get_skill_runtime()
    seen = {}

    async def probe(ctx, params):
        seen["allow_cloud"] = ctx.allow_cloud
        return {"ok": True}

    rt.register(SkillManifest(
        "probe_no_cloud", "test probe", {"type": "object", "properties": {}},
        frozenset({"llm:local"})), probe)
    rt.register(SkillManifest(
        "probe_with_cloud", "test probe", {"type": "object", "properties": {}},
        frozenset({"llm:local", "llm:cloud"})), probe)

    ctx = SkillContext(user_id=1, username="admin", allow_cloud=True)
    anyio.run(rt.execute, "probe_no_cloud", {}, ctx)
    assert seen["allow_cloud"] is False
    anyio.run(rt.execute, "probe_with_cloud", {}, ctx)
    assert seen["allow_cloud"] is True


def test_rag_query_normalization(client):
    """D5: an Arabic-typed ي/ك query must find chunks indexed with Persian
    characters — normalization applies to both sides."""
    from neurai.db import get_db
    from neurai.rag import index_text, search_chunks

    signup(client, "admin")
    admin_id = get_db().query_one("SELECT id FROM users WHERE username='admin'")["id"]

    async def scenario():
        await index_text(admin_id, "document", 1, "علی کتاب را آورد")
        return await search_chunks(admin_id, "علي كتاب")  # Arabic yeh + kaf

    hits = anyio.run(scenario)
    assert hits and "علی" in hits[0].text


def test_export_meeting_is_owner_scoped(client):
    """minutes/export reads the meeting WHERE owner_id=? — defense in depth
    beyond the skill-layer check."""
    import pytest

    from conftest import as_user
    from neurai.db import get_db
    from neurai.minutes.export import export_meeting
    from neurai.skills.runtime import SkillContext

    signup(client, "alice")
    meeting_id = client.post("/api/meetings", json={"title": "محرمانه"}).json()["id"]
    signup(client, "bob")
    bob_id = get_db().query_one("SELECT id FROM users WHERE username='bob'")["id"]

    bob_ctx = SkillContext(user_id=bob_id, username="bob", confirmed=True)
    with pytest.raises(RuntimeError):
        anyio.run(export_meeting, meeting_id, bob_ctx, "txt", "plain")


def test_migrations_are_versioned(app_env):
    from neurai.db import get_db

    db = get_db()
    version = db.query_one("SELECT value FROM schema_meta WHERE key='version'")
    assert int(version["value"]) >= 2
    # migration 002 applied: the sensitivity column exists
    cols = [r["name"] for r in db.query("PRAGMA table_info(meetings)")]
    assert "sensitivity" in cols
