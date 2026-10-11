"""Tests for the milestone pipeline.

The properties that matter:

* **evidence-driven** — a milestone appears because a real event occurred, never
  because time passed;
* **activity is not milestones** — the same events feed both, but a milestone only
  appears on a genuine phase change;
* **structure is separate from presentation** — the payload is the same object the
  UI renders and a future voice session will consume.
"""

from __future__ import annotations

import asyncio

import pytest

from app.config import Settings
from app.container import Container
from app.domain import EventType, TaskStatus
from app.services.milestones import (
    MAX_PER_TASK,
    Milestone,
    MilestoneService,
    MilestoneStage,
    MilestoneStatus,
    MilestoneTracker,
)
from app.services.narration import NarrationService, Priority, RecordingTransport

# --------------------------------------------------------------------------- #
# Derivation
# --------------------------------------------------------------------------- #
def test_a_task_is_accepted_into_understanding():
    tracker = MilestoneTracker()
    milestone = tracker.observe(
        "t1",
        event_type=EventType.TASK_CREATED.value,
        message="created",
        instruction="Build a calculator",
    )
    assert milestone is not None
    assert milestone.stage == MilestoneStage.UNDERSTANDING.value
    assert milestone.status == MilestoneStatus.ACTIVE.value
    assert milestone.detail == "Build a calculator"
    assert milestone.evidence == ["task created"]


def test_a_plan_is_evidence_of_planning():
    tracker = MilestoneTracker()
    tracker.observe("t1", event_type=EventType.TASK_CREATED.value, message="created")
    milestone = tracker.observe(
        "t1",
        event_type=EventType.PROGRESS_SUMMARY.value,
        message="Planned 3 steps",
        data={"source": "orchestrator", "steps": 3},
    )
    assert milestone is not None
    assert milestone.stage == MilestoneStage.PLANNING.value
    assert "3 step(s)" in (milestone.detail or "")


def test_a_progress_summary_without_plan_evidence_is_not_a_milestone():
    """Activity must not be promoted to a milestone by accident."""
    tracker = MilestoneTracker()
    tracker.observe("t1", event_type=EventType.TASK_CREATED.value, message="created")
    assert (
        tracker.observe(
            "t1",
            event_type=EventType.PROGRESS_SUMMARY.value,
            message="Pi is running some/model",
            data={"provider": "x"},
        )
        is None
    )


def test_the_first_file_change_opens_implementation_and_closes_the_previous_phase():
    tracker = MilestoneTracker()
    tracker.observe("t1", event_type=EventType.TASK_CREATED.value, message="created")
    tracker.observe(
        "t1",
        event_type=EventType.PROGRESS_SUMMARY.value,
        message="planned",
        data={"source": "orchestrator"},
    )
    milestone = tracker.observe(
        "t1",
        event_type=EventType.FILE_CHANGED.value,
        message="Created calculator.py",
        data={"path": "calculator.py"},
    )
    assert milestone is not None
    assert milestone.stage == MilestoneStage.IMPLEMENTING.value
    assert "calculator.py" in (milestone.detail or "")

    stages = {item.stage: item.status for item in tracker.for_task("t1")}
    assert stages[MilestoneStage.UNDERSTANDING.value] == MilestoneStatus.DONE.value
    assert stages[MilestoneStage.PLANNING.value] == MilestoneStatus.DONE.value
    assert stages[MilestoneStage.IMPLEMENTING.value] == MilestoneStatus.ACTIVE.value


def test_further_file_changes_extend_evidence_without_new_milestones():
    tracker = MilestoneTracker()
    tracker.observe(
        "t1",
        event_type=EventType.FILE_CHANGED.value,
        message="a",
        data={"path": "a.py"},
    )
    assert (
        tracker.observe(
            "t1",
            event_type=EventType.FILE_CHANGED.value,
            message="b",
            data={"path": "b.py"},
        )
        is None
    )
    active = tracker.active("t1")
    assert active is not None
    assert active.stage == MilestoneStage.IMPLEMENTING.value
    assert "b.py" in active.evidence


def test_running_tests_opens_verification():
    tracker = MilestoneTracker()
    tracker.observe(
        "t1", event_type=EventType.FILE_CHANGED.value, message="x", data={"path": "x.py"}
    )
    milestone = tracker.observe(
        "t1",
        event_type=EventType.TEST_RESULT.value,
        message="Tests finished: 3 passed",
        data={},
    )
    assert milestone is not None
    assert milestone.stage == MilestoneStage.VERIFYING.value
    assert "3 passed" in (milestone.detail or "")


def test_a_static_check_also_counts_as_verification():
    tracker = MilestoneTracker()
    milestone = tracker.observe(
        "t1",
        event_type=EventType.CHECK_RESULT.value,
        message="Pyright found no type errors",
        data={},
    )
    assert milestone is not None
    assert milestone.stage == MilestoneStage.VERIFYING.value


def test_an_error_opens_a_failed_blocked_milestone():
    tracker = MilestoneTracker()
    milestone = tracker.observe(
        "t1", event_type=EventType.ERROR.value, message="402 Insufficient credits", data={}
    )
    assert milestone is not None
    assert milestone.stage == MilestoneStage.BLOCKED.value
    assert milestone.status == MilestoneStatus.FAILED.value


def test_completion_closes_the_chain():
    tracker = MilestoneTracker()
    tracker.observe("t1", event_type=EventType.TASK_CREATED.value, message="created")
    milestone = tracker.finish(
        "t1", status=TaskStatus.COMPLETED.value, summary="Done: tests passed"
    )
    assert milestone.stage == MilestoneStage.COMPLETED.value
    assert milestone.status == MilestoneStatus.DONE.value
    assert "tests passed" in (milestone.detail or "")
    assert all(
        item.status != MilestoneStatus.ACTIVE.value for item in tracker.for_task("t1")
    )


def test_cancellation_and_failure_have_their_own_outcomes():
    tracker = MilestoneTracker()
    cancelled = tracker.finish("t1", status=TaskStatus.CANCELLED.value)
    assert cancelled.stage == MilestoneStage.CANCELLED.value

    failed = tracker.finish("t2", status=TaskStatus.FAILED.value, error="boom")
    assert failed.stage == MilestoneStage.BLOCKED.value
    assert failed.status == MilestoneStatus.FAILED.value


def test_unrelated_events_produce_nothing():
    """No timers, no filler: silence when there is no evidence."""
    tracker = MilestoneTracker()
    for event_type in (
        EventType.TOOL_STARTED.value,
        EventType.TOOL_FINISHED.value,
        EventType.RUN_STARTED.value,
        EventType.MESSAGE_RECEIVED.value,
        EventType.ASSISTANT_MESSAGE.value,
    ):
        assert tracker.observe("t1", event_type=event_type, message="noise") is None
    assert tracker.for_task("t1") == []


def test_the_milestone_history_is_bounded():
    tracker = MilestoneTracker()
    for index in range(MAX_PER_TASK + 20):
        tracker._open(  # noqa: SLF001 - exercising the bound directly
            "t1",
            MilestoneStage.IMPLEMENTING,
            detail=f"step {index}",
            evidence=[f"e{index}"],
        )
    assert len(tracker.for_task("t1")) <= MAX_PER_TASK


def test_sequence_numbers_are_monotonic():
    tracker = MilestoneTracker()
    tracker.observe("t1", event_type=EventType.TASK_CREATED.value, message="c")
    tracker.observe(
        "t1", event_type=EventType.FILE_CHANGED.value, message="f", data={"path": "f.py"}
    )
    sequences = [item.sequence for item in tracker.for_task("t1")]
    assert sequences == sorted(sequences)
    assert len(set(sequences)) == len(sequences)


# --------------------------------------------------------------------------- #
# Service: wording, broadcast, narration, persistence
# --------------------------------------------------------------------------- #
class _Bus:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def publish(self, message: dict) -> None:
        self.messages.append(message)


async def test_a_milestone_is_published_and_narrated():
    bus = _Bus()
    transport = RecordingTransport()
    narration = NarrationService(transport=transport, min_interval=0)
    service = MilestoneService(bus=bus, narration=narration)
    # The narration worker delivers queued lines; without it nothing is spoken.
    await narration.start()
    await service.observe(
        task_id="t1",
        project_id="p1",
        event_type=EventType.TASK_CREATED.value,
        message="created",
        instruction="Build a calculator",
    )
    await asyncio.sleep(0.03)

    assert bus.messages and bus.messages[0]["channel"] == "milestone"
    assert bus.messages[0]["payload"]["project_id"] == "p1"
    # The voice channel consumes the same structured object.
    assert transport.lines, "a milestone should reach the narration channel"
    assert "Understanding the request" in transport.lines[0].text
    await narration.stop()


async def test_an_error_milestone_is_narrated_as_critical():
    transport = RecordingTransport()
    narration = NarrationService(transport=transport, min_interval=0)
    service = MilestoneService(narration=narration)
    await narration.start()

    await service.observe(
        task_id="t1",
        event_type=EventType.ERROR.value,
        message="provider failed",
    )
    await asyncio.sleep(0.03)
    assert transport.lines
    assert transport.lines[0].priority == int(Priority.CRITICAL)
    await narration.stop()


async def test_the_model_may_reword_but_a_failure_falls_back(settings_factory):
    class WorkingBrain:
        async def describe_milestone(self, **_kwargs):
            return "Reading the request and locating the relevant files."

    class BrokenBrain:
        async def describe_milestone(self, **_kwargs):
            raise RuntimeError("no credits")

    good = MilestoneService(brain=WorkingBrain())
    payload = await good.observe(
        task_id="t1", event_type=EventType.TASK_CREATED.value, message="c"
    )
    assert payload is not None
    assert payload["worded_by"] == "orchestrator-model"
    assert payload["detail"].startswith("Reading the request")

    broken = MilestoneService(brain=BrokenBrain())
    payload = await broken.observe(
        task_id="t2", event_type=EventType.TASK_CREATED.value, message="c"
    )
    assert payload is not None
    # Deterministic wording survives; the pipeline is the same shape either way.
    assert payload["worded_by"] == "evidence"


async def test_the_model_cannot_invent_a_milestone():
    """Wording is offered only for a transition the evidence already justified."""

    class EagerBrain:
        called = 0

        async def describe_milestone(self, **_kwargs):
            EagerBrain.called += 1
            return "Making great progress!"

    service = MilestoneService(brain=EagerBrain())
    assert (
        await service.observe(
            task_id="t1", event_type=EventType.TOOL_STARTED.value, message="noise"
        )
        is None
    )
    assert EagerBrain.called == 0


def test_snapshot_and_restore_round_trip():
    source = MilestoneService()
    tracker = source.tracker
    tracker.observe("t1", event_type=EventType.TASK_CREATED.value, message="c")
    tracker.observe(
        "t1", event_type=EventType.FILE_CHANGED.value, message="f", data={"path": "f.py"}
    )
    snapshot = source.snapshot()
    assert len(snapshot["milestones"]) == 2

    restored = MilestoneService()
    restored.restore(snapshot)
    assert [item["stage"] for item in restored.for_task("t1")] == [
        MilestoneStage.UNDERSTANDING.value,
        MilestoneStage.IMPLEMENTING.value,
    ]


def test_restore_ignores_malformed_payloads():
    service = MilestoneService()
    service.restore({"milestones": [None, "nonsense", {"stage": "implementing"}]})
    # Only the dict with a task id is adopted; nothing raises.
    assert service.snapshot()["milestones"] == []


def test_milestone_serialisation_is_stable():
    milestone = Milestone(
        task_id="t1",
        stage=MilestoneStage.IMPLEMENTING.value,
        title="Making the changes",
        evidence=["file changed: a.py"],
    )
    payload = milestone.to_dict()
    assert set(payload) >= {
        "id",
        "task_id",
        "stage",
        "title",
        "detail",
        "status",
        "evidence",
        "sequence",
        "created_at",
        "updated_at",
        "worded_by",
    }
    assert Milestone.from_dict(payload).stage == MilestoneStage.IMPLEMENTING.value


# --------------------------------------------------------------------------- #
# Integration: a real task produces a milestone chain, and it persists
# --------------------------------------------------------------------------- #
@pytest.fixture
async def container(settings_factory):
    instance = await Container.create(settings_factory())
    try:
        yield instance
    finally:
        await instance.close()


async def test_a_coding_task_produces_a_milestone_chain(container):
    project = await container.projects.create("milestones-demo")
    task = await container.orchestrator.start_coding_task(
        project_id=project.id, instruction="Write a simple Python calculator"
    )
    for _ in range(300):
        async with container.session_factory() as session:
            from app.repositories import TaskRepository

            current = await TaskRepository(session).get(task.id)
        if current is not None and current.status in {"COMPLETED", "FAILED", "CANCELLED"}:
            break
        await asyncio.sleep(0.02)

    # Give the background task time to finish _set_status (which includes milestone finish)
    # after the DB commit that the loop observes. When running with other tests,
    # the event loop may be busier, so poll for the COMPLETED milestone.
    for _ in range(50):
        milestones = container.milestones.tracker.for_task(task.id)
        if milestones and milestones[-1].stage == MilestoneStage.COMPLETED.value:
            break
        await asyncio.sleep(0.02)
    else:
        milestones = container.milestones.tracker.for_task(task.id)
    assert milestones, "a completed task must have produced milestones"
    stages = [item.stage for item in milestones]
    assert stages[0] == MilestoneStage.UNDERSTANDING.value
    assert MilestoneStage.IMPLEMENTING.value in stages
    assert stages[-1] == MilestoneStage.COMPLETED.value
    assert all(item.evidence for item in milestones), "every milestone cites evidence"


async def test_milestones_are_persisted_to_the_project_store(container):
    project = await container.projects.create("persist-demo")
    task = await container.orchestrator.start_coding_task(
        project_id=project.id, instruction="Write a calculator"
    )
    for _ in range(300):
        async with container.session_factory() as session:
            from app.repositories import TaskRepository

            current = await TaskRepository(session).get(task.id)
        if current is not None and current.status in {"COMPLETED", "FAILED"}:
            break
        await asyncio.sleep(0.02)

    paths = container.store.paths(project)
    assert paths.milestones.is_file(), "milestones were not written to .solo/state"

    # A fresh service can read them back — this is what survives a restart.
    import json

    payload = json.loads(paths.milestones.read_text())
    assert payload["milestones"], "the persisted snapshot is empty"
    restored = MilestoneService()
    restored.restore(payload)
    assert [m["stage"] for m in restored.for_task(task.id)][0] == (
        MilestoneStage.UNDERSTANDING.value
    )


# --------------------------------------------------------------------------- #
# API layer — the defect was here, not in the tracker
# --------------------------------------------------------------------------- #
def test_milestone_endpoints_serve_a_completed_task(authed, wait_for_terminal):
    """Regression: the endpoints awaited a synchronous store read.

    The tracker and the WebSocket stream were both correct, so the task completed
    and milestones were published — but every REST call returned 500 because
    ``_hydrate`` awaited plain file I/O. The bug was invisible to service-level
    tests, which is exactly why this one goes through HTTP.
    """
    project = authed.post("/api/projects", json={"name": "api-milestones"}).json()
    task = authed.post(
        "/api/tasks",
        json={"project_id": project["id"], "instruction": "add a health endpoint"},
    ).json()
    wait_for_terminal(authed, task["id"])

    listed = authed.get(f"/api/milestones/task/{task['id']}")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body, "the endpoint returned no milestones for a completed task"
    assert body[0]["stage"] == MilestoneStage.UNDERSTANDING.value
    assert body[-1]["stage"] == MilestoneStage.COMPLETED.value
    assert all(item["evidence"] for item in body)

    # The same shape is exposed collection-wide and as a snapshot.
    assert authed.get("/api/milestones").status_code == 200
    snapshot = authed.get("/api/milestones/state")
    assert snapshot.status_code == 200
    assert snapshot.json()["version"] == 1


def test_milestones_for_an_unknown_task_are_a_clean_404(authed):
    response = authed.get("/api/milestones/task/does-not-exist")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_events_arriving_after_completion_do_not_reopen_the_chain():
    """Regression: a trailing event must not overwrite the outcome.

    The terminal transition and the last verification event are not ordered
    relative to each other, so a late `test.result` used to open a fresh
    `verifying` milestone after `finish()`. The chain then ended on the wrong
    stage and the panel showed work still in progress for a finished task.
    """
    tracker = MilestoneTracker()
    tracker.observe("t1", event_type=EventType.TASK_CREATED.value, message="created")
    tracker.finish("t1", status=TaskStatus.COMPLETED.value, summary="Done.")

    # Anything that arrives afterwards is ignored.
    assert (
        tracker.observe(
            "t1", event_type=EventType.TEST_RESULT.value, message="3 passed"
        )
        is None
    )
    assert (
        tracker.observe("t1", event_type=EventType.FILE_CHANGED.value, message="x")
        is None
    )
    assert (
        tracker.observe("t1", event_type=EventType.ERROR.value, message="late error")
        is None
    )

    chain = tracker.for_task("t1")
    assert chain[-1].stage == MilestoneStage.COMPLETED.value
    assert all(item.status != MilestoneStatus.ACTIVE.value for item in chain)


def test_a_completed_chain_stays_closed_after_a_reload():
    source = MilestoneTracker()
    source.observe("t1", event_type=EventType.TASK_CREATED.value, message="created")
    source.finish("t1", status=TaskStatus.COMPLETED.value, summary="Done.")

    restored = MilestoneTracker()
    restored.hydrate("t1", source.for_task("t1"))
    assert (
        restored.observe("t1", event_type=EventType.TEST_RESULT.value, message="late")
        is None
    )
    assert restored.for_task("t1")[-1].stage == MilestoneStage.COMPLETED.value


def test_a_mid_run_failure_may_still_be_followed_by_recovery():
    """`blocked` is not terminal: a task can fail a check and carry on."""
    tracker = MilestoneTracker()
    tracker.observe("t1", event_type=EventType.ERROR.value, message="check failed")
    recovered = tracker.observe(
        "t1",
        event_type=EventType.TEST_RESULT.value,
        message="passing after a fix",
    )
    assert recovered is not None
    assert recovered.stage == MilestoneStage.VERIFYING.value


def test_repeated_errors_produce_one_blocked_milestone():
    """Regression: a single bad run emitted the same obstacle three times.

    One provider failure produces several `error` events — the provider's own
    error, the agent giving up, the task settling — and each opened another
    `blocked` entry, so the panel repeated the same problem. Repeated errors now
    extend the existing milestone's evidence.
    """
    tracker = MilestoneTracker()
    tracker.observe("t1", event_type=EventType.TASK_CREATED.value, message="created")

    first = tracker.observe(
        "t1", event_type=EventType.ERROR.value, message="403 subscription required"
    )
    assert first is not None and first.stage == MilestoneStage.BLOCKED.value

    for _ in range(2):
        assert (
            tracker.observe(
                "t1", event_type=EventType.ERROR.value, message="403 subscription required"
            )
            is None
        )

    chain = tracker.for_task("t1")
    assert [item.stage for item in chain] == [
        MilestoneStage.UNDERSTANDING.value,
        MilestoneStage.BLOCKED.value,
    ]
    # The repeated message is not duplicated in the evidence either.
    assert len(chain[-1].evidence) == len(set(chain[-1].evidence))

    # A different, later failure is still recorded as its own evidence.
    assert (
        tracker.observe("t1", event_type=EventType.ERROR.value, message="timeout")
        is None
    )
    assert "timeout" in tracker.for_task("t1")[-1].evidence
