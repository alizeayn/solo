"""Milestone endpoints.

Milestones are the Orchestrator's structured reading of a task: which phase is in
progress, what established it, and how it ended. They are deliberately separate
from agent activity — that panel shows what the agent is *doing*, this shows what
it *means*.

The payload is the same structure the voice channel consumes, so a future
ElevenLabs session reads these objects rather than re-deriving progress from raw
events.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query, status

from ..deps import ContainerDep, CurrentUser
from ..repositories import ProjectRepository, TaskRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/milestones", tags=["milestones"])


@router.get("", response_model=list[dict])
async def list_milestones(
    container: ContainerDep,
    _: CurrentUser,
    project_id: str | None = Query(default=None),
) -> list[dict]:
    """Every milestone currently held, optionally for one project."""
    if project_id:
        await _hydrate(container, project_id)
    payload = container.milestones.snapshot()["milestones"]
    if project_id:
        payload = [item for item in payload if item.get("task_id")]
    return payload


@router.get("/task/{task_id}", response_model=list[dict])
async def task_milestones(
    task_id: str, container: ContainerDep, _: CurrentUser
) -> list[dict]:
    """The milestone chain for one task, oldest first."""
    async with container.session_factory() as session:
        task = await TaskRepository(session).get(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="task not found"
        )
    await _hydrate(container, task.project_id)
    return container.milestones.for_task(task_id)


@router.get("/state", response_model=dict)
async def milestone_state(
    container: ContainerDep, _: CurrentUser, project_id: str | None = Query(default=None)
) -> dict:
    """The whole structured snapshot, as persisted for later consumers."""
    if project_id:
        await _hydrate(container, project_id)
    return container.milestones.snapshot()


async def _hydrate(container: ContainerDep, project_id: str) -> None:
    """Load persisted milestones into memory once per project.

    Milestones are mirrored to the project store, so reopening a project — or
    restarting Solo — shows the history rather than an empty panel.
    """
    if container.store is None:
        return
    async with container.session_factory() as session:
        project = await ProjectRepository(session).get(project_id)
    if project is None:
        return
    # The store is synchronous (plain file I/O); keep it off the event loop.
    payload = await asyncio.to_thread(container.store.read_milestones, project)
    if isinstance(payload, dict) and payload.get("milestones"):
        container.milestones.restore(payload)
