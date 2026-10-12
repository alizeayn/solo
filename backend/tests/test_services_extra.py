"""Tests for provider error handling, the event bus, and adapter failures.

These cover the acceptance criterion "provider-adapter error handling" without
touching the network: ``httpx.AsyncClient`` is replaced with a stub.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

import app.services.settings_service as settings_module
from app.adapters import build_adapter
from app.container import Container
from app.domain import TaskStatus
from app.repositories import ProjectRepository, TaskRepository
from app.schemas import SettingsUpdate
from app.services.context import build_snapshot, offline_answer
from app.services.event_bus import EventBus
from app.services.orchestrator import OrchestratorService
from app.services.project_service import resolve_project_root


class FailingAdapter:
    """Adapter whose run always raises, to exercise the failure path."""

    name = "failing"

    async def start(self) -> None:
        return None

    async def run(self, **_kwargs):
        raise RuntimeError("boom: simulated adapter failure")

    async def steer(self, **_kwargs) -> None:
        return None

    async def cancel(self, **_kwargs) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def health(self) -> dict:
        return {"backend": self.name, "available": False}


class _StubResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class _StubClient:
    """Stand-in for ``httpx.AsyncClient`` used by the connection tests."""

    def __init__(self, *, response=None, error=None) -> None:
        self._response = response
        self._error = error

    async def __aenter__(self) -> "_StubClient":
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False

    async def get(self, *_args, **_kwargs):
        if self._error:
            raise self._error
        return self._response


def _patch_http(monkeypatch, *, response=None, error=None) -> None:
    monkeypatch.setattr(
        settings_module.httpx,
        "AsyncClient",
        lambda **_kwargs: _StubClient(response=response, error=error),
    )


class _RoutedClient:
    """Stand-in for ``httpx.AsyncClient`` that routes by URL.

    The ElevenLabs check makes three calls (account, models, voices), so a
    single canned response is not enough. ``routes`` maps a URL fragment to
    ``(status_code, payload)``; anything unmatched is a 404.
    """

    def __init__(self, routes=None, *, error=None) -> None:
        self._routes = routes or {}
        self._error = error
        self.calls: list[str] = []

    async def __aenter__(self) -> "_RoutedClient":
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False

    async def request(self, method, url, **_kwargs):
        self.calls.append(url)
        if self._error:
            raise self._error
        for fragment, (code, payload) in self._routes.items():
            if fragment in url:
                return _StubResponse(code, payload)
        return _StubResponse(404)

    async def get(self, url, **_kwargs):
        return await self.request("GET", url)

    async def post(self, url, **_kwargs):
        return await self.request("POST", url)

    async def aclose(self) -> None:
        """The real client is closed when the caller owns it."""

    async def close(self) -> None:
        pass


def _patch_elevenlabs(monkeypatch, *, user=(200, {}), models=None, voices=None, error=None):
    """Patch ``httpx.AsyncClient`` for the ElevenLabs code path."""
    from app.services import elevenlabs as elevenlabs_module

    routes = {
        "/v1/user": user,
        "/v1/models": models if models is not None else (200, _DEFAULT_MODELS),
        "/v2/voices": voices if voices is not None else (200, _DEFAULT_VOICES),
    }
    holder = {}

    def factory(**_kwargs):
        holder["client"] = _RoutedClient(routes, error=error)
        return holder["client"]

    monkeypatch.setattr(elevenlabs_module.httpx, "AsyncClient", factory)
    return holder


_DEFAULT_MODELS = [
    {
        "model_id": "eleven_flash_v2_5",
        "name": "Eleven Flash v2.5",
        "can_do_text_to_speech": True,
        "maximum_text_length_per_request": 40000,
    },
    {
        "model_id": "scribe_v2",
        "name": "Scribe v2",
        "can_do_text_to_speech": False,
    },
]

_DEFAULT_VOICES = {"voices": [{"voice_id": "voice-1", "name": "Rachel"}]}


@pytest.fixture
async def container(settings_factory):
    instance = await Container.create(settings_factory())
    try:
        yield instance
    finally:
        await instance.close()


# --------------------------------------------------------------------------- #
# OpenRouter
# --------------------------------------------------------------------------- #
async def test_openrouter_missing_key(container):
    result = await container.settings_service.test_openrouter()
    assert result.ok is False
    assert "No OpenRouter" in result.message


async def test_openrouter_valid_key(container, monkeypatch):
    await container.settings_service.update(
        SettingsUpdate(openrouter_api_key="sk-or-v1-abcdefgh")
    )
    _patch_http(
        monkeypatch, response=_StubResponse(200, {"data": {"label": "personal"}})
    )
    result = await container.settings_service.test_openrouter()
    assert result.ok is True
    assert "personal" in result.message


@pytest.mark.parametrize("status_code", [401, 403])
async def test_openrouter_rejects_invalid_key(container, monkeypatch, status_code):
    await container.settings_service.update(
        SettingsUpdate(openrouter_api_key="sk-or-v1-badkey12")
    )
    _patch_http(monkeypatch, response=_StubResponse(status_code))
    result = await container.settings_service.test_openrouter()
    assert result.ok is False
    assert "rejected" in result.message


async def test_openrouter_unexpected_status(container, monkeypatch):
    await container.settings_service.update(
        SettingsUpdate(openrouter_api_key="sk-or-v1-abcdefgh")
    )
    _patch_http(monkeypatch, response=_StubResponse(500))
    result = await container.settings_service.test_openrouter()
    assert result.ok is False
    assert "500" in result.message


async def test_openrouter_network_error(container, monkeypatch):
    await container.settings_service.update(
        SettingsUpdate(openrouter_api_key="sk-or-v1-abcdefgh")
    )
    _patch_http(monkeypatch, error=httpx.ConnectError("no route to host"))
    result = await container.settings_service.test_openrouter()
    assert result.ok is False
    assert "Could not reach OpenRouter" in result.message
    # The API key must never leak into the error detail.
    assert "abcdefgh" not in (result.detail or "")


# --------------------------------------------------------------------------- #
# ElevenLabs
# --------------------------------------------------------------------------- #
async def test_elevenlabs_missing_key(container):
    result = await container.settings_service.test_elevenlabs()
    assert result.ok is False


async def test_elevenlabs_valid_needs_no_agent_id(container, monkeypatch):
    """A valid key is enough: Solo uses TTS and STT, not the Agents Platform."""
    await container.settings_service.update(
        SettingsUpdate(elevenlabs_api_key="sk_abcdef123456")
    )
    _patch_elevenlabs(monkeypatch)
    result = await container.settings_service.test_elevenlabs()
    assert result.ok is True
    # The message states what was actually found, not merely that a key exists.
    assert "speech model" in result.message
    assert "eleven_flash_v2_5" in (result.detail or "")


async def test_elevenlabs_reports_the_selected_model(container, monkeypatch):
    await container.settings_service.update(
        SettingsUpdate(
            elevenlabs_api_key="sk_abcdef123456",
            elevenlabs_model_id="eleven_multilingual_v2",
        )
    )
    _patch_elevenlabs(monkeypatch)
    result = await container.settings_service.test_elevenlabs()
    assert result.ok is True
    assert "eleven_multilingual_v2" in (result.detail or "")


async def test_elevenlabs_rejects_invalid_key(container, monkeypatch):
    # Validation reads the model catalog, so that is where a rejection shows.
    await container.settings_service.update(
        SettingsUpdate(elevenlabs_api_key="sk_abcdef123456")
    )
    _patch_elevenlabs(
        monkeypatch,
        models=(
            401,
            {
                "detail": {
                    "code": "unauthorized",
                    "message": "Invalid API key",
                    "status": "invalid_api_key",
                }
            },
        ),
    )
    result = await container.settings_service.test_elevenlabs()
    assert result.ok is False
    assert "abcdef123456" not in (result.message or "")
    assert "abcdef123456" not in (result.detail or "")


async def test_a_scoped_key_is_not_reported_as_rejected(container, monkeypatch):
    """The live-API case: valid for speech, but without `user_read`.

    Reporting this as "rejected" would send the user to regenerate a key that
    works. It must be reported as a permission problem, and validation must still
    succeed because models are readable.
    """
    await container.settings_service.update(
        SettingsUpdate(
            elevenlabs_api_key="sk_scoped", elevenlabs_tts_voice_id="voice-1"
        )
    )
    _patch_elevenlabs(
        monkeypatch,
        voices=(
            401,
            {
                "detail": {
                    "type": "authentication_error",
                    "code": "unauthorized",
                    "message": (
                        "The API key you used is missing the permission "
                        "voices_read to execute this operation."
                    ),
                    "status": "missing_permissions",
                }
            },
        ),
    )
    result = await container.settings_service.test_elevenlabs()
    assert result.ok is True, "a speech-capable key must not fail validation"
    # The permission problem is explained, and the integration still works.
    assert "voices_read" in (result.detail or "")
    assert result.state == "configured"
    # The API's own message survives, instead of a generic "rejected".
    assert "rejected" not in result.message.lower()


async def test_a_paid_plan_error_keeps_its_explanation(container, monkeypatch):
    """A 402 must say *why*, not become a generic HTTP error."""
    await container.settings_service.update(
        SettingsUpdate(elevenlabs_api_key="sk_free_plan")
    )
    _patch_elevenlabs(
        monkeypatch,
        models=(
            402,
            {
                "detail": {
                    "code": "paid_plan_required",
                    "message": "Free users cannot use library voices via the API.",
                    "status": "payment_required",
                }
            },
        ),
    )
    result = await container.settings_service.test_elevenlabs()
    assert result.ok is False
    assert "paid plan" in result.message.lower() or "library voices" in result.message.lower()


async def test_elevenlabs_without_a_usable_voice_asks_for_one(
    container, monkeypatch
):
    """No voice and no way to list one is a distinct, actionable state."""
    await container.settings_service.update(
        SettingsUpdate(elevenlabs_api_key="sk_abcdef123456")
    )
    _patch_elevenlabs(monkeypatch, voices=(200, {"voices": []}))
    result = await container.settings_service.test_elevenlabs()
    assert result.ok is False
    assert result.state == "needs_voice"
    assert "voice" in result.detail.lower()


async def test_elevenlabs_network_failure_is_named(container, monkeypatch):
    await container.settings_service.update(
        SettingsUpdate(elevenlabs_api_key="sk_abcdef123456")
    )
    _patch_elevenlabs(
        monkeypatch, error=httpx.ConnectError("no route to host")
    )
    result = await container.settings_service.test_elevenlabs()
    assert result.ok is False
    assert "Could not reach ElevenLabs" in result.message
    assert "abcdef123456" not in (result.detail or "")


# --------------------------------------------------------------------------- #
# Adapter factory
# --------------------------------------------------------------------------- #
def test_build_adapter_unknown_backend(settings_factory):
    with pytest.raises(ValueError, match="unknown coding-agent backend"):
        build_adapter(settings_factory(), backend="does-not-exist")


def test_build_adapter_pi_is_deferred(settings_factory):
    # Phase 1 must not silently fall back to the mock adapter.
    from app.adapters.pi_agent import PiCodingAgentAdapter

    assert isinstance(build_adapter(settings_factory(), backend="pi"), PiCodingAgentAdapter)


# --------------------------------------------------------------------------- #
# Event bus
# --------------------------------------------------------------------------- #
async def test_event_bus_fans_out_to_all_subscribers():
    bus = EventBus()
    first = await bus.subscribe()
    second = await bus.subscribe()
    await bus.publish({"hello": "world"})
    assert (await first.get())["hello"] == "world"
    assert (await second.get())["hello"] == "world"
    await bus.unsubscribe(first)
    await bus.unsubscribe(second)
    assert bus.subscriber_count == 0


async def test_event_bus_drops_oldest_for_slow_subscriber():
    bus = EventBus(queue_size=2)
    queue = await bus.subscribe()
    for index in range(5):
        await bus.publish({"index": index})
    assert queue.qsize() == 2
    assert (await queue.get())["index"] == 3


# --------------------------------------------------------------------------- #
# Adapter failure → FAILED task
# --------------------------------------------------------------------------- #
async def test_adapter_failure_marks_task_failed(settings_factory):
    container = await Container.create(settings_factory())
    try:
        orchestrator = OrchestratorService(
            session_factory=container.session_factory,
            bus=container.bus,
            adapter=FailingAdapter(),
            settings=container.settings,
        )
        async with container.session_factory() as session:
            project = await ProjectRepository(session).create(
                name="boom", slug="boom", root_path="boom"
            )
            await session.commit()

        task = await orchestrator.start_coding_task(
            project_id=project.id, instruction="this will fail"
        )
        for _ in range(200):
            async with container.session_factory() as session:
                current = await TaskRepository(session).get(task.id)
            if current is not None and current.status in {"FAILED", "COMPLETED"}:
                break
            await asyncio.sleep(0.01)

        assert current is not None
        assert current.status == TaskStatus.FAILED.value
        assert current.error and "boom" in current.error
        await orchestrator.shutdown()
    finally:
        await container.close()


# --------------------------------------------------------------------------- #
# Context snapshot helpers
# --------------------------------------------------------------------------- #
async def test_snapshot_and_offline_answer(settings_factory):
    container = await Container.create(settings_factory())
    try:
        async with container.session_factory() as session:
            project = await ProjectRepository(session).create(
                name="ctx", slug="ctx", root_path="ctx"
            )
            await session.commit()
            root = resolve_project_root(container.settings, project)
            root.mkdir(parents=True, exist_ok=True)
            (root / "main.py").write_text("print(1)")
            (root / "README.md").write_text("# hi")
            await TaskRepository(session).create(
                project_id=project.id,
                instruction="add a feature",
                task_type="CODING",
                status=TaskStatus.RUNNING,
            )
            await session.commit()

            snapshot = await build_snapshot(session, project, root)
            assert snapshot.file_count == 2
            assert snapshot.active_task is not None

            prompt = snapshot.to_prompt_text()
            assert "ctx" in prompt
            assert "Active task" in prompt

            answer = offline_answer(snapshot, "what is in main.py?")
            assert "main.py" in answer

            summary = offline_answer(snapshot, "give me an overview")
            assert "2 file" in summary
            assert "active" in summary.lower()
    finally:
        await container.close()
