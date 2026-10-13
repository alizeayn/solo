"""Tests for the Orchestrator's provider layer.

The Orchestrator reasons through one of several model providers. Two things are
worth guarding closely:

* **OpenRouter must not regress.** It is the default and the only provider that
  has ever run in production, so every change here is checked against it.
* **OpenCode Go needs a header OpenRouter does not.** It rejects a request that
  carries no `x-opencode-session` with a 400:

      {"type":"error","error":{"type":"MissingSessionID","message":"Request is
       missing x-opencode-session and cannot be routed efficiently."}}

  That is not a degraded response, it is every call failing — and a provider
  wired up without it would look like a broken key.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.openrouter import OpenRouterClient, OpenRouterError, ProviderError
from app.services.orchestrator_providers import (
    DEFAULT_PROVIDER,
    OPENCODE_GO,
    OPENCODE_GO_BASE_URL,
    OPENROUTER,
    PROVIDERS,
    build_headers,
    get_provider,
    opencode_go_headers,
    provider_catalog,
)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def test_both_providers_are_registered():
    assert set(PROVIDERS) == {OPENROUTER, OPENCODE_GO}
    assert get_provider(OPENROUTER).label == "OpenRouter"
    assert get_provider(OPENCODE_GO).label == "OpenCode Go"


def test_an_unknown_provider_falls_back_rather_than_raising():
    """A saved setting can name a provider a later release removed.

    Raising here would leave the Orchestrator unusable with no way to reach the
    UI that fixes it.
    """
    assert get_provider("some-removed-provider").id == DEFAULT_PROVIDER
    assert get_provider(None).id == DEFAULT_PROVIDER
    assert get_provider("").id == DEFAULT_PROVIDER
    # Case and whitespace from a hand-edited setting must not defeat it.
    assert get_provider("  OpenCode_Go  ").id == OPENCODE_GO


def test_each_provider_points_at_its_own_settings():
    """Sharing a key or model setting would silently cross-configure them."""
    keys = {spec.key_setting for spec in PROVIDERS.values()}
    models = {spec.model_setting for spec in PROVIDERS.values()}
    assert len(keys) == len(PROVIDERS)
    assert len(models) == len(PROVIDERS)


def test_the_catalogue_describes_each_provider_for_the_ui():
    catalog = {entry["id"]: entry for entry in provider_catalog()}
    assert catalog[OPENROUTER]["requires_session_header"] is False
    assert catalog[OPENCODE_GO]["requires_session_header"] is True
    assert catalog[OPENCODE_GO]["base_url"] == OPENCODE_GO_BASE_URL
    assert catalog[OPENCODE_GO]["key_url"].startswith("https://")
    assert catalog[OPENCODE_GO]["documentation"].startswith("https://")


# --------------------------------------------------------------------------- #
# Headers — the part that decides whether OpenCode Go works at all
# --------------------------------------------------------------------------- #
def test_opencode_go_sends_the_session_header_its_api_requires():
    headers = opencode_go_headers("abc123")
    assert headers["x-opencode-session"] == "abc123"
    # The API asks clients to identify themselves rather than look like a
    # generic HTTP library.
    assert headers["User-Agent"].startswith("solo/")


def test_openrouter_needs_no_extra_headers():
    assert build_headers(get_provider(OPENROUTER), "abc123") == {}


def test_the_client_actually_sends_the_provider_headers():
    """The registry building headers is no use if the transport drops them."""
    client = OpenRouterClient(
        "test-key",
        base_url=OPENCODE_GO_BASE_URL,
        extra_headers=opencode_go_headers("sess-42"),
    )
    # What the transport will put on the wire.
    assert client._headers["x-opencode-session"] == "sess-42"
    assert client._headers["Authorization"] == "Bearer test-key"
    assert client._base_url == OPENCODE_GO_BASE_URL


def test_openrouter_keeps_its_attribution_headers():
    """OpenRouter uses these on its dashboard; the abstraction must not drop them."""
    client = OpenRouterClient("test-key")
    assert client._headers["HTTP-Referer"] == "http://localhost"
    assert client._headers["X-Title"] == "Solo"
    assert "x-opencode-session" not in client._headers


# --------------------------------------------------------------------------- #
# Error type
# --------------------------------------------------------------------------- #
def test_the_error_type_is_shared_between_providers():
    """Callers must not branch on which provider is configured."""
    assert ProviderError is OpenRouterError
    with pytest.raises(ProviderError):
        raise OpenRouterError("OpenCode Go rejected the key.", status=401)


# --------------------------------------------------------------------------- #
# Provider-aware wiring, through the real container
# --------------------------------------------------------------------------- #
async def test_the_brain_uses_opencode_go_when_it_is_selected(settings_factory):
    from app.container import Container
    from app.schemas import SettingsUpdate

    settings = settings_factory()
    container = await Container.create(settings)
    service = container.settings_service

    # Default is unchanged: OpenRouter.
    assert (await container.brain.active_provider()).id == OPENROUTER

    await service.update(
        SettingsUpdate(orchestrator_provider=OPENCODE_GO, opencode_go_api_key="go-key")
    )

    spec = await container.brain.active_provider()
    assert spec.id == OPENCODE_GO

    pair = await container.brain.credentials()
    assert pair is not None, "a saved OpenCode Go key must produce a client"
    client, model = pair
    assert model is None, "a model is not needed to list models"
    # The client is pointed at Go, not at OpenRouter's endpoint.
    assert client._base_url == OPENCODE_GO_BASE_URL
    assert client._headers["x-opencode-session"] == container.brain.session_id

    configuration = await container.brain.configuration()
    assert configuration["provider"] == OPENCODE_GO
    assert configuration["provider_label"] == "OpenCode Go"
    assert configuration["base_url"] == OPENCODE_GO_BASE_URL


async def test_switching_provider_does_not_disturb_the_other(settings_factory):
    """Adding a provider must not remove or break the first one."""
    from app.container import Container
    from app.schemas import SettingsUpdate

    container = await Container.create(settings_factory())
    service = container.settings_service
    await service.update(
        SettingsUpdate(
            openrouter_api_key="or-key", openrouter_model="or/model",
            opencode_go_api_key="go-key", opencode_go_model="kimi-k3",
            orchestrator_provider=OPENCODE_GO,
        )
    )

    # Go is active and reports Go's model.
    client, model = await container.brain.credentials()
    assert client._base_url == OPENCODE_GO_BASE_URL
    assert model == "kimi-k3"

    # Switching back restores OpenRouter exactly.
    await service.update(SettingsUpdate(orchestrator_provider=OPENROUTER))
    client, model = await container.brain.credentials()
    assert client._base_url == "https://openrouter.ai/api/v1"
    assert model == "or/model"
    # And OpenRouter's client carries no Go session header.
    assert "x-opencode-session" not in client._headers


async def test_the_opencode_go_key_is_encrypted_at_rest(settings_factory):
    """Which provider is active must not change how well a key is protected."""
    import sqlite3

    from app.container import Container
    from app.schemas import SettingsUpdate

    settings = settings_factory()
    container = await Container.create(settings)
    await container.settings_service.update(SettingsUpdate(opencode_go_api_key="go-secret"))

    connection = sqlite3.connect(settings.db_path)
    try:
        row = connection.execute(
            "SELECT value, is_secret FROM app_settings WHERE key = 'opencode_go_api_key'"
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    stored, is_secret = row
    assert is_secret == 1
    assert "go-secret" not in stored, "the key was stored in the clear"
