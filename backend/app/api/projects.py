"""Project / workspace endpoints.

Path safety: the browser sends a name or a ZIP file — never a filesystem path.
All validation happens in :mod:`app.services.project_service`.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from ..deps import ContainerDep, CurrentUser
from ..models import Project
from ..schemas import ProjectCreate, ProjectOut
from ..services.archive import ArchiveError
from ..services.project_service import ProjectError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

_CHUNK = 1024 * 1024  # 1 MiB


async def _to_out(container: ContainerDep, project: Project) -> ProjectOut:
    out = ProjectOut.model_validate(project)
    try:
        out.file_count = await container.projects.file_count(project)
    except ProjectError:  # pragma: no cover - tampered root path
        out.file_count = 0
    return out


@router.get("", response_model=list[ProjectOut])
async def list_projects(container: ContainerDep, _: CurrentUser) -> list[ProjectOut]:
    projects = await container.projects.list()
    return [await _to_out(container, project) for project in projects]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, container: ContainerDep, _: CurrentUser
) -> ProjectOut:
    try:
        project = await container.projects.create(payload.name)
    except ProjectError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return await _to_out(container, project)


@router.post("/upload", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def upload_project(
    container: ContainerDep,
    _: CurrentUser,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
) -> ProjectOut:
    """Upload a ZIP archive and extract it into the managed workspaces directory."""
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
    except (ArchiveError, ProjectError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    finally:
        temp_path.unlink(missing_ok=True)

    logger.info("uploaded project %s (%d bytes)", project.id, total)
    return await _to_out(container, project)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str, container: ContainerDep, _: CurrentUser
) -> ProjectOut:
    project = await container.projects.get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return await _to_out(container, project)


@router.delete(
    "/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_project(
    project_id: str, container: ContainerDep, _: CurrentUser
) -> None:
    if not await container.projects.delete(project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
