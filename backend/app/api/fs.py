"""Filesystem browsing for the Open Project dialog.

This endpoint exposes directory names only — never file contents — and every
path passes through :func:`app.services.project_paths.resolve_directory`, which
enforces the blocked-path list, the optional allow-list and symlink
resolution. See that module for the security model.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from ..deps import ContainerDep, CurrentUser
from ..schemas import FsListing
from ..services.project_paths import ProjectPathError, list_directory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fs", tags=["filesystem"])


@router.get("/list", response_model=FsListing)
async def browse(
    container: ContainerDep,
    _: CurrentUser,
    path: str | None = Query(default=None, description="Directory to list"),
) -> FsListing:
    """List sub-directories of *path* (or the default root when omitted)."""
    try:
        listing = list_directory(container.settings, path)
    except ProjectPathError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return FsListing.model_validate(listing)
