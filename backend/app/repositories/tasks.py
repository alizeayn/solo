"""Task repository."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain import ACTIVE_STATUSES, TERMINAL_STATUSES, TaskStatus
from ..models import Task, TaskFile


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, task_id: str) -> Task | None:
        return await self.session.get(Task, task_id)

    async def create(
        self,
        *,
        project_id: str,
        instruction: str,
        task_type: str,
        conversation_id: str | None = None,
        parent_task_id: str | None = None,
        status: TaskStatus = TaskStatus.QUEUED,
    ) -> Task:
        task = Task(
            project_id=project_id,
            conversation_id=conversation_id,
            parent_task_id=parent_task_id,
            task_type=task_type,
            status=status.value,
            instruction=instruction,
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def list(
        self, *, project_id: str | None = None, limit: int = 100
    ) -> list[Task]:
        stmt = select(Task).order_by(Task.created_at.desc()).limit(limit)
        if project_id is not None:
            stmt = stmt.where(Task.project_id == project_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_active(self, project_id: str) -> Task | None:
        """Return the current active modifying task for a project, if any."""
        stmt = (
            select(Task)
            .where(Task.project_id == project_id)
            .where(Task.status.in_([s.value for s in ACTIVE_STATUSES]))
            .order_by(Task.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(
        self,
        task: Task,
        *,
        status: TaskStatus | None = None,
        progress_summary: str | None = None,
        result_summary: str | None = None,
        error: str | None = None,
        agent_session_ref: str | None = None,
    ) -> Task:
        """Apply a partial update, stamping ``completed_at`` for terminal states."""
        if status is not None:
            task.status = status.value
            if status in TERMINAL_STATUSES:
                task.completed_at = datetime.now(timezone.utc)
        if progress_summary is not None:
            task.progress_summary = progress_summary
        if result_summary is not None:
            task.result_summary = result_summary
        if error is not None:
            task.error = error
        if agent_session_ref is not None:
            task.agent_session_ref = agent_session_ref
        task.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return task

    async def add_file(
        self, *, task_id: str, path: str, change_type: str = "modified"
    ) -> TaskFile:
        """Record a changed file, de-duplicating on (task, path)."""
        result = await self.session.execute(
            select(TaskFile).where(
                TaskFile.task_id == task_id, TaskFile.path == path
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.change_type = change_type
            await self.session.flush()
            return existing
        record = TaskFile(task_id=task_id, path=path, change_type=change_type)
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_files(self, task_id: str) -> list[TaskFile]:
        result = await self.session.execute(
            select(TaskFile)
            .where(TaskFile.task_id == task_id)
            .order_by(TaskFile.created_at)
        )
        return list(result.scalars().all())

    async def mark_in_flight_for_recovery(self) -> int:
        """Mark non-terminal tasks as ``RECOVERY_REQUIRED`` after a restart.

        Called once at startup: any task that was running when the process died
        is unknown, so we never assume it completed.
        """
        stmt = select(Task).where(Task.status.in_([s.value for s in ACTIVE_STATUSES]))
        result = await self.session.execute(stmt)
        tasks = list(result.scalars().all())
        for task in tasks:
            task.status = TaskStatus.RECOVERY_REQUIRED.value
            task.error = "Application restarted while this task was in flight."
            task.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return len(tasks)
