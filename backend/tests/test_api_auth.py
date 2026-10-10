"""API tests for authentication, health and the WebSocket handshake."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from tests.conftest import ADMIN

PROTECTED = [
    ("get", "/api/projects"),
    ("get", "/api/settings"),
    ("get", "/api/tasks"),
    ("get", "/api/auth/me"),
]


def test_health_is_public_and_hides_secrets(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["workspaces_dir"] is True
    assert body["coding_agent"] == "mock"
    # No credential-shaped content leaks.
    assert "key" not in response.text.lower()
    assert "password" not in response.text.lower()


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_protected_endpoints_require_auth(client, method, path):
    assert getattr(client, method)(path).status_code == 401


def test_status_before_setup(client):
    body = client.get("/api/auth/status").json()
    assert body == {"initialized": False, "authenticated": False, "username": None}


def test_setup_then_status_and_me(client):
    response = client.post("/api/auth/setup", json=ADMIN)
    assert response.status_code == 201
    assert "solo_session" in response.cookies

    status = client.get("/api/auth/status").json()
    assert status["initialized"] is True
    assert status["authenticated"] is True
    assert status["username"] == "admin"
    assert client.get("/api/auth/me").json()["username"] == "admin"


def test_setup_is_one_shot(client):
    assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
    second = client.post(
        "/api/auth/setup", json={"username": "other", "password": "another-pass"}
    )
    assert second.status_code == 409


def test_setup_rejects_short_password(client):
    response = client.post(
        "/api/auth/setup", json={"username": "admin", "password": "short"}
    )
    assert response.status_code == 422


def test_logout_invalidates_session(authed):
    assert authed.get("/api/projects").status_code == 200
    assert authed.post("/api/auth/logout").status_code == 200
    # Cookie is cleared, so protected routes reject again.
    assert authed.get("/api/projects").status_code == 401


def test_session_cookie_is_not_secure_over_plain_http(client):
    """Browsers reject Secure cookies over plain http, which would break sign-in
    on a local install. Auto-detection keeps HTTP usable while still flagging
    the cookie when the request arrives over HTTPS."""
    response = client.post("/api/auth/setup", json=ADMIN)
    assert response.status_code == 201
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" not in cookie


def test_session_cookie_is_secure_when_the_scheme_is_https(settings_factory):
    with TestClient(
        create_app(settings_factory()), base_url="https://testserver"
    ) as https_client:
        response = https_client.post("/api/auth/setup", json=ADMIN)
        assert response.status_code == 201
        assert "Secure" in response.headers["set-cookie"]


def test_session_cookie_secure_can_be_forced(settings_factory):
    settings = settings_factory(session_cookie_secure=True)
    with TestClient(create_app(settings)) as forced:
        response = forced.post("/api/auth/setup", json=ADMIN)
        assert "Secure" in response.headers["set-cookie"]


def test_login_flow(authed):
    authed.post("/api/auth/logout")
    bad = authed.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong-password"}
    )
    assert bad.status_code == 401
    good = authed.post("/api/auth/login", json=ADMIN)
    assert good.status_code == 200
    assert authed.get("/api/projects").status_code == 200


def test_cross_origin_state_changing_request_is_rejected(authed):
    response = authed.post(
        "/api/projects",
        json={"name": "evil"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_same_origin_is_allowed(authed):
    response = authed.post(
        "/api/projects",
        json={"name": "ok"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 201


def test_websocket_requires_authentication(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws"):
            pass


def test_websocket_ready_message_when_authenticated(authed):
    with authed.websocket_connect("/api/ws") as websocket:
        message = websocket.receive_json()
        assert message["channel"] == "ready"
        assert message["payload"]["user"] == "admin"
