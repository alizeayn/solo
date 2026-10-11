"""Tests for the ElevenLabs client, the transport, and the voice endpoints.

No network: the client accepts an injected ``httpx.AsyncClient``, so a routed
stub stands in for the service. What matters here:

* the **real** request shape (``xi-api-key``, path, multipart vs JSON), because a
  wrong header or path is exactly the kind of bug a canned response hides;
* errors that **name the real cause** — a missing key is never reported as a
  missing model, and a rejected key is never reported as a network problem;
* the transport keeps the line when synthesis fails. A task must not break
  because a voice was unavailable, and information must never be audio-only.
"""

from __future__ import annotations

import httpx
import pytest

from app.container import Container
from app.schemas import SettingsUpdate
from app.services.elevenlabs import (
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    ElevenLabsClient,
    ElevenLabsError,
    ElevenLabsTransport,
    chunk_text,
)


# --------------------------------------------------------------------------- #
# A routed stub standing in for the service
# --------------------------------------------------------------------------- #
class StubResponse:
    def __init__(self, status_code: int, payload=None, content: bytes = b"") -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class RoutedClient:
    """Routes by (method, path fragment) and records every call."""

    def __init__(self, routes: dict, *, error: Exception | None = None) -> None:
        self._routes = routes
        self._error = error
        self.calls: list[dict] = []

    async def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if self._error:
            raise self._error
        for key, response in self._routes.items():
            if isinstance(key, tuple):
                wanted_method, fragment = key
                if method != wanted_method or fragment not in url:
                    continue
            elif key not in url:
                continue
            if callable(response):
                return response(**kwargs)
            return response
        return StubResponse(404)

    async def aclose(self) -> None:
        pass


MODELS = [
    {
        "model_id": "scribe_v2",
        "name": "Scribe v2",
        "can_do_text_to_speech": False,
        "description": "Speech recognition",
    },
    {
        "model_id": "eleven_flash_v2_5",
        "name": "Eleven Flash v2.5",
        "can_do_text_to_speech": True,
        "maximum_text_length_per_request": 40000,
        "model_rates": {"character_cost_multiplier": 0.5},
        "languages": [{"language_id": "en", "name": "English"}],
    },
    {
        "model_id": "eleven_v4_turbo",
        "name": "Eleven v4 Turbo",
        "can_do_text_to_speech": True,
        "requires_alpha_access": False,
    },
]

VOICES = {
    "voices": [
        {
            "voice_id": "v-1",
            "name": "Rachel",
            "category": "premade",
            "labels": {"accent": "american"},
            "preview_url": "https://example.invalid/p.mp3",
        },
        {"voice_id": "v-2", "name": "Adam"},
        "not-a-dict",
    ]
}


def make_client(routes=None, *, error=None, **kwargs) -> tuple[ElevenLabsClient, RoutedClient]:
    stub = RoutedClient(
        routes
        if routes is not None
        else {
            "/v1/user": StubResponse(200, {"subscription": {"tier": "free"}}),
            "/v1/models": StubResponse(200, MODELS),
            "/v2/voices": StubResponse(200, VOICES),
        },
        error=error,
    )
    return ElevenLabsClient("sk_test_key", client=stub, **kwargs), stub


# --------------------------------------------------------------------------- #
# Request shape — a stub that accepts anything would not catch these
# --------------------------------------------------------------------------- #
async def test_the_key_is_sent_as_xi_api_key_not_bearer():
    """ElevenLabs uses ``xi-api-key``. A Bearer token would be a silent 401."""
    client, stub = make_client()
    await client.list_models()
    sent = stub.calls[0]
    assert sent["headers"] == {"xi-api-key": "sk_test_key"}
    assert "Authorization" not in sent["headers"]


async def test_synthesis_posts_to_the_voice_path_with_the_model():
    client, stub = make_client(
        routes={"/stream": StubResponse(200, content=b"MP3BYTES")}
    )
    audio, mime = await client.synthesize(
        "Hello there.", voice_id="v-1", model_id="eleven_flash_v2_5"
    )
    assert audio == b"MP3BYTES"
    assert mime == "audio/mpeg"
    call = stub.calls[0]
    assert call["method"] == "POST"
    assert call["url"].endswith("/v1/text-to-speech/v-1/stream")
    assert call["json"] == {"text": "Hello there.", "model_id": "eleven_flash_v2_5"}
    # mp3_44100_128 needs no paid tier and plays in every browser.
    assert call["params"] == {"output_format": "mp3_44100_128"}


async def test_transcription_is_multipart_with_the_model_id():
    client, stub = make_client(
        routes={"/speech-to-text": StubResponse(200, {"text": "build a calculator"})}
    )
    transcript = await client.transcribe(b"RIFF....", filename="clip.webm")
    assert transcript.text == "build a calculator"
    call = stub.calls[0]
    assert call["method"] == "POST"
    assert call["data"]["model_id"] == DEFAULT_STT_MODEL
    assert "file" in call["files"]


# --------------------------------------------------------------------------- #
# Model discovery
# --------------------------------------------------------------------------- #
async def test_models_are_parsed_and_speech_models_come_first():
    client, _ = make_client()
    models = await client.list_models()
    assert [m.id for m in models[:2]] == ["eleven_flash_v2_5", "eleven_v4_turbo"]
    assert models[-1].id == "scribe_v2"
    flash = models[0]
    assert flash.can_tts is True
    assert flash.max_text_length == 40000
    assert flash.cost_multiplier == 0.5
    assert flash.languages == ["English"]


async def test_a_model_without_an_id_is_skipped_rather_than_crashing():
    client, _ = make_client(routes={"/v1/models": StubResponse(200, [{"name": "x"}, MODELS[1]])})
    models = await client.list_models()
    assert [m.id for m in models] == ["eleven_flash_v2_5"]


# --------------------------------------------------------------------------- #
# Errors name the real cause
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("code", [401, 403])
async def test_a_rejected_key_says_rejected(code):
    client, _ = make_client(routes={"/v1/models": StubResponse(code)})
    with pytest.raises(ElevenLabsError) as caught:
        await client.list_models()
    assert "rejected the API key" in str(caught.value)
    assert caught.value.status == code
    # The key must never appear in an error.
    assert "sk_test_key" not in str(caught.value)


async def test_a_validation_error_is_distinguished_from_a_bad_key():
    client, _ = make_client(
        routes={"/speech-to-text": StubResponse(422, {"detail": [{"msg": "bad model"}]})}
    )
    with pytest.raises(ElevenLabsError) as caught:
        await client.transcribe(b"audio")
    assert "invalid" in str(caught.value)
    assert caught.value.detail == "bad model"


async def test_a_rate_limit_and_a_server_error_are_reported_as_such():
    for code, fragment in ((429, "rate limit"), (503, "503")):
        client, _ = make_client(routes={"/v1/models": StubResponse(code)})
        with pytest.raises(ElevenLabsError) as caught:
            await client.list_models()
        assert fragment in str(caught.value)


async def test_a_network_failure_is_named_not_swallowed():
    client, _ = make_client(error=httpx.ConnectError("no route to host"))
    with pytest.raises(ElevenLabsError) as caught:
        await client.verify_key()
    assert "Could not reach ElevenLabs" in str(caught.value)
    assert caught.value.detail == "ConnectError"


async def test_an_empty_recording_is_refused_locally():
    """No request is made for empty audio, and the reason is specific."""
    client, stub = make_client()
    with pytest.raises(ElevenLabsError) as caught:
        await client.transcribe(b"")
    assert "no audio" in str(caught.value).lower()
    # The specific reason lives in the detail, not only in the headline.
    assert "empty" in (caught.value.detail or "").lower()
    assert stub.calls == [], "no request should be made for empty audio"


async def test_synthesis_without_a_voice_says_so():
    client, _ = make_client()
    with pytest.raises(ElevenLabsError) as caught:
        await client.synthesize("hello", voice_id="")
    assert "No voice is selected" in str(caught.value)


async def test_an_empty_transcript_is_a_result_not_an_error():
    """The user may simply not have spoken."""
    client, _ = make_client(routes={"/speech-to-text": StubResponse(200, {"text": ""})})
    transcript = await client.transcribe(b"audio")
    assert transcript.is_empty is True


# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #
def test_short_text_is_one_chunk():
    assert chunk_text("Hello there.") == ["Hello there."]


def test_long_text_splits_on_sentences():
    text = " ".join(f"This is sentence number {i}." for i in range(60))
    chunks = chunk_text(text, limit=200)
    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
    # No words are lost or broken.
    assert " ".join(chunks).split() == text.split()


def test_a_single_sentence_longer_than_the_limit_is_still_split():
    chunks = chunk_text("x" * 50, limit=20)
    assert all(len(chunk) <= 20 for chunk in chunks)
    assert "".join(chunks) == "x" * 50


def test_empty_text_produces_no_chunks():
    assert chunk_text("   ") == []


# --------------------------------------------------------------------------- #
# The transport
# --------------------------------------------------------------------------- #
class Line:
    """Minimal stand-in for ``NarrationLine``."""

    def __init__(self, text: str, line_id: str = "line-1") -> None:
        self.text = text
        self.id = line_id


async def test_without_configuration_the_transport_records_and_says_so():
    transport = ElevenLabsTransport(lambda: _none())
    line = Line("Task complete.")
    await transport.deliver(line)
    assert transport.name == "recording"
    assert transport.audio_available is False
    # The line is still kept, so nothing is silently lost.
    assert transport.recent_lines() == [line]
    assert transport.audio_for("line-1") is None


async def _none():
    return None


async def test_when_configured_the_transport_synthesises_real_audio():
    client, _ = make_client(routes={"/stream": StubResponse(200, content=b"AUDIO")})

    async def config():
        return type("C", (), {"client": client, "voice_id": "v-1", "model_id": "m"})()

    transport = ElevenLabsTransport(config)
    await transport.deliver(Line("Working on it."))
    assert transport.name == "elevenlabs"
    assert transport.audio_available is True
    assert transport.audio_for("line-1") == (b"AUDIO", "audio/mpeg")


async def test_a_synthesis_failure_keeps_the_line_and_loses_only_the_audio():
    """A task must never break because a voice was unavailable."""

    class Broken:
        async def synthesize(self, *_args, **_kwargs):
            raise ElevenLabsError("ElevenLabs rejected the API key.")

    async def config():
        return type("C", (), {"client": Broken(), "voice_id": "v", "model_id": "m"})()

    transport = ElevenLabsTransport(config)
    line = Line("Still worth saying.")
    await transport.deliver(line)  # must not raise
    assert transport.recent_lines() == [line]
    assert transport.audio_for("line-1") is None


async def test_an_unexpected_transport_error_is_contained():
    async def config():
        raise RuntimeError("the settings store exploded")

    transport = ElevenLabsTransport(config)
    line = Line("Survives.")
    await transport.deliver(line)  # must not raise
    assert transport.recent_lines() == [line]


async def test_configuration_is_resolved_per_line_not_cached():
    """Saving a model or voice takes effect on the next line, not the next boot."""
    client, stub = make_client(routes={"/stream": StubResponse(200, content=b"X")})
    seen: list[str] = []

    async def config():
        seen.append("resolved")
        return type("C", (), {"client": client, "voice_id": "v", "model_id": "m"})()

    transport = ElevenLabsTransport(config)
    await transport.deliver(Line("one", "a"))
    await transport.deliver(Line("two", "b"))
    assert seen == ["resolved", "resolved"]


async def test_stop_records_a_barge_in():
    transport = ElevenLabsTransport(lambda: _none())
    await transport.stop()
    await transport.stop()
    assert transport.stops == 2


async def test_audio_storage_is_bounded():
    client, _ = make_client(routes={"/stream": StubResponse(200, content=b"X")})

    async def config():
        return type("C", (), {"client": client, "voice_id": "v", "model_id": "m"})()

    transport = ElevenLabsTransport(config, keep=3)
    for index in range(6):
        await transport.deliver(Line("hi", f"line-{index}"))
    assert transport.audio_for("line-0") is None, "old audio must be evicted"
    assert transport.audio_for("line-5") is not None


# --------------------------------------------------------------------------- #
# End to end through the container
# --------------------------------------------------------------------------- #
@pytest.fixture
async def container(settings_factory):
    instance = await Container.create(settings_factory())
    try:
        yield instance
    finally:
        await instance.close()


async def test_voice_config_is_none_without_a_key(container):
    assert await container.settings_service.voice_config() is None


async def test_voice_config_uses_the_selected_model_and_voice(container, monkeypatch):
    from app.services import settings_service as module

    stub = RoutedClient({"/v2/voices": StubResponse(200, VOICES)})
    monkeypatch.setattr(
        module.httpx, "AsyncClient", lambda **_kwargs: stub
    )
    await container.settings_service.update(
        SettingsUpdate(
            elevenlabs_api_key="sk_live_key",
            elevenlabs_model_id="eleven_multilingual_v2",
            elevenlabs_tts_voice_id="v-2",
        )
    )
    config = await container.settings_service.voice_config()
    assert config is not None
    assert config.model_id == "eleven_multilingual_v2"
    assert config.voice_id == "v-2"


async def test_voice_config_falls_back_to_the_accounts_first_voice(container, monkeypatch):
    """A hardcoded voice id may not exist for a given account."""
    from app.services import settings_service as module

    stub = RoutedClient({"/v2/voices": StubResponse(200, VOICES)})
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **_kwargs: stub)
    await container.settings_service.update(
        SettingsUpdate(elevenlabs_api_key="sk_live_key")
    )
    config = await container.settings_service.voice_config()
    assert config is not None
    assert config.voice_id == "v-1", "should use a voice the account actually has"
    assert config.model_id == DEFAULT_TTS_MODEL


async def test_narration_reports_audio_unavailable_until_configured(container):
    assert container.narration.state()["audio_available"] is False
    assert container.narration.state()["transport"] == "recording"