"""Conversation message endpoints (send + history).

Sending a message routes it through the orchestrator, which decides between
answering, steering, cancelling and starting a task.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from ..deps import ContainerDep, CurrentUser
from ..repositories import ConversationRepository, ProjectRepository
from ..schemas import MessageCreate, MessageDispatchResult, MessageOut

router = APIRouter(prefix="/api/projects/{project_id}/messages", tags=["messages"])


@router.get("", response_model=list[MessageOut])
async def list_messages(
    project_id: str,
    container: ContainerDep,
    _: CurrentUser,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[MessageOut]:
    async with container.session_factory() as session:
        project = await ProjectRepository(session).get(project_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
            )
        conversations = ConversationRepository(session)
        record = await conversations.get_or_create_for_project(project_id)
        messages = await conversations.list_messages(record.id, limit=limit)
        await session.commit()
        return [MessageOut.model_validate(message) for message in messages]


@router.post("", response_model=MessageDispatchResult, status_code=status.HTTP_201_CREATED)
async def send_message(
    project_id: str,
    payload: MessageCreate,
    container: ContainerDep,
    _: CurrentUser,
) -> MessageDispatchResult:
    try:
        result = await container.orchestrator.handle_user_message(
            project_id=project_id,
            content=payload.content,
            conversation_id=payload.conversation_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MessageDispatchResult(**result)
