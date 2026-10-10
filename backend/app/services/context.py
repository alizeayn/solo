"""Bounded context snapshots and the Phase-1 offline answer path.

The snapshot is the *only* project data that may be handed to an LLM or the
voice agent. It is deliberately small and hard-capped: never the whole
repository, never unbounded logs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Project
from ..repositories import EventRepository, TaskRepository
from .project_scan import summarize_project

#: Hard caps so a snapshot can never grow with the repository.
MAX_EVENTS_IN_SNAPSHOT = 12
MAX_SAMPLE_FILES = 20


@dataclass(slots=True)
class ContextSnapshot:
    """A bounded, JSON-serialisable view of the current project/task state."""

    project_id: str
    project_name: str
    file_count: int
    languages: dict[str, int] = field(default_factory=dict)
    sample_files: list[str] = field(default_factory=list)
    active_task: dict | None = None
    recent_activity: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_prompt_text(self) -> str:
        """Compact textual form suitable for an LLM prompt or voice context."""
        lines = [
            f"Project: {self.project_name} ({self.file_count} files)",
        ]
        if self.languages:
            langs = ", ".join(f"{k} {v}" for k, v in self.languages.items())
            lines.append(f"Languages: {langs}")
        if self.active_task:
            lines.append(
                "Active task: "
                f"[{self.active_task.get('status')}] {self.active_task.get('instruction', '')[:200]}"
            )
            if self.active_task.get("progress_summary"):
                lines.append(f"Progress: {self.active_task['progress_summary']}")
        if self.recent_activity:
            lines.append("Recent activity:")
            lines.extend(f"- {item}" for item in self.recent_activity)
        return "\n".join(lines)


async def build_snapshot(
    session: AsyncSession, project: Project, root: Path
) -> ContextSnapshot:
    """Assemble a bounded snapshot from project metadata and recent events."""
    summary = summarize_project(root)

    tasks = TaskRepository(session)
    active = await tasks.find_active(project.id)

    events = EventRepository(session)
    recent = await events.list_recent(project_id=project.id, limit=MAX_EVENTS_IN_SNAPSHOT)

    return ContextSnapshot(
        project_id=project.id,
        project_name=project.name,
        file_count=summary["file_count"],
        languages=summary["languages"],
        sample_files=summary["sample_files"][:MAX_SAMPLE_FILES],
        active_task=(
            {
                "id": active.id,
                "status": active.status,
                "instruction": active.instruction,
                "progress_summary": active.progress_summary,
            }
            if active is not None
            else None
        ),
        recent_activity=[f"{e.type}: {e.message}" for e in recent],
    )


def offline_answer(snapshot: ContextSnapshot, question: str) -> str:
    """Deterministic question answering used until OpenRouter is wired (Phase 3).

    Answers strictly from the bounded snapshot and never invents file contents.
    """
    lowered = question.lower()

    # If the question names a file we have in the sample, acknowledge it.
    for rel in snapshot.sample_files:
        stem = Path(rel).stem.lower()
        if stem and stem in lowered:
            return (
                f"`{rel}` exists in '{snapshot.project_name}'. "
                "I can open it and quote the exact lines once the OpenRouter "
                "context layer is enabled (Phase 3); the file itself is not "
                "included in the bounded snapshot."
            )

    parts = [f"'{snapshot.project_name}' contains {snapshot.file_count} file(s)"]
    if snapshot.languages:
        langs = ", ".join(f"{name} ({count})" for name, count in snapshot.languages.items())
        parts.append(f"detected languages: {langs}")
    answer = "; ".join(parts) + "."

    if snapshot.active_task:
        task = snapshot.active_task
        answer += (
            f" There is an active {task['status'].lower()} task: "
            f"\"{task['instruction'][:160]}\"."
        )
        if task.get("progress_summary"):
            answer += f" Latest progress: {task['progress_summary']}"
    else:
        answer += " No coding task is currently running."

    if snapshot.recent_activity:
        answer += " Most recent activity: " + snapshot.recent_activity[-1] + "."

    return answer
