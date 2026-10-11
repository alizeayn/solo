"""Regression tests for the Orchestrator's OpenRouter configuration flow.

The reported failure: an OpenRouter API key was saved and validated, yet
**Retrieve models** answered *"The Orchestrator needs an OpenRouter API key"*.

Root cause: `OrchestratorBrain.client()` required a key **and** a model, and the
model-list endpoint used it. Listing models is the step that comes *before*
choosing one, so in the normal first-run state — key saved, no model yet — the
endpoint saw `None` and blamed the missing key.

These tests pin the whole flow: one configuration source, the same source for the
UI and the endpoint, correct persistence, and distinct error messages for the
three genuinely different causes (no key, no model, Orchestrator disabled).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.container import Container
from app.main import create_app
from tests.conftest import ADMIN

KEY = "sk-or-v1-regression-key-0123456789"


class _StubResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _StubHttp:
    """Counts requests so a test can prove the endpoint actually tried."""

    def __init__(self, response: _StubResponse) -> None:
        self._response = response
        self.calls: list[str] = []

    async def __aenter__(self) -> "_StubHttp":
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False

    async def request(self, method: str, url: str, headers=None, json=None):  # noqa: A002
        self.calls.append(url)
        return self._response


MODELS = {
    "data": [
        {"id": "vendor/alpha", "name": "Alpha", "context_length": 200000},
        {"id": "vendor/beta", "name": "Beta", "context_length": 32000},
    ]
}


@pytest.fixture
def client(settings_factory):
    with TestClient(create_app(settings_factory())) as test_client:
        assert test_client.post("/api/auth/setup", json=ADMIN).status_code == 201
        yield test_client


@pytest.fixture
def stub_http(monkeypatch) -> _StubHttp:
    stub = _StubHttp(_StubResponse(200, MODELS))
    monkeypatch.setattr(
        "app.services.openrouter.httpx.AsyncClient", lambda **_kwargs: stub
    )
    return stub


# --------------------------------------------------------------------------- #
# The reported defect
# --------------------------------------------------------------------------- #
def test_model_retrieval_works_with_a_key_and_no_model_yet(client, stub_http):
    """The exact reported scenario: key saved, no model chosen."""
    client.put("/api/settings", json={"openrouter_api_key": KEY})

    status = client.get("/api/orchestrator/status").json()
    assert status["has_key"] is True
    assert status["model"] is None, "no model has been chosen yet"
    assert status["configured"] is False

    # Before the fix this returned 400 "needs an OpenRouter API key".
    response = client.get("/api/orchestrator/models")
    assert response.status_code == 200, response.text
    assert [model["id"] for model in response.json()] == ["vendor/alpha", "vendor/beta"]
    assert stub_http.calls, "the endpoint must actually reach OpenRouter"


def test_key_validation_and_model_retrieval_agree_on_the_same_source(client, stub_http):
    """The Settings UI and the endpoint must read one configuration value."""
    client.put("/api/settings", json={"openrouter_api_key": KEY})

    settings = client.get("/api/settings").json()
    assert settings["openrouter_api_key"]["configured"] is True
    assert KEY not in json.dumps(settings), "the key is never returned"

    # The key test and the model list both succeed from that single value.
    assert client.post("/api/orchestrator/test", params={"deep": False}).json()["ok"] is True
    assert client.get("/api/orchestrator/models").status_code == 200


def test_the_key_survives_a_restart(settings_factory):
    """Persistence: a saved key must still be readable by a new container."""
    settings = settings_factory()
    first = TestClient(create_app(settings))
    with first:
        first.post("/api/auth/setup", json=ADMIN)
        first.put("/api/settings", json={"openrouter_api_key": KEY})

    with TestClient(create_app(settings)) as second:
        assert second.post("/api/auth/login", json=ADMIN).status_code == 200
        assert second.get("/api/orchestrator/status").json()["has_key"] is True
        assert second.get("/api/settings").json()["openrouter_api_key"]["configured"] is True


# --------------------------------------------------------------------------- #
# Distinct, honest errors for the three real causes
# --------------------------------------------------------------------------- #
def test_no_key_reports_a_missing_key(client):
    response = client.get("/api/orchestrator/models")
    assert response.status_code == 400
    assert "No OpenRouter API key is saved" in response.json()["detail"]


def test_a_chosen_model_is_required_for_completions_but_not_for_listing(client, stub_http):
    """`client()` needs both; `credentials()` needs only the key."""
    client.put("/api/settings", json={"openrouter_api_key": KEY})

    # Listing works without a model…
    assert client.get("/api/orchestrator/models").status_code == 200

    container = client.app.state.container

    import asyncio

    async def check() -> tuple[bool, bool]:
        credentials = await container.brain.credentials()
        completions = await container.brain.client()
        return credentials is not None, completions is not None

    has_credentials, has_completions = asyncio.run(check())
    assert has_credentials is True
    assert has_completions is False, "a completion cannot run without a model"


def test_disabled_orchestrator_says_so_rather_than_blaming_the_key(client):
    client.put("/api/settings", json={"orchestrator_enabled": False})
    response = client.get("/api/orchestrator/models")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "disabled" in detail
    assert "No OpenRouter API key" not in detail


# --------------------------------------------------------------------------- #
# The selected model reaches the Orchestrator runtime
# --------------------------------------------------------------------------- #
async def test_the_selected_model_is_the_one_the_runtime_uses(settings_factory):
    """A model chosen in Settings must be what the brain actually calls."""
    container = await Container.create(settings_factory())
    try:
        await container.settings_service.update(
            type(
                "P",
                (),
                {
                    "model_dump": lambda self, **_kw: {
                        "openrouter_api_key": KEY,
                        "openrouter_model": "vendor/chosen",
                    }
                },
            )()
        )
        pair = await container.brain.client()
        assert pair is not None
        _client, model = pair
        assert model == "vendor/chosen", "the runtime must use the selected model"

        # And it is reported as configured, not merely stored.
        status = await container.brain.configuration()
        assert status["configured"] is True
        assert status["model"] == "vendor/chosen"
    finally:
        await container.close()


async def test_completions_fall_back_when_no_model_is_chosen(settings_factory):
    """Without a model the brain must return None, so callers use the rules."""
    container = await Container.create(settings_factory())
    try:
        await container.settings_service.update(
            type(
                "P",
                (),
                {"model_dump": lambda self, **_kw: {"openrouter_api_key": KEY}},
            )()
        )
        assert await container.brain.client() is None
        assert await container.brain.available() is False
        assert await container.brain.credentials() is not None
    finally:
        await container.close()


def test_model_selection_round_trip_through_the_api(client, stub_http):
    client.put("/api/settings", json={"openrouter_api_key": KEY})
    models = client.get("/api/orchestrator/models").json()

    chosen = models[0]["id"]
    assert client.put("/api/orchestrator/config", json={"model": chosen}).status_code == 200

    status = client.get("/api/orchestrator/status").json()
    assert status["model"] == chosen
    assert status["configured"] is True
    assert client.get("/api/settings").json()["openrouter_model"] == chosen
