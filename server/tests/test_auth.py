from conftest import as_user, signup


def test_setup_login_me_logout(client):
    assert client.get("/api/auth/status").json() == {"needs_setup": True}

    token = signup(client, "admin")
    assert token

    me = client.get("/api/auth/me").json()
    assert me["username"] == "admin"
    assert me["is_admin"] is True

    # setup only works once
    r = client.post("/api/auth/setup", json={"username": "second", "password": "secret123"})
    assert r.status_code == 409

    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401

    r = client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    assert r.status_code == 200

    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrongpass"})
    assert r.status_code == 401


def test_non_admin_cannot_create_users(client):
    signup(client, "admin")
    user_token = signup(client, "user1")
    as_user(client, user_token)
    r = client.post("/api/auth/users", json={"username": "evil", "password": "secret123"})
    assert r.status_code == 403


def test_unauthenticated_rejected(client):
    assert client.get("/api/meetings").status_code == 401
    assert client.get("/api/admin/settings").status_code == 401
