"""Milestones: the Orchestrator's structured interpretation of a task.

**Activity and milestones answer different questions.** The Activity panel shows
what the agent is *doing* — tool calls, files, commands. Milestones show what that
means: which phase of the task is in progress, what has been established, and what
happened in the end. The two are fed from the same events but are not the same
thing, and the frontend must not have to infer one from the other.

Two rules shape this module:

* **Every milestone is derived from evidence.** A transition happens because a real
  event occurred — a task was accepted, a file changed, tests ran, a check
  finished, an error arrived. There are no timers and no invented progress, so a
  stalled task produces nothing rather than a reassuring animation.
* **Structure is separate from presentation.** A milestone carries its stage,
  status and the evidence that justified it. The UI renders it; the voice channel
  consumes the same object. Neither re-derives it.

The optional OpenRouter model only *words* a transition the evidence already
justified; it can never create one. With no model, deterministic text is used, so
the pipeline is identical in shape either way.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ..domain import EventType, TaskStatus
from .narration import Priority

logger = logging.getLogger(__name__)

#: Retained milestones per task, and tasks per project.
MAX_PER_TASK = 40
MAX_TASKS = 50


class MilestoneStage(str, Enum):
    """The phase of a task. Ordered as a task normally progresses."""

    UNDERSTANDING = "understanding"
    PLANNING = "planning"
    IMPLEMENTING = "implementing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class MilestoneStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"


#: Stages that end a task rather than continuing it.
TERMINAL_STAGES = frozenset(
    {MilestoneStage.COMPLETED, MilestoneStage.BLOCKED, MilestoneStage.CANCELLED}
)

_TITLES: dict[MilestoneStage, str] = {
    MilestoneStage.UNDERSTANDING: "Understanding the request",
    MilestoneStage.PLANNING: "Planning the implementation",
    MilestoneStage.IMPLEMENTING: "Making the changes",
    MilestoneStage.VERIFYING: "Checking the result",
    MilestoneStage.COMPLETED: "Task complete",
    MilestoneStage.BLOCKED: "Blocked",
    MilestoneStage.CANCELLED: "Task cancelled",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip(text: str | None, limit: int = 200) -> str | None:
    if not text:
        return None
    cleaned = " ".join(str(text).split())
    if not cleaned:
        return None
    return cleaned if len(cleaned) <= limit else f"{cleaned[: limit - 1].rstrip()}…"


@dataclass
class Milestone:
    task_id: str
    stage: str
    title: str
    status: str = MilestoneStatus.ACTIVE.value
    detail: str | None = None
    #: The concrete events that justified this milestone. Shown in the UI and
    #: available to any other consumer, so a milestone can always be explained.
    evidence: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    sequence: int = 0
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    #: ``orchestrator-model`` when the wording came from OpenRouter, ``evidence``
    #: when it was derived deterministically.
    worded_by: str = "evidence"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "stage": self.stage,
            "title": self.title,
            "detail": self.detail,
            "status": self.status,
            "evidence": list(self.evidence),
            "sequence": self.sequence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "worded_by": self.worded_by,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Milestone":
        return cls(
            id=str(raw.get("id") or uuid.uuid4().hex[:12]),
            task_id=str(raw.get("task_id") or ""),
            stage=str(raw.get("stage") or MilestoneStage.UNDERSTANDING.value),
            title=str(raw.get("title") or ""),
            detail=raw.get("detail"),
            status=str(raw.get("status") or MilestoneStatus.ACTIVE.value),
            evidence=[str(item) for item in (raw.get("evidence") or [])],
            sequence=int(raw.get("sequence") or 0),
            created_at=str(raw.get("created_at") or _now()),
            updated_at=str(raw.get("updated_at") or _now()),
            worded_by=str(raw.get("worded_by") or "evidence"),
        )


class MilestoneTracker:
    """Derives milestones from normalised events. Pure and synchronous.

    Kept free of I/O so the transition rules — which are the interesting part —
    can be tested directly, without a database, a bus or a model.
    """

    def __init__(self) -> None:
        self._by_task: dict[str, list[Milestone]] = {}
        self._sequence = 0
        # Tasks whose chain has been closed by `finish`. Kept separately from
        # the milestone list because "is this task over" is a different question
        # from "what milestones does it have".
        self._closed: set[str] = set()

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    def for_task(self, task_id: str) -> list[Milestone]:
        return list(self._by_task.get(task_id, []))

    def all(self) -> list[dict[str, Any]]:
        return [
            milestone.to_dict()
            for milestones in self._by_task.values()
            for milestone in milestones
        ]

    def active(self, task_id: str) -> Milestone | None:
        for milestone in reversed(self._by_task.get(task_id, [])):
            if milestone.status == MilestoneStatus.ACTIVE.value:
                return milestone
        return None

    def hydrate(self, task_id: str, milestones: list[Milestone]) -> None:
        """Adopt milestones loaded from the project store."""
        self._by_task[task_id] = milestones[-MAX_PER_TASK:]
        for milestone in milestones:
            self._sequence = max(self._sequence, milestone.sequence)
        # A chain that ended in a terminal stage stays closed after a reload.
        # Only `completed`/`cancelled` are treated as authoritative here: a
        # `blocked` milestone can be opened by a mid-run error that the agent
        # later recovers from.
        if milestones and milestones[-1].stage in {
            MilestoneStage.COMPLETED.value,
            MilestoneStage.CANCELLED.value,
        }:
            self._closed.add(task_id)

    # ------------------------------------------------------------------ #
    # Transitions
    # ------------------------------------------------------------------ #
    def _open(
        self,
        task_id: str,
        stage: MilestoneStage,
        *,
        detail: str | None,
        evidence: list[str],
        status: MilestoneStatus = MilestoneStatus.ACTIVE,
    ) -> Milestone:
        # Close whatever was active: a task is in one phase at a time.
        existing = self._by_task.setdefault(task_id, [])
        for milestone in existing:
            if milestone.status == MilestoneStatus.ACTIVE.value:
                milestone.status = MilestoneStatus.DONE.value
                milestone.updated_at = _now()

        self._sequence += 1
        milestone = Milestone(
            task_id=task_id,
            stage=stage.value,
            title=_TITLES[stage],
            status=status.value,
            detail=_clip(detail),
            evidence=[item for item in evidence if item][:6],
            sequence=self._sequence,
        )
        existing.append(milestone)
        del existing[:-MAX_PER_TASK]

        # Bound the number of tasks retained.
        if len(self._by_task) > MAX_TASKS:
            oldest = min(
                self._by_task,
                key=lambda key: self._by_task[key][-1].sequence
                if self._by_task[key]
                else 0,
            )
            if oldest != task_id:
                self._by_task.pop(oldest, None)
        return milestone

    def observe(
        self,
        task_id: str,
        *,
        event_type: str,
        message: str,
        data: dict[str, Any] | None = None,
        instruction: str | None = None,
    ) -> Milestone | None:
        """Return a new milestone when the evidence justifies one.

        Returning ``None`` is the common case: most events are activity, not a
        phase change.
        """
        data = data or {}
        # A finished task accepts no further milestones. Runtime events can
        # still arrive after the terminal transition — a final check result, a
        # trailing tool event — and without this guard they would reopen a chain
        # that has already been closed, so the last milestone would no longer be
        # the outcome.
        if task_id in self._closed:
            return None
        existing = self._by_task.get(task_id, [])
        stages_seen = {milestone.stage for milestone in existing}

        # --- a task was accepted --------------------------------------- #
        if event_type == EventType.TASK_CREATED.value:
            return self._open(
                task_id,
                MilestoneStage.UNDERSTANDING,
                detail=instruction or message,
                evidence=["task created"],
            )

        # --- the orchestrator produced a plan --------------------------- #
        if event_type == EventType.PROGRESS_SUMMARY.value and (
            data.get("plan_id") or data.get("source") == "orchestrator"
        ):
            detail = message
            if data.get("steps"):
                detail = f"{data['steps']} step(s): {message}"
            return self._open(
                task_id,
                MilestoneStage.PLANNING,
                detail=detail,
                evidence=[message],
            )

        # --- something was actually written ----------------------------- #
        if event_type == EventType.FILE_CHANGED.value:
            path = _clip(str(data.get("path") or ""), 120) or "a file"
            if MilestoneStage.IMPLEMENTING.value not in stages_seen:
                return self._open(
                    task_id,
                    MilestoneStage.IMPLEMENTING,
                    detail=f"First change: {path}",
                    evidence=[f"file changed: {path}"],
                )
            # Already implementing: extend the active milestone's evidence
            # rather than emitting a milestone per file.
            active = self.active(task_id)
            if active is not None and active.stage == MilestoneStage.IMPLEMENTING.value:
                note = _clip(path, 120)
                if note and note not in active.evidence:
                    active.evidence.append(note)
                    active.evidence = active.evidence[-6:]
                    active.updated_at = _now()
            return None

        # --- verification evidence -------------------------------------- #
        if event_type in {
            EventType.TEST_RESULT.value,
            EventType.CHECK_RESULT.value,
        }:
            if MilestoneStage.VERIFYING.value not in stages_seen:
                return self._open(
                    task_id,
                    MilestoneStage.VERIFYING,
                    detail=message,
                    evidence=[message],
                )
            active = self.active(task_id)
            if active is not None and active.stage == MilestoneStage.VERIFYING.value:
                active.detail = _clip(message)
                active.evidence = [*active.evidence[-5:], _clip(message, 160) or message]
                active.updated_at = _now()
            return None

        # --- a failure --------------------------------------------------- #
        if event_type == EventType.ERROR.value:
            # One failure, one milestone. A single bad run produces several error
            # events (the provider error, the agent giving up, the task settling),
            # and each used to open another `blocked` entry — so the panel showed
            # the same obstacle three times. Repeated errors extend the existing
            # milestone's evidence instead.
            last = existing[-1] if existing else None
            if last is not None and last.stage == MilestoneStage.BLOCKED.value:
                note = _clip(message, 160)
                if note and note not in last.evidence:
                    last.evidence = [*last.evidence[-5:], note]
                    last.detail = _clip(message) or last.detail
                    last.updated_at = _now()
                return None
            return self._open(
                task_id,
                MilestoneStage.BLOCKED,
                detail=message,
                evidence=[message],
                status=MilestoneStatus.FAILED,
            )

        return None

    def finish(
        self,
        task_id: str,
        *,
        status: str,
        summary: str | None = None,
        error: str | None = None,
    ) -> Milestone:
        """Close a task with a terminal milestone."""
        try:
            task_status = TaskStatus(status)
        except ValueError:
            task_status = TaskStatus.FAILED

        if task_status is TaskStatus.COMPLETED:
            stage = MilestoneStage.COMPLETED
            state = MilestoneStatus.DONE
            detail = summary
            evidence = ["run finished", "task completed"]
        elif task_status is TaskStatus.CANCELLED:
            stage = MilestoneStage.CANCELLED
            state = MilestoneStatus.DONE
            detail = summary or "Cancelled by the user."
            evidence = ["task cancelled"]
        else:
            stage = MilestoneStage.BLOCKED
            state = MilestoneStatus.FAILED
            detail = error or summary or "The task failed."
            evidence = [("error: " + (error or "unknown"))[:200]]

        # Close the chain before recording the terminal milestone: `observe`
        # refuses anything that arrives afterwards.
        self._closed.add(task_id)
        return self._open(
            task_id, stage, detail=detail, evidence=evidence, status=state
        )


class MilestoneService:
    """Owns milestones: derivation, optional wording, persistence, broadcast."""

    def __init__(
        self,
        *,
        tracker: MilestoneTracker | None = None,
        bus: Any | None = None,
        brain: Any | None = None,
        narration: Any | None = None,
    ) -> None:
        self._tracker = tracker or MilestoneTracker()
        self._bus = bus
        self._brain = brain
        self._narration = narration

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    def for_task(self, task_id: str) -> list[dict[str, Any]]:
        return [milestone.to_dict() for milestone in self._tracker.for_task(task_id)]

    @property
    def tracker(self) -> MilestoneTracker:
        return self._tracker

    def snapshot(self) -> dict[str, Any]:
        """Structured state for persistence and for other consumers (voice)."""
        return {"version": 1, "updated_at": _now(), "milestones": self._tracker.all()}

    def restore(self, payload: dict[str, Any]) -> None:
        grouped: dict[str, list[Milestone]] = {}
        for raw in payload.get("milestones") or []:
            if not isinstance(raw, dict):
                continue
            milestone = Milestone.from_dict(raw)
            if milestone.task_id:
                grouped.setdefault(milestone.task_id, []).append(milestone)
        for task_id, milestones in grouped.items():
            milestones.sort(key=lambda item: item.sequence)
            self._tracker.hydrate(task_id, milestones)

    # ------------------------------------------------------------------ #
    # Observation
    # ------------------------------------------------------------------ #
    async def observe(
        self,
        *,
        task_id: str,
        project_id: str | None = None,
        event_type: str,
        message: str,
        data: dict[str, Any] | None = None,
        instruction: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            milestone = self._tracker.observe(
                task_id,
                event_type=event_type,
                message=message,
                data=data,
                instruction=instruction,
            )
        except Exception:  # noqa: BLE001 - milestones must never break a task
            logger.warning("milestone derivation failed", exc_info=True)
            return None
        if milestone is None:
            return None

        await self._word(milestone, instruction=instruction)
        payload = {**milestone.to_dict(), "project_id": project_id}
        await self._publish(payload)
        await self._narrate(milestone)
        return payload

    async def finish(
        self,
        *,
        task_id: str,
        project_id: str | None = None,
        status: str,
        summary: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        try:
            milestone = self._tracker.finish(
                task_id, status=status, summary=summary, error=error
            )
        except Exception:  # noqa: BLE001
            logger.warning("milestone completion failed", exc_info=True)
            return None
        payload = {**milestone.to_dict(), "project_id": project_id}
        await self._publish(payload)
        await self._narrate(milestone, important=True)
        return payload

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    async def _word(self, milestone: Milestone, *, instruction: str | None) -> None:
        """Let the Orchestrator model phrase a transition the evidence justified.

        The model may only reword: the stage, status and evidence are already
        decided, and a failure or an absent key leaves the deterministic text.
        """
        if self._brain is None or milestone.status != MilestoneStatus.ACTIVE.value:
            return
        describe = getattr(self._brain, "describe_milestone", None)
        if not callable(describe):
            return
        try:
            detail = await describe(
                stage=milestone.stage,
                title=milestone.title,
                evidence=milestone.evidence,
                instruction=instruction,
            )
        except Exception:  # noqa: BLE001
            logger.debug("milestone wording failed", exc_info=True)
            return
        if isinstance(detail, str) and detail.strip():
            milestone.detail = _clip(detail.strip(), 240)
            milestone.worded_by = "orchestrator-model"

    async def _publish(self, payload: dict[str, Any]) -> None:
        if self._bus is None:
            return
        try:
            await self._bus.publish({"channel": "milestone", "payload": payload})
        except Exception:  # noqa: BLE001
            logger.debug("could not publish a milestone", exc_info=True)

    async def _narrate(self, milestone: Milestone, *, important: bool = False) -> None:
        """Milestones are the voice channel's unit of speech.

        This is the link the ElevenLabs integration will rely on: it consumes
        *structured milestones*, not raw agent activity.
        """
        if self._narration is None:
            return
        text = milestone.detail or milestone.title
        if milestone.stage == MilestoneStage.IMPLEMENTING.value and milestone.evidence:
            text = f"{milestone.title}: {', '.join(milestone.evidence[:2])}"
        priority = (
            Priority.CRITICAL
            if milestone.status == MilestoneStatus.FAILED.value
            else Priority.IMPORTANT
            if important or milestone.stage in {s.value for s in TERMINAL_STAGES}
            else Priority.PROGRESS
        )
        try:
            await self._narration.announce(
                f"{milestone.title}. {text}" if text != milestone.title else milestone.title,
                kind="milestone",
                priority=int(priority),
                task_id=milestone.task_id,
            )
        except Exception:  # noqa: BLE001
            logger.debug("could not narrate a milestone", exc_info=True)
