"""Tests for the orchestration layer: state, OpenRouter client and the brain."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.domain import Intent, PlannedTaskStatus
from app.services.openrouter import (
    OpenRouterClient,
    OpenRouterError,
    _model_from_payload,
    _parse_json_object,
)
from app.services.orchestration_state import (
    MAX_QUEUE,
    OrchestrationState,
    PlannedTask,
)
from app.services.orchestrator_brain import IntentDecision, OrchestratorBrain

# --------------------------------------------------------------------------- #
# Orchestration state
# --------------------------------------------------------------------------- #
def test_state_round_trips_through_json():
    state = OrchestrationState(project_id="p1")
    item = state.add(PlannedTask(title="first", instruction="do a thing", priority=10))
    state.add_note("also update the docs", task_id="t1")
    state.set_active("t1", plan_id=item.id)

    restored = OrchestrationState.from_dict(state.to_dict(), project_id="p1")
    assert restored.project_id == "p1"
    assert [task.title for task in restored.queue] == ["first"]
    assert restored.active_task_id == "t1"
    assert restored.active_plan_id == item.id
    assert restored.notes[0]["text"] == "also update the docs"


def test_next_pending_respects_priority():
    state = OrchestrationState(project_id="p1")
    state.add(PlannedTask(title="low", instruction="low", priority=90))
    state.add(PlannedTask(title="high", instruction="high", priority=5))
    assert state.next_pending().title == "high"


def test_dependencies_block_until_satisfied():
    state = OrchestrationState(project_id="p1")
    first = state.add(PlannedTask(title="first", instruction="one", priority=50))
    second = state.add(
        PlannedTask(
            title="second", instruction="two", priority=1, depends_on=[first.id]
        )
    )
    # `second` has better priority but must wait for `first`.
    assert state.next_pending().id == first.id
    state.set_status(first.id, PlannedTaskStatus.DONE)
    assert state.next_pending().id == second.id


def test_notes_are_retained_and_can_be_marked_applied():
    state = OrchestrationState(project_id="p1")
    state.add_note("steer me", task_id="t1", applied="steered")
    state.add_note("pending instruction", task_id="t1")
    assert len(state.pending_notes()) == 1
    assert state.pending_notes("t1")[0]["text"] == "pending instruction"
    assert state.pending_notes("other") == []


def test_queue_is_bounded_and_drops_the_lowest_priority():
    state = OrchestrationState(project_id="p1")
    for index in range(MAX_QUEUE):
        state.add(PlannedTask(title=f"t{index}", instruction="x", priority=50))
    assert len(state.queue) == MAX_QUEUE
    state.add(PlannedTask(title="important", instruction="x", priority=0))
    assert len(state.queue) == MAX_QUEUE
    assert "important" in [task.title for task in state.queue]


def test_remove_and_clear_finished():
    state = OrchestrationState(project_id="p1")
    keep = state.add(PlannedTask(title="keep", instruction="x"))
    drop = state.add(PlannedTask(title="drop", instruction="x"))
    assert state.remove(drop.id) is True
    assert state.remove(drop.id) is False
    assert [task.id for task in state.queue] == [keep.id]

    state.set_status(keep.id, PlannedTaskStatus.DONE)
    assert state.clear_finished() == 1
    assert state.queue == []


def test_summary_reports_counts_and_next_step():
    state = OrchestrationState(project_id="p1")
    state.add(PlannedTask(title="a", instruction="x", priority=50))
    state.set_status(state.queue[0].id, PlannedTaskStatus.DONE)
    state.add(PlannedTask(title="b", instruction="x", priority=10))
    summary = state.summary()
    assert summary["queue_size"] == 2
    assert summary["status_counts"] == {"done": 1, "pending": 1}
    assert summary["next"]["title"] == "b"
    assert summary["revision"] > 0


# --------------------------------------------------------------------------- #
# OpenRouter client
# --------------------------------------------------------------------------- #
class _StubResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _StubHttp:
    def __init__(self, response: _StubResponse | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    async def __aenter__(self) -> "_StubHttp":
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False

    async def request(self, method: str, url: str, headers=None, json=None):  # noqa: A002
        self.calls.append({"method": method, "url": url, "json": json, "headers": headers})
        if self._error:
            raise self._error
        assert self._response is not None
        return self._response


def _patch_openrouter(monkeypatch, *, response=None, error=None) -> _StubHttp:
    stub = _StubHttp(response=response, error=error)
    monkeypatch.setattr(
        "app.services.openrouter.httpx.AsyncClient", lambda **_kwargs: stub
    )
    return stub


async def test_openrouter_verify_key(monkeypatch):
    _patch_openrouter(
        monkeypatch,
        response=_StubResponse(200, {"data": {"label": "my key", "usage": 1.5}}),
    )
    client = OpenRouterClient("sk-or-v1-secret")
    assert (await client.verify_key())["label"] == "my key"


async def test_openrouter_reports_provider_error_messages(monkeypatch):
    _patch_openrouter(
        monkeypatch,
        response=_StubResponse(402, {"error": {"message": "Insufficient credits"}}),
    )
    client = OpenRouterClient("sk-or-v1-secret")
    with pytest.raises(OpenRouterError) as excinfo:
        await client.verify_key()
    assert "Insufficient credits" in str(excinfo.value)
    assert excinfo.value.status == 402


async def test_openrouter_network_error_is_clear(monkeypatch):
    _patch_openrouter(monkeypatch, error=httpx.ConnectError("no route"))
    client = OpenRouterClient("sk-or-v1-secret")
    with pytest.raises(OpenRouterError, match="Could not reach OpenRouter"):
        await client.list_models()


async def test_openrouter_list_models(monkeypatch):
    _patch_openrouter(
        monkeypatch,
        response=_StubResponse(
            200,
            {
                "data": [
                    {
                        "id": "vendor/model-b",
                        "name": "B",
                        "context_length": 1000,
                        "supported_parameters": ["structured_outputs"],
                    },
                    {"id": "vendor/model-a", "name": "A"},
                ]
            },
        ),
    )
    models = await OpenRouterClient("k").list_models()
    assert [model.id for model in models] == ["vendor/model-a", "vendor/model-b"]
    assert models[1].supports_structured_output is True


async def test_openrouter_completion_extracts_text(monkeypatch):
    _patch_openrouter(
        monkeypatch,
        response=_StubResponse(200, {"choices": [{"message": {"content": "  hello  "}}]}),
    )
    assert await OpenRouterClient("k").complete(model="m", messages=[]) == "hello"


async def test_openrouter_completion_rejects_empty(monkeypatch):
    _patch_openrouter(
        monkeypatch, response=_StubResponse(200, {"choices": [{"message": {"content": ""}}]})
    )
    with pytest.raises(OpenRouterError, match="empty response"):
        await OpenRouterClient("k").complete(model="m", messages=[])


def test_model_payload_parsing_tolerates_missing_fields():
    model = _model_from_payload({"id": "x"})
    assert model.id == "x"
    assert model.name == "x"
    assert model.supports_structured_output is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('```\n{"a": 1}\n```', {"a": 1}),
    ],
)
def test_json_parsing_tolerates_code_fences(raw, expected):
    assert _parse_json_object(raw) == expected


def test_json_parsing_rejects_non_json():
    with pytest.raises(OpenRouterError, match="valid JSON"):
        _parse_json_object("not json at all")


# --------------------------------------------------------------------------- #
# Orchestrator brain
# --------------------------------------------------------------------------- #
class FakeOpenRouter:
    """Stands in for OpenRouterClient with scripted JSON responses."""

    def __init__(self, payloads: list[Any]) -> None:
        self._payloads = list(payloads)
        self.calls: list[dict] = []

    async def complete_json(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        item = self._payloads.pop(0) if self._payloads else {}
        if isinstance(item, Exception):
            raise item
        return item


def brain_with(payloads: list[Any], settings_factory) -> tuple[OrchestratorBrain, FakeOpenRouter]:
    fake = FakeOpenRouter(payloads)
    settings = settings_factory()

    async def factory():
        return fake, "test/model"

    brain = OrchestratorBrain(
        settings=settings, settings_service=None, client_factory=factory
    )
    return brain, fake


async def test_brain_classifies_intent(settings_factory):
    brain, fake = brain_with(
        [{"intent": "START_CODING_TASK", "reason": "asks for a change", "confidence": 0.9}],
        settings_factory,
    )
    decision = await brain.classify("add a login page", has_active_task=False)
    assert decision is not None
    assert decision.intent is Intent.START_CODING_TASK
    assert fake.calls[0]["schema_name"] == "intent"


async def test_brain_returns_none_when_unconfigured(settings_factory):
    brain = OrchestratorBrain(
        settings=settings_factory(), settings_service=None, client_factory=None
    )
    assert await brain.available() is False
    assert await brain.classify("hello", has_active_task=False) is None


async def test_brain_falls_back_when_the_model_errors(settings_factory):
    brain, _fake = brain_with([OpenRouterError("boom")], settings_factory)
    assert await brain.classify("hello", has_active_task=False) is None


async def test_brain_rejects_invalid_intent_values(settings_factory):
    brain, _fake = brain_with([{"intent": "DO_SOMETHING_ELSE", "reason": "x"}], settings_factory)
    assert await brain.classify("hello", has_active_task=False) is None


async def test_brain_guard_rail_clears_plans_for_questions(settings_factory):
    brain, _fake = brain_with(
        [
            {
                "intent": "CHAT_OR_EXPLAIN",
                "reason": "a question",
                "is_compound": True,
                "subtasks": [{"title": "sneaky", "instruction": "do work"}],
            }
        ],
        settings_factory,
    )
    decision = await brain.classify("what changed?", has_active_task=True)
    assert decision is not None
    assert decision.subtasks == []
    assert brain.plan_from(decision) == []


async def test_brain_decomposes_and_resolves_dependencies(settings_factory):
    brain, _fake = brain_with(
        [
            {
                "intent": "START_CODING_TASK",
                "reason": "compound request",
                "is_compound": True,
                "subtasks": [
                    {"title": "module", "instruction": "create the module", "priority": 10},
                    {
                        "title": "tests",
                        "instruction": "write tests",
                        "priority": 20,
                        "depends_on": ["module"],
                    },
                ],
            }
        ],
        settings_factory,
    )
    decision = await brain.classify("add a module and tests", has_active_task=False)
    assert decision is not None
    planned = brain.plan_from(decision)
    assert [item.title for item in planned] == ["module", "tests"]
    # The dependency must reference the generated id of the first step.
    assert planned[1].depends_on == [planned[0].id]
    assert planned[0].depends_on == []


async def test_plan_dependencies_ignore_unknown_titles(settings_factory):
    decision = IntentDecision.model_validate(
        {
            "intent": "START_CODING_TASK",
            "reason": "x",
            "subtasks": [{"title": "a", "instruction": "i", "depends_on": ["ghost"]}],
        }
    )
    brain, _fake = brain_with([], settings_factory)
    planned = brain.plan_from(decision)
    assert planned[0].depends_on == []


async def test_brain_summarises_progress(settings_factory):
    brain, fake = brain_with(
        [{"summary": "I created the module and ran the tests.", "outcome": "completed"}],
        settings_factory,
    )
    summary = await brain.summarise(
        instruction="add a module",
        status="COMPLETED",
        activity=["file.changed: Created mod.py"],
    )
    assert summary == "I created the module and ran the tests."
    assert fake.calls[0]["schema_name"] == "summary"


async def test_brain_summarise_returns_none_on_failure(settings_factory):
    brain, _fake = brain_with([OpenRouterError("down")], settings_factory)
    assert await brain.summarise(instruction="x", status="FAILED", activity=[]) is None


async def test_brain_answers_questions(settings_factory):
    brain, _fake = brain_with([{"answer": "There are three files."}], settings_factory)
    assert (
        await brain.answer_question(question="how many files?", snapshot_text="3 files")
        == "There are three files."
    )


async def test_brain_ignores_invalid_answer_payloads(settings_factory):
    brain, _fake = brain_with([{"nope": "missing"}], settings_factory)
    assert await brain.answer_question(question="q", snapshot_text="s") is None


async def test_brain_tracks_call_statistics(settings_factory):
    brain, _fake = brain_with(
        [{"intent": "CHAT_OR_EXPLAIN", "reason": "q"}, {"intent": "CHAT_OR_EXPLAIN", "reason": "q"}],
        settings_factory,
    )
    await brain.classify("a", has_active_task=False)
    await brain.classify("b", has_active_task=False)
    config = await brain.configuration()
    assert config["call_count"] == 2
    assert config["failure_count"] == 0
    assert config["last_latency_ms"] is not None
    assert config["last_model"] == "test/model"


async def test_brain_records_failures(settings_factory):
    brain, _fake = brain_with([OpenRouterError("nope")], settings_factory)
    await brain.classify("a", has_active_task=False)
    config = await brain.configuration()
    assert config["failure_count"] == 1
    assert config["last_error"] == "nope"


def test_intent_decision_rejects_out_of_range_priority():
    with pytest.raises(ValidationError):
        IntentDecision.model_validate(
            {
                "intent": "START_CODING_TASK",
                "reason": "x",
                "subtasks": [{"title": "a", "instruction": "b", "priority": 500}],
            }
        )


async def test_prompt_context_is_bounded(settings_factory):
    """Classification input must never grow with the project."""
    from app.services import orchestrator_brain as module

    brain, fake = brain_with([{"intent": "CHAT_OR_EXPLAIN", "reason": "ok"}], settings_factory)
    huge = "x" * 50_000
    await brain.classify(
        huge, has_active_task=True, active_instruction=huge, active_summary=huge
    )
    assert len(fake.calls[0]["user"]) < module.MAX_MESSAGE_CHARS + 3000
