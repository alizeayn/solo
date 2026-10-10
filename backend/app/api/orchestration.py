"""Project-scoped orchestration state and static checks.

These endpoints expose the orchestrator's working memory (queue, priority,
dependencies, mid-run notes) and let the workspace run Pyright over the project
on demand. Mutations go through the orchestrator so the persisted state and the
broadcast view stay in step.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from ..deps import ContainerDep, CurrentUser
from ..domain import PlannedTaskStatus
from ..schemas import (
    CheckResultOut,
    ChecksStatusOut,
    OrchestrationPlanIn,
    OrchestrationStateOut,
)
from ..services.project_paths import ProjectPathError, resolve_project_root

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["orchestration"])


@router.get("/checks/status", response_model=ChecksStatusOut)
async def checks_status(container: ContainerDep, _: CurrentUser) -> ChecksStatusOut:
    return ChecksStatusOut.model_validate(container.checks.status())


@router.get(
    "/projects/{project_id}/orchestration", response_model=OrchestrationStateOut
)
async def get_orchestration(
    project_id: str, container: ContainerDep, _: CurrentUser
) -> OrchestrationStateOut:
    try:
        payload = await container.orchestrator.orchestration_state(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return OrchestrationStateOut.model_validate(payload)


@router.post(
    "/projects/{project_id}/orchestration/plan",
    response_model=OrchestrationStateOut,
)
async def plan_instruction(
    project_id: str,
    payload: OrchestrationPlanIn,
    container: ContainerDep,
    _: CurrentUser,
) -> OrchestrationStateOut:
    """Ask the Orchestrator model to decompose an instruction into a plan."""
    try:
        await container.orchestrator.plan_instruction(
            project_id=project_id, content=payload.instruction
        )
        result = await container.orchestrator.orchestration_state(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return OrchestrationStateOut.model_validate(result)


@router.post(
    "/projects/{project_id}/orchestration/notes", response_model=OrchestrationStateOut
)
async def add_note(
    project_id: str,
    payload: OrchestrationPlanIn,
    container: ContainerDep,
    _: CurrentUser,
) -> OrchestrationStateOut:
    """Record an instruction in the project's working memory."""
    try:
        await container.orchestrator.add_orchestration_note(project_id, payload.instruction)
        result = await container.orchestrator.orchestration_state(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return OrchestrationStateOut.model_validate(result)


@router.delete(
    "/projects/{project_id}/orchestration/queue/{plan_id}",
    response_model=OrchestrationStateOut,
)
async def remove_planned_task(
    project_id: str, plan_id: str, container: ContainerDep, _: CurrentUser
) -> OrchestrationStateOut:
    try:
        removed = await container.orchestrator.remove_planned_task(project_id, plan_id)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="queued step not found"
            )
        result = await container.orchestrator.orchestration_state(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return OrchestrationStateOut.model_validate(result)


@router.post(
    "/projects/{project_id}/orchestration/queue/{plan_id}/skip",
    response_model=OrchestrationStateOut,
)
async def skip_planned_task(
    project_id: str, plan_id: str, container: ContainerDep, _: CurrentUser
) -> OrchestrationStateOut:
    try:
        updated = await container.orchestrator.set_planned_task_status(
            project_id, plan_id, PlannedTaskStatus.SKIPPED.value
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="queued step not found"
            )
        result = await container.orchestrator.orchestration_state(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return OrchestrationStateOut.model_validate(result)


@router.post("/projects/{project_id}/orchestration/advance", response_model=dict)
async def advance_queue(
    project_id: str, container: ContainerDep, _: CurrentUser
) -> dict:
    """Start the next ready queued step immediately."""
    try:
        return await container.orchestrator.advance_queue(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/projects/{project_id}/checks", response_model=CheckResultOut)
async def run_checks(
    project_id: str, container: ContainerDep, _: CurrentUser
) -> CheckResultOut:
    """Run Pyright over the project now."""
    project = await container.projects.get(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )
    if not container.checks.available():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=container.checks.status()["detail"],
        )
    try:
        root = resolve_project_root(container.settings, project)
    except ProjectPathError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    result = await container.checks.run_for_project(root)
    return CheckResultOut.model_validate(result.to_dict())
