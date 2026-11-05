from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app

TOKEN = "test-setup-token-1234567890"


@pytest.fixture
def fresh_client(settings):
    settings.setup_token = TOKEN
    with TestClient(create_app(settings)) as c:
        yield c


def _setup(client, token=TOKEN, username="admin", password="Sehr-Sicheres-Passwort-42"):
    return client.post("/api/setup", json={"setup_token": token, "username": username, "password": password})


def test_setup_required_without_users(fresh_client):
    assert fresh_client.get("/api/setup/status").json()["setup_required"] is True


def test_setup_creates_admin_and_logs_in(fresh_client):
    response = _setup(fresh_client)
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "admin"
    assert fresh_client.get("/api/auth/session").json()["authenticated"] is True
    assert fresh_client.get("/api/setup/status").json()["setup_required"] is False
    # nur einmal möglich
    assert _setup(fresh_client, username="zweiter").status_code == 409


def test_setup_rejects_wrong_token(fresh_client):
    response = _setup(fresh_client, token="falscher-schluessel")
    assert response.status_code == 403
    assert fresh_client.get("/api/setup/status").json()["setup_required"] is True


def test_setup_enforces_password_policy(fresh_client):
    response = _setup(fresh_client, password="kurz")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_user_input"
    assert "kurz" not in response.text


def test_setup_disabled_when_users_exist(client):
    # Der Standard-Client legt bereits einen Benutzer an.
    assert client.get("/api/setup/status").json()["setup_required"] is False
    assert _setup(client, token="egal").status_code == 409
