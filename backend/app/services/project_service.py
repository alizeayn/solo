"""Project / workspace management.

Security boundary: browser users never supply a filesystem path. Projects are
created only inside the application-managed workspaces directory, and every
path is re-validated before use.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import Settings
from ..domain import ProjectSource
from ..models import Project
from ..repositories import ProjectRepository
from .archive import safe_extract_zip
from .project_scan import scan_project_files

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class ProjectError(ValueError):
    """Raised for invalid project operations (bad name, missing project...)."""


def slugify(name: str) -> str:
    """Turn a display name into a filesystem-safe slug."""
    slug = _SLUG_RE.sub("-", (name or "").strip().lower()).strip("-")
    return slug[:64] or "project"


def resolve_project_root(settings: Settings, project: Project) -> Path:
    """Resolve a project's absolute root, guaranteeing it stays in-workspace."""
    base = settings.workspaces_dir.resolve()
    candidate = (base / project.root_path).resolve()
    if candidate != base and base not in candidate.parents:
        raise ProjectError("project root escapes the managed workspaces directory")
    return candidate


class ProjectService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    async def list(self) -> list[Project]:
        async with self._session_factory() as session:
            return await ProjectRepository(session).list()

    async def get(self, project_id: str) -> Project | None:
        async with self._session_factory() as session:
            return await ProjectRepository(session).get(project_id)

    async def file_count(self, project: Project) -> int:
        root = resolve_project_root(self._settings, project)
        return len(scan_project_files(root))

    # ------------------------------------------------------------------ #
    # Mutations
    # ------------------------------------------------------------------ #
    async def create(self, name: str) -> Project:
        name = (name or "").strip()
        if not name:
            raise ProjectError("project name is required")
        async with self._session_factory() as session:
            repo = ProjectRepository(session)
            slug = await self._unique_slug(repo, slugify(name))
            root = self._settings.workspaces_dir / slug
            root.mkdir(parents=True, exist_ok=True)
            project = await repo.create(
                name=name,
                slug=slug,
                root_path=slug,
                source=ProjectSource.CREATED.value,
            )
            await session.commit()
            logger.info("created project %s (%s)", project.id, slug)
            return project

    async def import_zip(self, *, name: str, upload_path: Path) -> Project:
        name = (name or "").strip() or upload_path.stem
        async with self._session_factory() as session:
            repo = ProjectRepository(session)
            slug = await self._unique_slug(repo, slugify(name))
            root = self._settings.workspaces_dir / slug
            # Let ArchiveError propagate; the API layer maps it to HTTP 400.
            written = safe_extract_zip(upload_path, root, settings=self._settings)
            if written == 0:
                raise ProjectError("archive contained no extractable files")
            project = await repo.create(
                name=name,
                slug=slug,
                root_path=slug,
                source=ProjectSource.UPLOADED.value,
            )
            await session.commit()
            logger.info("imported project %s (%s) with %d files", project.id, slug, written)
            return project

    async def delete(self, project_id: str) -> bool:
        async with self._session_factory() as session:
            repo = ProjectRepository(session)
            project = await repo.get(project_id)
            if project is None:
                return False
            root = resolve_project_root(self._settings, project)
            await repo.delete(project)
            await session.commit()
        # Remove files only after the DB record is gone, and only in-workspace.
        if root.exists() and root.is_dir():
            shutil.rmtree(root, ignore_errors=True)
        logger.info("deleted project %s", project_id)
        return True

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    async def _unique_slug(self, repo: ProjectRepository, base: str) -> str:
        slug = base
        suffix = 2
        while await repo.get_by_slug(slug) is not None:
            slug = f"{base}-{suffix}"
            suffix += 1
        return slug
