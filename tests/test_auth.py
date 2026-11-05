from __future__ import annotations

import sqlite3

import pytest

from backend.db import Database
from backend.services.auth import SessionStore, UserError, UserRepository
from backend.services.auth.rate_limit import FailureRateLimiter

from .conftest import ADMIN_PASSWORD, ADMIN_USER, login


def test_login_success_sets_httponly_cookie(client):
    response = client.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["user"]["username"] == ADMIN_USER
    assert body["csrf_token"]
    assert ADMIN_PASSWORD not in response.text

    cookie = response.headers["set-cookie"]
    assert "asm_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie or "SameSite=Strict" in cookie

    session = client.get("/api/auth/session").json()
    assert session["authenticated"] is True
    assert session["csrf_token"] == body["csrf_token"]


def test_login_wrong_password(client):
    response = client.post("/api/auth/login", json={"username": ADMIN_USER, "password": "falsch-falsch-falsch"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    assert client.get("/api/auth/session").json()["authenticated"] is False


def test_login_unknown_user_same_error(client):
    response = client.post("/api/auth/login", json={"username": "gibtsnicht", "password": "irgendwas-123"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_login_rate_limit(client):
    for _ in range(3):  # login_max_attempts=3 in der Testkonfiguration
        assert client.post("/api/auth/login", json={"username": ADMIN_USER, "password": "falsch"}).status_code == 401
    blocked = client.post("/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0


def test_validation_error_does_not_echo_input(client):
    secret = "x" * 2000  # länger als erlaubt
    response = client.post("/api/auth/login", json={"username": ADMIN_USER, "password": secret})
    assert response.status_code == 422
    assert secret not in response.text


def test_logout_requires_csrf_and_invalidates_session(client):
    csrf = login(client)
    assert client.post("/api/auth/logout").status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": "falsch"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/auth/session").json()["authenticated"] is False
    assert client.get("/api/databases").status_code == 401


def test_cross_origin_post_rejected(client):
    response = client.post(
        "/api/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_untrusted_host_rejected(client):
    assert client.get("/api/health", headers={"Host": "attacker.example"}).status_code == 400


def test_security_headers(client):
    response = client.get("/api/health")
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_docs_disabled_in_production(client):
    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 404


def test_password_stored_as_argon2id(settings, client):
    with sqlite3.connect(settings.users_db_path) as conn:
        (stored,) = conn.execute("SELECT password_hash FROM users WHERE username = ?", (ADMIN_USER,)).fetchone()
    assert stored.startswith("$argon2id$")
    assert ADMIN_PASSWORD not in stored


def test_password_policy(tmp_path):
    db = Database(tmp_path / "u.sqlite3")
    db.init_schema()
    repo = UserRepository(db)
    with pytest.raises(UserError):
        repo.create_user("kurz", "abc")
    with pytest.raises(UserError):
        repo.create_user("admin2", "admin2-Passwort-123")  # enthält Benutzernamen
    repo.create_user("admin3", "Gutes-Passwort-123")
    with pytest.raises(UserError):
        repo.create_user("ADMIN3", "Gutes-Passwort-456")  # Benutzernamen sind case-insensitiv eindeutig


def test_session_idle_expiry(tmp_path):
    db = Database(tmp_path / "u.sqlite3")
    db.init_schema()
    user = UserRepository(db).create_user("operator", "Gutes-Passwort-123")
    now = [1000.0]
    ended: list[str] = []
    store = SessionStore(db, idle_seconds=60, absolute_seconds=3600, on_session_end=ended.append, clock=lambda: now[0])
    token, session = store.create(user)
    now[0] += 30
    assert store.get(token) is not None  # verlängert bis 1090
    now[0] += 61
    assert store.get(token) is None
    assert ended == [session.session_id]


def test_rate_limiter_lockout_expires():
    now = [0.0]
    limiter = FailureRateLimiter(2, window_seconds=60, lockout_seconds=30, clock=lambda: now[0])
    limiter.register_failure("k")
    assert limiter.retry_after("k") == 0
    limiter.register_failure("k")
    assert limiter.retry_after("k") == 30
    now[0] = 31
    assert limiter.retry_after("k") == 0
