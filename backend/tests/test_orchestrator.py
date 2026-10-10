"""Service-level tests: restart recovery and admin bootstrap."""

from __future__ import annotations

from app.container import Container
from app.domain import TaskStatus
from app.repositories import ProjectRepository, TaskRepository


async def _make_project_and_task(container: Container, status: TaskStatus) -> str:
    async with container.session_factory() as session:
        project = await ProjectRepository(session).create(
            name="recovery", slug=f"recovery-{status.value.lower()}", root_path="recovery"
        )
        task = await TaskRepository(session).create(
            project_id=project.id,
            instruction="long running work",
            task_type="CODING",
            status=status,
        )
        await session.commit()
        return task.id


async def test_in_flight_tasks_are_marked_for_recovery(settings_factory):
    container = await Container.create(settings_factory())
    try:
        task_id = await _make_project_and_task(container, TaskStatus.RUNNING)
        count = await container.orchestrator._mark_stale_tasks_for_recovery()
        assert count == 1
        async with container.session_factory() as session:
            task = await TaskRepository(session).get(task_id)
            assert task is not None
            assert task.status == TaskStatus.RECOVERY_REQUIRED.value
            assert task.error and "restarted" in task.error
    finally:
        await container.close()


async def test_completed_tasks_are_not_marked_for_recovery(settings_factory):
    container = await Container.create(settings_factory())
    try:
        task_id = await _make_project_and_task(container, TaskStatus.COMPLETED)
        assert await container.orchestrator._mark_stale_tasks_for_recovery() == 0
        async with container.session_factory() as session:
            task = await TaskRepository(session).get(task_id)
            assert task is not None
            assert task.status == TaskStatus.COMPLETED.value
    finally:
        await container.close()


async def test_bootstrap_admin_from_password_file(settings_factory):
    settings = settings_factory()
    settings.ensure_directories()
    settings.bootstrap_password_file.write_text("installer-generated-pass")

    container = await Container.create(settings)
    try:
        assert await container.auth.bootstrap_admin() == "admin"
        # File is consumed so the plaintext is not retained.
        assert not settings.bootstrap_password_file.exists()
        assert await container.auth.is_initialized() is True
        # A second bootstrap is a no-op.
        assert await container.auth.bootstrap_admin() is None
    finally:
        await container.close()


async def test_bootstrap_is_skipped_without_a_password(settings_factory):
    container = await Container.create(settings_factory())
    try:
        assert await container.auth.bootstrap_admin() is None
        assert await container.auth.is_initialized() is False
    finally:
        await container.close()


async def test_health_reports_mock_agent(settings_factory):
    container = await Container.create(settings_factory())
    try:
        assert container.adapter_name == "mock"
        health = await container.adapter.health()
        assert health["available"] is True
    finally:
        await container.close()
