"""Project management: create, open in place, import, delete.

Three distinct ways a project can enter Solo:

* **Create** — a new directory is created (in the managed workspaces directory
  by default, or at a chosen parent path) and initialised with a Solo
  metadata store.
* **Open** — an existing directory on this machine is adopted *in place*. Its
  contents are never copied and never uploaded; Solo only adds the metadata
  directory and reads the project where it already lives.
* **Import** — a ZIP archive is extracted into the managed workspaces
  directory (the one path that does copy files, offered for convenience).

Path safety lives in :mod:`app.services.project_paths`; all database access
goes through :class:`ProjectRepository`.
"""

from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import Settings
from ..domain import ProjectLocation, ProjectSource
from ..models import Project
from ..repositories import ProjectRepository
from .archive import safe_extract_zip
from .project_paths import (
    ProjectPathError,
    has_project_metadata,
    metadata_path,
    resolve_directory,
    resolve_project_root,
)
from .project_scan import scan_project_files
from .project_store import ProjectStoreService

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class ProjectError(ValueError):
    """Raised for invalid project operations (bad name, missing project...)."""


def slugify(name: str) -> str:
    """Turn a display name into a filesystem-safe slug."""
    slug = _SLUG_RE.sub("-", (name or "").strip().lower()).strip("-")
    return slug[:64] or "project"


class ProjectService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        store: ProjectStoreService,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._store = store

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
        try:
            root = resolve_project_root(self._settings, project)
        except ProjectPathError:
            return 0
        return len(scan_project_files(root))

    # ------------------------------------------------------------------ #
    # Create
    # ------------------------------------------------------------------ #
    async def create(self, name: str, *, parent: str | None = None) -> Project:
        """Create a new project directory.

        ``parent`` unset creates the project inside Solo's managed workspaces
        directory. ``parent`` set creates it at ``<parent>/<slug>`` on disk.
        """
        name = (name or "").strip()
        if not name:
            raise ProjectError("project name is required")

        slug = slugify(name)

        if parent:
            parent_dir = resolve_directory(self._settings, parent)
            root = (parent_dir / slug).resolve()
            if root.exists() and any(root.iterdir()):
                raise ProjectError(f"{root} already exists and is not empty")
            try:
                root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise ProjectError(
                    f"cannot create {root}: {exc.strerror or exc}"
                ) from exc
            location = ProjectLocation.EXTERNAL.value
            root_path = str(root)
        else:
            location = ProjectLocation.MANAGED.value
            root = None
            root_path = ""

        return await self._register(
            name=name,
            slug=slug,
            location=location,
            root_path=root_path,
            origin=ProjectSource.CREATED.value,
        )

    # ------------------------------------------------------------------ #
    # Open in place
    # ------------------------------------------------------------------ #
    async def open_existing(self, path: str, *, name: str | None = None) -> Project:
        """Adopt an existing directory on this machine, without copying it.

        Idempotent: opening the same directory twice returns the same record.
        An existing ``.solo/project.json`` is honoured, including its project id,
        so history written by another Solo installation is preserved.
        """
        resolved = resolve_directory(self._settings, path)
        root_path = str(resolved)

        async with self._session_factory() as session:
            repo = ProjectRepository(session)
            existing = await repo.find_by_root(
                root_path, ProjectLocation.EXTERNAL.value
            )
            if existing is not None:
                project = existing
                await session.commit()
            else:
                manifest = self._store.read_manifest_at(resolved) or {}
                adopted_id = manifest.get("id")
                if adopted_id and await repo.get(adopted_id) is not None:
                    adopted_id = None

                project = await self._create_record(
                    repo,
                    name=(name or resolved.name or "project").strip(),
                    location=ProjectLocation.EXTERNAL.value,
                    root_path=root_path,
                    origin=ProjectSource.OPENED.value,
                    project_id=adopted_id,
                )
                await session.flush()
                try:
                    self._store.initialize(project, origin=ProjectSource.OPENED.value)
                except ProjectPathError:
                    await session.rollback()
                    raise
                await session.commit()

        # Rebuild the tree so an opened project reflects its current contents.
        await self._store.refresh(project)
        logger.info("opened project %s at %s", project.id, root_path)
        return project

    # ------------------------------------------------------------------ #
    # Import a ZIP archive
    # ------------------------------------------------------------------ #
    async def import_zip(self, *, name: str, upload_path: Path) -> Project:
        name = (name or "").strip() or upload_path.stem
        slug = slugify(name)

        async with self._session_factory() as session:
            repo = ProjectRepository(session)
            unique_slug = await self._unique_slug(repo, slug)
            root = self._settings.workspaces_dir / unique_slug
            # ArchiveError / ProjectPathError propagate to the API layer.
            written = safe_extract_zip(upload_path, root, settings=self._settings)
            if written == 0:
                raise ProjectError("archive contained no extractable files")
            project = await repo.create(
                name=name,
                slug=unique_slug,
                root_path=unique_slug,
                source=ProjectSource.IMPORTED.value,
                location=ProjectLocation.MANAGED.value,
                metadata_dir=self._settings.metadata_dir_name,
            )
            await session.flush()
            self._store.initialize(project, origin=ProjectSource.IMPORTED.value)
            await session.commit()
            logger.info(
                "imported project %s (%s) with %d files", project.id, unique_slug, written
            )

        await self._store.refresh(project)
        return project

    # ------------------------------------------------------------------ #
    # Delete
    # ------------------------------------------------------------------ #
    async def delete(
        self, project_id: str, *, remove_files: bool | None = None
    ) -> bool:
        """Remove a project.

        Managed projects have their directory removed. Projects opened in place
        are only unregistered: the user's files on disk are never deleted unless
        ``remove_files=True`` is passed explicitly.
        """
        async with self._session_factory() as session:
            repo = ProjectRepository(session)
            project = await repo.get(project_id)
            if project is None:
                return False
            managed = project.location == ProjectLocation.MANAGED.value
            try:
                root: Path | None = resolve_project_root(self._settings, project)
            except ProjectPathError:  # pragma: no cover - tampered record
                root = None
            await repo.delete(project)
            await session.commit()

        should_remove = managed if remove_files is None else remove_files
        if should_remove and root is not None and root.is_dir():
            shutil.rmtree(root, ignore_errors=True)

        logger.info(
            "deleted project %s (files removed: %s)", project_id, should_remove
        )
        return True

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    async def _register(
        self,
        *,
        name: str,
        slug: str,
        location: str,
        root_path: str,
        origin: str,
    ) -> Project:
        """Create the DB record and initialise its metadata store."""
        async with self._session_factory() as session:
            repo = ProjectRepository(session)
            if location == ProjectLocation.MANAGED.value:
                unique_slug = await self._unique_slug(repo, slug)
                root = self._settings.workspaces_dir / unique_slug
                try:
                    root.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    raise ProjectError(
                        f"cannot create {root}: {exc.strerror or exc}"
                    ) from exc
                root_path = unique_slug
                slug = unique_slug
            else:
                slug = await self._unique_slug(repo, slug)

            project = await repo.create(
                name=name,
                slug=slug,
                root_path=root_path,
                source=origin,
                location=location,
                metadata_dir=self._settings.metadata_dir_name,
            )
            await session.flush()
            try:
                self._store.initialize(project, origin=origin)
            except ProjectPathError:
                await session.rollback()
                raise
            await session.commit()

        await self._store.refresh(project)
        logger.info("created project %s (%s)", project.id, project.location)
        return project

    async def _create_record(
        self,
        repo: ProjectRepository,
        *,
        name: str,
        location: str,
        root_path: str,
        origin: str,
        project_id: str | None = None,
    ) -> Project:
        slug = await self._unique_slug(repo, slugify(name))
        return await repo.create(
            name=name,
            slug=slug,
            root_path=root_path,
            source=origin,
            location=location,
            metadata_dir=self._settings.metadata_dir_name,
            project_id=project_id,
        )

    async def _unique_slug(self, repo: ProjectRepository, base: str) -> str:
        slug = base
        suffix = 2
        while await repo.get_by_slug(slug) is not None:
            slug = f"{base}-{suffix}"
            suffix += 1
        return slug


__all__ = [
    "ProjectError",
    "ProjectService",
    "has_project_metadata",
    "metadata_path",
    "resolve_project_root",
    "slugify",
]
