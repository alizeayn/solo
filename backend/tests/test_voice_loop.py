"""The complete voice loop, end to end, with a stubbed ElevenLabs service.

This is the phase's acceptance test. It exercises the exact sequence the user
asked for, and every step is the real code path:

1. Save an ElevenLabs API key.
2. Retrieve the models the account can use.
3. Select a speech model and a voice, and confirm the *runtime* picks them up.
4. Transcribe a recorded utterance.
5. Dispatch the transcript through the existing message endpoint.
6. Pi Agent (simulator) executes it; milestones are derived from real events.
7. Narration selects what is worth saying.
8. The ElevenLabs transport synthesises each line.
9. The audio is served back by line id.

Only the network is faked. Everything between the HTTP boundary and the
synthesised bytes is the production path, which is the point: a test that stubbed
the transport would prove nothing about the integration.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

# --------------------------------------------------------------------------- #
# A routed stand-in for the ElevenLabs API
# --------------------------------------------------------------------------- #

MODELS = [
    {
        "model_id": "eleven_flash_v2_5",
        "name": "Eleven Flash v2.5",
        "can_do_text_to_speech": True,
        "maximum_text_length_per_request": 40000,
        "model_rates": {"character_cost_multiplier": 0.5},
        "languages": [{"language_id": "en", "name": "English"}],
    },
    {
        "model_id": "scribe_v2",
        "name": "Scribe v2",
        "can_do_text_to_speech": False,
    },
]

VOICES = {"voices": [{"voice_id": "voice-1", "name": "Rachel", "category": "premade"}]}


class Response:
    def __init__(self, status_code: int, payload=None, content: bytes = b"") -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = content

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class StubElevenLabs:
    """Routes by URL, and records what was actually asked for."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.synthesised: list[str] = []
        self.transcribed = 0

    async def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url})
        if "/v1/user" in url:
            return Response(200, {"subscription": {"tier": "creator"}})
        if "/v1/models" in url:
            return Response(200, MODELS)
        if "/v2/voices" in url:
            return Response(200, VOICES)
        if "/v1/single-use-token/" in url:
            # Realtime needs a scoped token, not the API key. The type is part
            # of the path and is validated by the real service.
            if not url.endswith("/realtime_scribe"):
                return Response(422, {"detail": "unsupported token type"})
            return Response(200, {"token": "sutkn_stub_token"})
        if "/v1/speech-to-text" in url:
            self.transcribed += 1
            return Response(
                200,
                {"text": "Write a simple Python calculator", "language_code": "en"},
            )
        if "/v1/text-to-speech/" in url:
            text = (kwargs.get("json") or {}).get("text", "")
            self.synthesised.append(text)
            # A distinct byte string per line, so the test can prove the exact
            # audio for a line is what gets served back.
            return Response(200, content=b"ID3" + text.encode()[:40])
        return Response(404)

    async def aclose(self) -> None:
        pass


@pytest.fixture
def elevenlabs(monkeypatch) -> StubElevenLabs:
    stub = StubElevenLabs()
    from app.services import elevenlabs as module

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **_kwargs: stub)
    return stub


@pytest.fixture
def client(settings_factory, elevenlabs) -> TestClient:
    """An app with the deterministic agent, so the loop is reproducible."""
    settings: Settings = settings_factory(agent_backend="mock", mock_step_delay=0.0)
    app = create_app(settings)
    with TestClient(app) as test_client:
        # Narration paces delivery in production so speech never runs together.
        # The pacing itself is covered in test_account_and_voice.py; here it only
        # slows the test down.
        app.state.container.narration._min_interval = 0.0
        yield test_client


def _sign_in(client: TestClient) -> None:
    """Create the admin account, as conftest's ``authed`` fixture does.

    This module builds its own client (the ElevenLabs stub must be in place
    before the app is created), so it cannot reuse the shared fixture.
    """
    from tests.conftest import ADMIN

    response = client.post("/api/auth/setup", json=ADMIN)
    assert response.status_code == 201, response.text


# --------------------------------------------------------------------------- #
# Step 1-3: configure, discover, select
# --------------------------------------------------------------------------- #
def test_the_key_can_be_saved_tested_and_validated(client, elevenlabs):
    _sign_in(client)

    saved = client.put("/api/settings", json={"elevenlabs_api_key": "sk_live_abc123"})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["elevenlabs_api_key"]["configured"] is True
    # The key itself is never returned.
    assert "sk_live_abc123" not in saved.text

    result = client.post("/api/settings/test/elevenlabs").json()
    assert result["ok"] is True, result
    # The message states what was found, not merely that a key exists.
    assert "speech model" in result["message"]


def test_models_and_voices_are_discovered_from_the_account(client, elevenlabs):
    _sign_in(client)
    client.put("/api/settings", json={"elevenlabs_api_key": "sk_live_abc123"})

    models = client.get("/api/voice/models").json()
    assert [model["id"] for model in models] == ["eleven_flash_v2_5", "scribe_v2"]
    assert models[0]["can_tts"] is True
    assert models[0]["max_text_length"] == 40000
    assert models[0]["languages"] == ["English"]
    assert models[1]["can_tts"] is False, "a recognition model is not offered as a voice"

    voices = client.get("/api/voice/voices").json()
    assert voices == [
        {
            "id": "voice-1",
            "name": "Rachel",
            "category": "premade",
            "description": None,
            "labels": {},
            "preview_url": None,
        }
    ]


def test_model_discovery_without_a_key_names_the_key(client):
    _sign_in(client)
    response = client.get("/api/voice/models")
    assert response.status_code == 400
    assert "ElevenLabs API key" in response.json()["detail"]


def test_the_selected_model_and_voice_reach_the_runtime(client, elevenlabs):
    """Selecting is not merely displayed: the transport uses it."""
    _sign_in(client)
    client.put("/api/settings", json={"elevenlabs_api_key": "sk_live_abc123"})

    state = client.put(
        "/api/voice/settings",
        json={"model_id": "eleven_flash_v2_5", "voice_id": "voice-1"},
    ).json()
    assert state["model_id"] == "eleven_flash_v2_5"
    assert state["voice_id"] == "voice-1"
    assert state["configured"] is True
    # A configured account reports audio as available until an attempt actually
    # fails. What must never happen is reporting it available *after* a failure.
    assert state["voice_configured"] is True
    assert state["audio_available"] is True, "a configured transport must report audio"
    assert state["phase"] == "voice-active"

    # And it survives a settings round trip, i.e. it is the stored value.
    settings = client.get("/api/settings").json()
    assert settings["elevenlabs_model_id"] == "eleven_flash_v2_5"
    assert settings["elevenlabs_tts_voice_id"] == "voice-1"


# --------------------------------------------------------------------------- #
# Step 4: speech in
# --------------------------------------------------------------------------- #
def test_transcription_returns_text_without_dispatching_it(client, elevenlabs):
    """Transcription produces text; dispatching it is a separate, explicit step."""
    _sign_in(client)
    client.put("/api/settings", json={"elevenlabs_api_key": "sk_live_abc123"})

    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("utterance.webm", b"\x1aE\xdf\xa3fake-webm", "audio/webm")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == "Write a simple Python calculator"
    assert body["empty"] is False
    assert elevenlabs.transcribed == 1
    # Nothing was created: the caller decides what to do with the text.
    assert client.get("/api/tasks").json() == []


def test_an_empty_utterance_is_refused_before_calling_elevenlabs(client, elevenlabs):
    _sign_in(client)
    client.put("/api/settings", json={"elevenlabs_api_key": "sk_live_abc123"})

    response = client.post(
        "/api/voice/transcribe",
        files={"file": ("empty.webm", b"", "audio/webm")},
    )
    assert response.status_code == 400
    assert elevenlabs.transcribed == 0


# --------------------------------------------------------------------------- #
# Steps 5-9: the full loop
# --------------------------------------------------------------------------- #
def test_a_spoken_task_runs_and_the_progress_is_spoken_back(client, elevenlabs):
    """The acceptance test: speak a task, watch it run, hear it narrated.

    The transcript is posted to ``/api/projects/{id}/messages`` — the same
    endpoint a typed message uses — so this also proves the voice path is not a
    parallel system.
    """
    _sign_in(client)
    client.put("/api/settings", json={"elevenlabs_api_key": "sk_live_abc123"})
    client.put(
        "/api/voice/settings",
        json={"model_id": "eleven_flash_v2_5", "voice_id": "voice-1"},
    )

    project = client.post("/api/projects", json={"name": "voice-loop"}).json()

    # --- speak ------------------------------------------------------------ #
    transcript = client.post(
        "/api/voice/transcribe",
        files={"file": ("utterance.webm", b"\x1aE\xdf\xa3fake", "audio/webm")},
    ).json()
    assert transcript["text"]

    # --- the existing task path, unchanged -------------------------------- #
    dispatch = client.post(
        f"/api/projects/{project['id']}/messages",
        json={"content": transcript["text"]},
    )
    assert dispatch.status_code == 201, dispatch.text
    task_id = dispatch.json()["task_id"]
    assert task_id, "a spoken coding instruction must create a task"

    # --- wait for the agent ------------------------------------------------ #
    deadline = time.monotonic() + 20
    status = None
    while time.monotonic() < deadline:
        status = client.get(f"/api/tasks/{task_id}").json()["status"]
        if status in {"COMPLETED", "FAILED", "CANCELLED"}:
            break
        time.sleep(0.02)
    assert status == "COMPLETED", f"task ended as {status}"

    # --- milestones were derived from the run ------------------------------ #
    milestones = client.get(f"/api/milestones/task/{task_id}").json()
    stages = [item["stage"] for item in milestones]
    assert stages[0] == "understanding"
    assert "implementing" in stages
    assert stages[-1] == "completed"
    assert all(item["evidence"] for item in milestones)

    # --- narration selected what was worth saying -------------------------- #
    # Wait for the queue to drain, not merely for one line to appear:
    # otherwise the comparison below races the narration worker.
    deadline = time.monotonic() + 15
    state: dict = {}
    while time.monotonic() < deadline:
        state = client.get("/api/voice/state").json()
        if state["queued"] == 0 and state["spoken"] >= 1:
            break
        time.sleep(0.02)

    lines = client.get("/api/voice/history").json()
    spoken = [line for line in lines if line.get("spoken")]
    assert lines, "a completed task produced nothing for the voice channel"
    assert spoken, "no line reached the transport"
    # Milestones are spoken; tool calls are not. Every line must be a milestone
    # or an outcome, never low-level activity.
    assert all(line["text"] for line in lines)
    # `reply` carries the agent's acknowledgement and `file` a file change. Both
    # are conversational, not low-level: a spoken conversation needs the agent to
    # confirm what it understood, and the user asked which files changed.
    assert all(
        line["kind"]
        in {"progress", "outcome", "summary", "milestone", "error", "reply", "file"}
        for line in lines
    ), [line["kind"] for line in lines]

    kinds = {line["kind"] for line in lines}
    assert "reply" in kinds, "the agent never acknowledged the request aloud"
    acknowledgement = next(line for line in lines if line["kind"] == "reply")
    # It confirms what was understood by echoing the request itself.
    assert "calculator" in acknowledgement["text"].lower()
    assert acknowledgement["priority"] <= 1, "an acknowledgement must outrank progress" 

    # --- ElevenLabs actually synthesised it -------------------------------- #
    assert elevenlabs.synthesised, "the transport never called text-to-speech"
    # Every synthesised request named the selected model and voice.
    tts_calls = [call for call in elevenlabs.calls if "/text-to-speech/" in call["url"]]
    assert all("/text-to-speech/voice-1/" in call["url"] for call in tts_calls)
    assert elevenlabs.synthesised == [
        line["text"] for line in spoken
    ], "the spoken text must match what was synthesised"

    # --- and the audio is served back by line id --------------------------- #
    first = spoken[0]
    audio = client.get(f"/api/voice/audio/{first['id']}")
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/")
    assert audio.content.startswith(b"ID3")
    assert first["text"].encode()[:20] in audio.content

    # --- the state is consistent across the API ---------------------------- #
    state = client.get("/api/voice/state").json()
    assert state["audio_available"] is True
    assert state["spoken"] >= len(spoken)
    assert state["voice_id"] == "voice-1"


def test_a_question_asked_by_voice_is_answered_from_the_task_state(client, elevenlabs):
    """Voice input is not only for starting work: a question is classified too."""
    _sign_in(client)
    client.put("/api/settings", json={"elevenlabs_api_key": "sk_live_abc123"})
    project = client.post("/api/projects", json={"name": "voice-questions"}).json()

    # The stub returns a coding instruction; send a question instead by posting
    # the text directly, which is exactly what transcription would have supplied.
    dispatch = client.post(
        f"/api/projects/{project['id']}/messages",
        json={"content": "how many files are there?"},
    ).json()
    # Classified as a question and answered — not dispatched as a coding
    # task. The turn is still recorded, which is why this asserts the
    # classification and the answer rather than the absence of a row.
    assert dispatch["intent"] == "CHAT_OR_EXPLAIN"
    assert dispatch["message"]["content"], "the answer is returned as a message"


def test_audio_is_404_for_a_line_that_was_never_spoken(client, elevenlabs):
    _sign_in(client)
    client.put("/api/settings", json={"elevenlabs_api_key": "sk_live_abc123"})
    assert client.get("/api/voice/audio/does-not-exist").status_code == 404


def test_without_a_key_the_loop_still_shows_every_line(client, elevenlabs, monkeypatch):
    """Speech is optional: losing audio must not lose information."""
    _sign_in(client)
    project = client.post("/api/projects", json={"name": "no-voice"}).json()

    dispatch = client.post(
        f"/api/projects/{project['id']}/messages",
        json={"content": "add a health endpoint"},
    ).json()
    task_id = dispatch["task_id"]

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if client.get(f"/api/tasks/{task_id}").json()["status"] == "COMPLETED":
            break
        time.sleep(0.02)

    lines = client.get("/api/voice/history").json()
    assert lines, "narration must still be recorded without audio"
    # The lines are delivered to the recording transport, so they are all shown
    # but none has audio.
    assert elevenlabs.synthesised == [], "no key means no synthesis"
    state = client.get("/api/voice/state").json()
    assert state["audio_available"] is False
    assert state["transport"] == "recording"
    assert state["phase"] == "narration-only"

async def test_narration_speaks_acknowledgements_and_file_changes():
    """The two lines a spoken conversation cannot do without.

    Milestones alone made the exchange one-sided: the user asked for something and
    was answered only in text, and file work was invisible until the next phase.
    """
    from app.services.orchestrator import _file_sentence

    assert _file_sentence("added", "login.html") == "I've created login.html."
    assert _file_sentence("modified", "styles.css") == "I've updated styles.css."
    assert _file_sentence("deleted", "old.css") == "I've removed old.css."
    # An unknown verb must still produce something sayable rather than a blank.
    assert _file_sentence(None, "app.py") == "I've updated app.py."


async def test_the_greeting_endpoint_speaks_through_the_normal_pipeline(client):
    """A greeting is a narration line, not a second mechanism.

    Routing it through /api/voice/say means one synthesis path, one WebSocket
    stream and one player, so the greeting cannot drift from milestone speech.
    """
    _sign_in(client)
    response = client.post(
        "/api/voice/say", json={"text": "Hello. What would you like me to work on?", "kind": "greeting"}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["queued"] is True, payload
    assert payload["state"]["enabled"] is True
    assert payload["id"]

    # It lands in the transcript like any other line.
    history = client.get("/api/voice/history").json()
    assert any("What would you like" in line["text"] for line in history)


async def test_an_empty_greeting_is_rejected(client):
    _sign_in(client)
    response = client.post("/api/voice/say", json={"text": ""})
    assert response.status_code == 422


async def test_the_realtime_token_endpoint_never_returns_the_api_key(client, elevenlabs):
    """The browser gets a scoped token; the API key stays on the server.

    This is the documented pattern for client-side streaming, and it is the only
    reason a browser can open a Realtime socket without holding a key that could
    also spend the account's credits on anything else.
    """
    _sign_in(client)
    client.put("/api/settings", json={"elevenlabs_api_key": "sk_live_abc123"})

    response = client.post("/api/voice/stt-token")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["available"] is True, payload
    token = payload["token"]
    assert isinstance(token, str) and token
    # The socket URL and model are not secrets; the key must not appear at all.
    assert payload["url"].startswith("wss://")
    assert "xi-api-key" not in payload["url"]
    assert "xi-api-key" not in response.text
    assert "sk_" not in response.text


async def test_the_realtime_token_endpoint_explains_itself_when_unconfigured(client):
    """Unavailable is not an error: the UI falls back and says why.

    Returning 500 here would take the whole voice panel down for a condition the
    user can fix, and would leave batch transcription unreachable.
    """
    _sign_in(client)
    response = client.post("/api/voice/stt-token")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["reason"]
