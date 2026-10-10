"""Event repository: normalised application events + bounded raw logs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import RawLog, TaskEvent


class EventRepository:
    def __init__(self, session: AsyncSession, *, raw_log_max_chars: int = 200_000) -> None:
        self.session = session
        self.raw_log_max_chars = raw_log_max_chars

    async def add(
        self,
        *,
        type: str,  # noqa: A002 - matches the domain vocabulary field name
        message: str,
        task_id: str | None = None,
        project_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> TaskEvent:
        event = TaskEvent(
            task_id=task_id,
            project_id=project_id,
            type=type,
            message=message,
            data=data or {},
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_for_task(self, task_id: str, *, limit: int = 500) -> list[TaskEvent]:
        result = await self.session.execute(
            select(TaskEvent)
            .where(TaskEvent.task_id == task_id)
            .order_by(TaskEvent.created_at.desc(), TaskEvent.id.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def list_recent(
        self, *, project_id: str, limit: int = 100
    ) -> list[TaskEvent]:
        result = await self.session.execute(
            select(TaskEvent)
            .where(TaskEvent.project_id == project_id)
            .order_by(TaskEvent.created_at.desc(), TaskEvent.id.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def add_raw_log(self, *, task_id: str | None, content: str) -> RawLog:
        """Append raw diagnostic output, trimmed to the configured cap."""
        trimmed = content[-self.raw_log_max_chars :]
        record = RawLog(task_id=task_id, content=trimmed)
        self.session.add(record)
        await self.session.flush()
        return record
