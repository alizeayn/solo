"""Project repository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Project


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self) -> list[Project]:
        result = await self.session.execute(select(Project).order_by(Project.created_at))
        return list(result.scalars().all())

    async def get(self, project_id: str) -> Project | None:
        return await self.session.get(Project, project_id)

    async def get_by_slug(self, slug: str) -> Project | None:
        result = await self.session.execute(select(Project).where(Project.slug == slug))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        name: str,
        slug: str,
        root_path: str,
        source: str = "created",
        location: str = "managed",
        metadata_dir: str = ".solo",
        project_id: str | None = None,
    ) -> Project:
        project = Project(
            name=name,
            slug=slug,
            root_path=root_path,
            source=source,
            location=location,
            metadata_dir=metadata_dir,
        )
        if project_id:
            project.id = project_id
        self.session.add(project)
        await self.session.flush()
        return project

    async def find_by_root(self, root_path: str, location: str) -> Project | None:
        """Locate a project by its stored root, to make 'open' idempotent."""
        result = await self.session.execute(
            select(Project)
            .where(Project.root_path == root_path, Project.location == location)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def delete(self, project: Project) -> None:
        await self.session.delete(project)
