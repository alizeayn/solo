"""API tests for settings storage, masking and connection tests."""

from __future__ import annotations

SECRET = "sk-or-v1-1234567890abcdef"


def test_defaults_are_unconfigured(authed):
    body = authed.get("/api/settings").json()
    assert body["openrouter_api_key"] == {"configured": False, "masked": None}
    assert body["elevenlabs_api_key"] == {"configured": False, "masked": None}
    assert body["voice_enabled"] is True
    assert body["progress_speech_enabled"] is True


def test_secret_is_stored_masked_and_never_returned(authed):
    response = authed.put("/api/settings", json={"openrouter_api_key": SECRET})
    assert response.status_code == 200
    assert SECRET not in response.text

    body = authed.get("/api/settings").json()
    assert body["openrouter_api_key"]["configured"] is True
    assert body["openrouter_api_key"]["masked"].endswith("cdef")
    assert SECRET not in authed.get("/api/settings").text


def test_secret_persists_across_requests_and_is_encrypted_at_rest(authed):
    authed.put("/api/settings", json={"openrouter_api_key": SECRET})
    assert authed.get("/api/settings").json()["openrouter_api_key"]["configured"]

    # Raw secret must not appear anywhere in the SQLite file.
    db_path = authed.app.state.container.settings.db_path
    assert SECRET.encode() not in db_path.read_bytes()


def test_plain_settings_roundtrip(authed):
    payload = {
        "openrouter_model": "anthropic/claude-3.5-sonnet",
        "elevenlabs_agent_id": "agent_123",
        "pi_provider": "openrouter",
        "pi_reuse_openrouter_key": True,
        "voice_enabled": False,
    }
    body = authed.put("/api/settings", json=payload).json()
    assert body["openrouter_model"] == payload["openrouter_model"]
    assert body["elevenlabs_agent_id"] == "agent_123"
    assert body["pi_provider"] == "openrouter"
    assert body["pi_reuse_openrouter_key"] is True
    assert body["voice_enabled"] is False


def test_empty_string_clears_secret(authed):
    authed.put("/api/settings", json={"openrouter_api_key": SECRET})
    body = authed.put("/api/settings", json={"openrouter_api_key": ""}).json()
    assert body["openrouter_api_key"]["configured"] is False


def test_delete_secret_endpoint(authed):
    authed.put("/api/settings", json={"elevenlabs_api_key": "sk_abcdef123456"})
    assert authed.get("/api/settings").json()["elevenlabs_api_key"]["configured"]
    body = authed.delete("/api/settings/secret/elevenlabs_api_key").json()
    assert body["elevenlabs_api_key"]["configured"] is False
    assert authed.delete("/api/settings/secret/unknown").status_code == 404


def test_test_openrouter_without_key(authed):
    body = authed.post("/api/settings/test/openrouter").json()
    assert body["ok"] is False
    assert "not configured" in body["message"].lower() or "No OpenRouter" in body["message"]


def test_test_elevenlabs_without_key(authed):
    body = authed.post("/api/settings/test/elevenlabs").json()
    assert body["ok"] is False


def test_test_pi_reports_status(authed):
    response = authed.post("/api/settings/test/pi")
    assert response.status_code == 200
    assert isinstance(response.json()["ok"], bool)


def test_unknown_provider_returns_404(authed):
    assert authed.post("/api/settings/test/nope").status_code == 404


def test_settings_require_auth(client):
    assert client.get("/api/settings").status_code == 401
    assert client.put("/api/settings", json={}).status_code == 401
