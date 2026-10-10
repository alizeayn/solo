"""Conversation and message repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Conversation, Message


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, conversation_id: str) -> Conversation | None:
        return await self.session.get(Conversation, conversation_id)

    async def get_or_create_for_project(self, project_id: str) -> Conversation:
        """Return the project's single MVP conversation, creating it if needed."""
        result = await self.session.execute(
            select(Conversation)
            .where(Conversation.project_id == project_id)
            .order_by(Conversation.created_at)
            .limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        conversation = Conversation(project_id=project_id)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def add_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        task_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            task_id=task_id,
            meta=meta or {},
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_messages(
        self, conversation_id: str, *, limit: int = 200
    ) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))
