"""Task endpoints: create, inspect, cancel and steer coding tasks."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..deps import ContainerDep, CurrentUser
from ..repositories import EventRepository, TaskRepository
from ..schemas import EventOut, TaskCreate, TaskDetailOut, TaskFileOut, TaskOut
from ..services.orchestrator import TaskConflictError

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class SteerRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=32_000)


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    container: ContainerDep,
    _: CurrentUser,
    project_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[TaskOut]:
    async with container.session_factory() as session:
        tasks = await TaskRepository(session).list(project_id=project_id, limit=limit)
        return [TaskOut.model_validate(task) for task in tasks]


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate, container: ContainerDep, _: CurrentUser
) -> TaskOut:
    try:
        task = await container.orchestrator.start_coding_task(
            project_id=payload.project_id, instruction=payload.instruction
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TaskConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return TaskOut.model_validate(task)


@router.get("/{task_id}", response_model=TaskDetailOut)
async def get_task(task_id: str, container: ContainerDep, _: CurrentUser) -> TaskDetailOut:
    async with container.session_factory() as session:
        repo = TaskRepository(session)
        task = await repo.get(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="task not found"
            )
        files = await repo.list_files(task_id)
        # Build from TaskOut so the ``files`` relationship is never lazy-loaded
        # outside the greenlet context (which async SQLAlchemy forbids).
        detail = TaskDetailOut(**TaskOut.model_validate(task).model_dump())
        detail.files = [TaskFileOut.model_validate(item) for item in files]
        return detail


@router.get("/{task_id}/events", response_model=list[EventOut])
async def list_task_events(
    task_id: str,
    container: ContainerDep,
    _: CurrentUser,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[EventOut]:
    async with container.session_factory() as session:
        events = await EventRepository(session).list_for_task(task_id, limit=limit)
        return [EventOut.model_validate(event) for event in events]


@router.post("/{task_id}/cancel", response_model=TaskOut)
async def cancel_task(task_id: str, container: ContainerDep, _: CurrentUser) -> TaskOut:
    task = await container.orchestrator.cancel_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return TaskOut.model_validate(task)


@router.post("/{task_id}/steer", response_model=TaskOut)
async def steer_task(
    task_id: str, payload: SteerRequest, container: ContainerDep, _: CurrentUser
) -> TaskOut:
    ok = await container.orchestrator.steer_task(task_id, payload.instruction)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="task is not active and cannot be steered",
        )
    async with container.session_factory() as session:
        task = await TaskRepository(session).get(task_id)
        if task is None:  # pragma: no cover - raced deletion
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="task not found"
            )
        return TaskOut.model_validate(task)
