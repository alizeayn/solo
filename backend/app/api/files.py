"""Project file endpoints for the Writing panel and the upload tile.

Reading, writing and uploading files inside an open project. Every path is
validated inside the project root by :mod:`app.services.project_files`, nothing
is executed, and Solo's own metadata directory is not writable from here.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from ..deps import ContainerDep, CurrentUser
from ..schemas import FileContentOut, FileWriteIn
from ..services.project_files import (
    MAX_READ_BYTES,
    MAX_UPLOAD_BYTES,
    MAX_WRITE_BYTES,
    ProjectFileError,
    ProjectFileService,
    safe_upload_name,
)
from ..services.project_paths import ProjectPathError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/files", tags=["files"])

_CHUNK = 1024 * 1024


async def _require_project(container: ContainerDep, project_id: str):
    project = await container.projects.get(project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project not found"
        )
    return project


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectFileError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"the project directory is not accessible: {exc}",
    )


@router.get("", response_model=FileContentOut)
async def read_file(
    project_id: str,
    container: ContainerDep,
    _: CurrentUser,
    path: str = Query(min_length=1, description="Path relative to the project root"),
) -> FileContentOut:
    project = await _require_project(container, project_id)
    service = ProjectFileService(container.settings)
    try:
        result = service.read(project, path)
    except (ProjectFileError, ProjectPathError, OSError) as exc:
        raise _map_error(exc) from exc
    return FileContentOut.model_validate(result.__dict__)


@router.put("", response_model=FileContentOut)
async def write_file(
    project_id: str,
    payload: FileWriteIn,
    container: ContainerDep,
    _: CurrentUser,
) -> FileContentOut:
    """Create or replace a text file in the project."""
    project = await _require_project(container, project_id)
    service = ProjectFileService(container.settings)
    try:
        result = service.write(
            project, payload.path, payload.content, overwrite=payload.overwrite
        )
    except (ProjectFileError, ProjectPathError, OSError) as exc:
        raise _map_error(exc) from exc

    logger.info("wrote %s (%d bytes) in project %s", result.path, result.size, project_id)
    await container.store.refresh(project)
    return FileContentOut.model_validate(result.__dict__)


@router.post("/upload", response_model=FileContentOut, status_code=status.HTTP_201_CREATED)
async def upload_file(
    project_id: str,
    container: ContainerDep,
    _: CurrentUser,
    file: UploadFile = File(...),
    directory: str = Form(default=""),
    overwrite: bool = Form(default=True),
) -> FileContentOut:
    """Upload one file into the project, optionally into a sub-directory."""
    project = await _require_project(container, project_id)

    try:
        name = safe_upload_name(file.filename or "")
    except ProjectFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    relative = f"{directory.strip().strip('/')}/{name}" if directory.strip() else name

    staging = container.settings.uploads_dir / f"{uuid.uuid4().hex}-{name}"
    service = ProjectFileService(container.settings)
    total = 0
    try:
        with open(staging, "wb") as sink:
            while True:
                chunk = await file.read(_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            "the file exceeds the "
                            f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit"
                        ),
                    )
                sink.write(chunk)

        result = service.save_upload(project, relative, staging, overwrite=overwrite)
    except HTTPException:
        raise
    except (ProjectFileError, ProjectPathError, OSError) as exc:
        raise _map_error(exc) from exc
    finally:
        staging.unlink(missing_ok=True)

    logger.info("uploaded %s (%d bytes) into project %s", result.path, total, project_id)
    await container.store.refresh(project)
    return FileContentOut.model_validate(result.__dict__)


@router.get("/limits", response_model=dict)
async def limits(_: CurrentUser) -> dict:
    """Limits the UI should show before a user hits them."""
    return {
        "max_read_bytes": MAX_READ_BYTES,
        "max_write_bytes": MAX_WRITE_BYTES,
        "max_upload_bytes": MAX_UPLOAD_BYTES,
    }
