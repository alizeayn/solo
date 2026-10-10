"""Project endpoints: create, open in place, import, inspect.

Path safety: the browser sends a name or a directory path — never an arbitrary
file operation. Every path is validated by :mod:`app.services.project_paths`
before use.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from ..deps import ContainerDep, CurrentUser
from ..domain import ProjectLocation
from ..models import Project
from ..schemas import (
    MemoryCreate,
    MemoryEntryOut,
    ProjectConfigUpdate,
    ProjectCreate,
    ProjectOpen,
    ProjectOut,
    ProjectSummaryOut,
    ProjectTreeOut,
)
from ..services.archive import ArchiveError
from ..services.project_paths import ProjectPathError, resolve_project_root
from ..services.project_service import ProjectError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

_CHUNK = 1024 * 1024  # 1 MiB


async def _to_out(container: ContainerDep, project: Project) -> ProjectOut:
    out = ProjectOut.model_validate(project)
    try:
        out.root = str(resolve_project_root(container.settings, project))
    except ProjectPathError:  # pragma: no cover - tampered record
        out.root = None
    out.is_managed = project.location == ProjectLocation.MANAGED.value
    out.file_count = await container.projects.file_count(project)
    return out


async def _require_project(container: ContainerDep, project_id: str) -> Project:
    project = await container.projects.get(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )
    return project


# --------------------------------------------------------------------------- #
# Collection
# --------------------------------------------------------------------------- #
@router.get("", response_model=list[ProjectOut])
async def list_projects(container: ContainerDep, _: CurrentUser) -> list[ProjectOut]:
    projects = await container.projects.list()
    return [await _to_out(container, project) for project in projects]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, container: ContainerDep, _: CurrentUser
) -> ProjectOut:
    """Create a new project directory and initialise its Solo state store."""
    try:
        project = await container.projects.create(payload.name, parent=payload.parent)
    except (ProjectError, ProjectPathError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return await _to_out(container, project)


@router.post("/open", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def open_project(
    payload: ProjectOpen, container: ContainerDep, _: CurrentUser
) -> ProjectOut:
    """Open an existing directory in place — nothing is copied or uploaded."""
    try:
        project = await container.projects.open_existing(payload.path, name=payload.name)
    except ProjectPathError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except ProjectError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return await _to_out(container, project)


@router.post("/upload", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def upload_project(
    container: ContainerDep,
    _: CurrentUser,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
) -> ProjectOut:
    """Import a ZIP archive into the managed workspaces directory."""
    filename = file.filename or "project.zip"
    if not filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="only .zip archives are supported",
        )

    settings = container.settings
    temp_path = settings.uploads_dir / f"{uuid.uuid4().hex}.zip"
    total = 0
    try:
        with open(temp_path, "wb") as sink:
            while True:
                chunk = await file.read(_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"archive exceeds the {settings.max_upload_mb} MB limit",
                    )
                sink.write(chunk)

        project = await container.projects.import_zip(
            name=name or Path(filename).stem, upload_path=temp_path
        )
    except HTTPException:
        raise
    except (ArchiveError, ProjectError, ProjectPathError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    finally:
        temp_path.unlink(missing_ok=True)

    logger.info("imported project %s (%d bytes)", project.id, total)
    return await _to_out(container, project)


# --------------------------------------------------------------------------- #
# Single project
# --------------------------------------------------------------------------- #
@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str, container: ContainerDep, _: CurrentUser
) -> ProjectOut:
    return await _to_out(container, await _require_project(container, project_id))


@router.delete(
    "/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_project(
    project_id: str,
    container: ContainerDep,
    _: CurrentUser,
    remove_files: bool | None = Query(
        default=None,
        description=(
            "Remove the project directory from disk. Defaults to True for "
            "managed projects and False for directories opened in place."
        ),
    ),
) -> None:
    if not await container.projects.delete(project_id, remove_files=remove_files):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )


# --------------------------------------------------------------------------- #
# Project state store
# --------------------------------------------------------------------------- #
@router.get("/{project_id}/summary", response_model=ProjectSummaryOut)
async def project_summary(
    project_id: str, container: ContainerDep, _: CurrentUser
) -> ProjectSummaryOut:
    project = await _require_project(container, project_id)
    try:
        summary = await container.store.summary(project)
    except (ProjectPathError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"project directory is not accessible: {exc}",
        ) from exc
    return ProjectSummaryOut.model_validate(summary)


@router.get("/{project_id}/tree", response_model=ProjectTreeOut)
async def project_tree(
    project_id: str,
    container: ContainerDep,
    _: CurrentUser,
    refresh: bool = Query(default=False, description="Rebuild from live state"),
) -> ProjectTreeOut:
    project = await _require_project(container, project_id)
    try:
        tree = await container.store.get_tree(project, refresh=refresh)
    except (ProjectPathError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"project directory is not accessible: {exc}",
        ) from exc
    return ProjectTreeOut.model_validate(tree)


@router.get("/{project_id}/config", response_model=dict)
async def get_project_config(
    project_id: str, container: ContainerDep, _: CurrentUser
) -> dict:
    project = await _require_project(container, project_id)
    return container.store.read_config(project)


@router.put("/{project_id}/config", response_model=dict)
async def update_project_config(
    project_id: str,
    payload: ProjectConfigUpdate,
    container: ContainerDep,
    _: CurrentUser,
) -> dict:
    project = await _require_project(container, project_id)
    patch = payload.model_dump(exclude_unset=True, exclude_none=True)
    try:
        return container.store.write_config(project, patch)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"project metadata is not writable: {exc}",
        ) from exc


@router.get("/{project_id}/memory", response_model=list[MemoryEntryOut])
async def list_memory(
    project_id: str,
    container: ContainerDep,
    _: CurrentUser,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[MemoryEntryOut]:
    project = await _require_project(container, project_id)
    entries = container.store.list_memory(project, limit=limit)
    return [MemoryEntryOut.model_validate(entry) for entry in entries]


@router.post(
    "/{project_id}/memory",
    response_model=MemoryEntryOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_memory(
    project_id: str,
    payload: MemoryCreate,
    container: ContainerDep,
    _: CurrentUser,
) -> MemoryEntryOut:
    project = await _require_project(container, project_id)
    try:
        entry = await container.store.add_memory(
            project, text=payload.text, kind=payload.kind, tags=payload.tags
        )
        await container.store.refresh(project)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"project metadata is not writable: {exc}",
        ) from exc
    return MemoryEntryOut.model_validate(entry)


@router.delete("/{project_id}/memory/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_memory(
    project_id: str, entry_id: str, container: ContainerDep, _: CurrentUser
) -> None:
    project = await _require_project(container, project_id)
    if not container.store.delete_memory(project, entry_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="memory entry not found"
        )
    await container.store.refresh(project)
