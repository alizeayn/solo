"""Orchestration state: Solo's durable, project-scoped working memory.

This is the foundation the later phases build on. Phase 2 uses it to hold the
task queue, the active task, and instructions the user introduced mid-run.
Phases 3–5 add a reasoning model and a voice model that read and write the same
structure — decomposition, prioritisation, dependency ordering, context
retention and "what should go to the coding agent next" are all decisions
expressed as changes to this state, not as new architecture.

It is persisted per project in ``.solo/state/orchestration.json`` so it travels
with the project like everything else in the store.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..domain import PlannedTaskStatus

#: Version of the on-disk orchestration document.
STATE_VERSION = 1
#: Queue bound: a runaway planner must not grow without limit.
MAX_QUEUE = 100
#: Retained mid-run notes.
MAX_NOTES = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PlannedTask:
    """One unit of intended work, before or during execution."""

    title: str
    instruction: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    priority: int = 50
    depends_on: list[str] = field(default_factory=list)
    status: str = PlannedTaskStatus.PENDING.value
    source: str = "user"
    task_id: str | None = None
    note: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "instruction": self.instruction,
            "priority": self.priority,
            "depends_on": list(self.depends_on),
            "status": self.status,
            "source": self.source,
            "task_id": self.task_id,
            "note": self.note,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PlannedTask":
        return cls(
            id=str(raw.get("id") or uuid.uuid4().hex[:12]),
            title=str(raw.get("title") or "Untitled"),
            instruction=str(raw.get("instruction") or ""),
            priority=int(raw.get("priority") or 50),
            depends_on=[str(item) for item in (raw.get("depends_on") or [])],
            status=str(raw.get("status") or PlannedTaskStatus.PENDING.value),
            source=str(raw.get("source") or "user"),
            task_id=raw.get("task_id"),
            note=raw.get("note"),
            created_at=str(raw.get("created_at") or _now()),
            updated_at=str(raw.get("updated_at") or _now()),
        )


@dataclass
class OrchestrationState:
    """The orchestrator's working memory for one project."""

    project_id: str
    version: int = STATE_VERSION
    revision: int = 0
    active_task_id: str | None = None
    active_plan_id: str | None = None
    queue: list[PlannedTask] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str = field(default_factory=_now)

    # ------------------------------------------------------------------ #
    # Serialisation
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "project_id": self.project_id,
            "revision": self.revision,
            "active_task_id": self.active_task_id,
            "active_plan_id": self.active_plan_id,
            "queue": [item.to_dict() for item in self.queue],
            "notes": list(self.notes),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, project_id: str) -> "OrchestrationState":
        return cls(
            project_id=str(raw.get("project_id") or project_id),
            version=int(raw.get("version") or STATE_VERSION),
            revision=int(raw.get("revision") or 0),
            active_task_id=raw.get("active_task_id"),
            active_plan_id=raw.get("active_plan_id"),
            queue=[
                PlannedTask.from_dict(item)
                for item in (raw.get("queue") or [])
                if isinstance(item, dict)
            ],
            notes=[item for item in (raw.get("notes") or []) if isinstance(item, dict)],
            updated_at=str(raw.get("updated_at") or _now()),
        )

    # ------------------------------------------------------------------ #
    # Mutation
    # ------------------------------------------------------------------ #
    def _touch(self) -> None:
        self.revision += 1
        self.updated_at = _now()

    def add(self, planned: PlannedTask) -> PlannedTask:
        """Append a planned task, keeping the queue bounded."""
        if len(self.queue) >= MAX_QUEUE:
            # Drop the lowest-priority pending item rather than the newest.
            pending = [item for item in self.queue if item.status == PlannedTaskStatus.PENDING.value]
            if pending:
                victim = max(pending, key=lambda item: (item.priority, item.created_at))
                self.queue.remove(victim)
        self.queue.append(planned)
        self._touch()
        return planned

    def add_many(self, items: list[PlannedTask]) -> list[PlannedTask]:
        return [self.add(item) for item in items]

    def find(self, plan_id: str) -> PlannedTask | None:
        return next((item for item in self.queue if item.id == plan_id), None)

    def set_status(
        self,
        plan_id: str,
        status: PlannedTaskStatus | str,
        *,
        task_id: str | None = None,
        note: str | None = None,
    ) -> PlannedTask | None:
        item = self.find(plan_id)
        if item is None:
            return None
        item.status = status.value if isinstance(status, PlannedTaskStatus) else str(status)
        if task_id is not None:
            item.task_id = task_id
        if note is not None:
            item.note = note
        item.updated_at = _now()
        self._touch()
        return item

    def set_active(self, task_id: str | None, *, plan_id: str | None = None) -> None:
        self.active_task_id = task_id
        self.active_plan_id = plan_id
        self._touch()

    def next_pending(self) -> PlannedTask | None:
        """Highest-priority pending task whose dependencies are satisfied."""
        done = {item.id for item in self.queue if item.status == PlannedTaskStatus.DONE.value}
        candidates = [
            item
            for item in self.queue
            if item.status == PlannedTaskStatus.PENDING.value
            and all(dep in done for dep in item.depends_on)
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda item: (item.priority, item.created_at))

    def add_note(
        self,
        text: str,
        *,
        task_id: str | None = None,
        kind: str = "instruction",
        applied: str | None = None,
    ) -> dict[str, Any]:
        """Record an instruction received while work was in progress.

        Phases 3–5 use these to decide how a late instruction affects the
        running task; Phase 2 records them so nothing the user said is lost.
        """
        note = {
            "id": uuid.uuid4().hex[:12],
            "text": text.strip(),
            "kind": kind,
            "task_id": task_id,
            "applied": applied,
            "created_at": _now(),
        }
        self.notes.append(note)
        self.notes = self.notes[-MAX_NOTES:]
        self._touch()
        return note

    def pending_notes(self, task_id: str | None = None) -> list[dict[str, Any]]:
        return [
            note
            for note in self.notes
            if note.get("applied") is None and (task_id is None or note.get("task_id") == task_id)
        ]

    def remove(self, plan_id: str) -> bool:
        """Drop a queued item that has not started."""
        item = self.find(plan_id)
        if item is None:
            return False
        self.queue.remove(item)
        self._touch()
        return True

    def clear_finished(self) -> int:
        """Drop completed/skipped entries, keeping the queue readable."""
        before = len(self.queue)
        self.queue = [
            item
            for item in self.queue
            if item.status
            not in {PlannedTaskStatus.DONE.value, PlannedTaskStatus.SKIPPED.value}
        ]
        removed = before - len(self.queue)
        if removed:
            self._touch()
        return removed

    # ------------------------------------------------------------------ #
    # Views
    # ------------------------------------------------------------------ #
    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for item in self.queue:
            counts[item.status] = counts.get(item.status, 0) + 1
        return {
            "version": self.version,
            "project_id": self.project_id,
            "revision": self.revision,
            "active_task_id": self.active_task_id,
            "active_plan_id": self.active_plan_id,
            "queue_size": len(self.queue),
            "status_counts": counts,
            "pending_notes": len(self.pending_notes()),
            "updated_at": self.updated_at,
            "next": (self.next_pending().to_dict() if self.next_pending() else None),
        }
