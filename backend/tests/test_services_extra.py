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


async def test_elevenlabs_valid_without_agent_id(container, monkeypatch):
    await container.settings_service.update(
        SettingsUpdate(elevenlabs_api_key="sk_abcdef123456")
    )
    _patch_http(monkeypatch, response=_StubResponse(200))
    result = await container.settings_service.test_elevenlabs()
    assert result.ok is False
    assert "Agent ID" in result.message


async def test_elevenlabs_valid_with_agent_id(container, monkeypatch):
    await container.settings_service.update(
        SettingsUpdate(
            elevenlabs_api_key="sk_abcdef123456", elevenlabs_agent_id="agent_1"
        )
    )
    _patch_http(monkeypatch, response=_StubResponse(200))
    result = await container.settings_service.test_elevenlabs()
    assert result.ok is True


async def test_elevenlabs_rejects_invalid_key(container, monkeypatch):
    await container.settings_service.update(
        SettingsUpdate(elevenlabs_api_key="sk_abcdef123456")
    )
    _patch_http(monkeypatch, response=_StubResponse(401))
    result = await container.settings_service.test_elevenlabs()
    assert result.ok is False
    assert "rejected" in result.message


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
