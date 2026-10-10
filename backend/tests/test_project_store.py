"""Tests for the per-project state store (``<project-root>/.solo``)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.container import Container
from app.repositories import ConversationRepository, TaskRepository
from app.services.project_paths import ProjectPathError


@pytest.fixture
async def container(settings_factory):
    instance = await Container.create(settings_factory())
    try:
        yield instance
    finally:
        await instance.close()


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


async def test_create_initialises_the_metadata_store(container):
    project = await container.projects.create("My App")
    paths = container.store.paths(project)

    assert paths.meta.is_dir()
    assert paths.manifest.is_file()
    assert paths.config.is_file()
    assert paths.tree.is_file()
    assert paths.memory_index.is_file()
    assert paths.gitignore.is_file()
    assert paths.memory_entries.is_dir()
    assert paths.sessions_dir.is_dir()
    assert paths.tasks_dir.is_dir()

    manifest = _read(paths.manifest)
    assert manifest["id"] == project.id
    assert manifest["name"] == "My App"
    assert manifest["origin"] == "created"
    assert manifest["root"] == str(paths.root)


async def test_the_metadata_directory_is_excluded_from_a_populated_tree(container):
    project = await container.projects.create("Demo")
    paths = container.store.paths(project)
    root = paths.root
    # Populate real content so the file tree is non-trivial.
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("x")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "dep.js").write_text("y")

    tree = await container.store.get_tree(project, refresh=True)
    files_group = next(
        child for child in tree["root"]["children"] if child["id"] == "group:files"
    )
    listing = json.dumps(files_group)
    assert paths.metadata_dir_name not in listing
    assert "node_modules" not in listing
    assert "main.py" in listing
    project = await container.projects.create("Demo")
    content = container.store.paths(project).gitignore.read_text()
    assert content.strip().endswith("*")
    assert "generated" in content.lower()


async def test_tree_has_the_four_state_groups(container):
    project = await container.projects.create("Demo")
    tree = await container.store.get_tree(project, refresh=True)

    ids = [child["id"] for child in tree["root"]["children"]]
    assert ids == ["group:files", "group:tasks", "group:memory", "group:sessions"]
    assert tree["root"]["kind"] == "project"
    assert tree["project"]["id"] == project.id


async def test_file_tree_lists_project_files_and_excludes_noise(container):
    project = await container.projects.create("Demo")
    paths = container.store.paths(project)

    (paths.root / "src").mkdir()
    (paths.root / "src" / "main.py").write_text("print(1)")
    (paths.root / "README.md").write_text("# hi")
    for ignored in ("node_modules", ".git", "__pycache__"):
        directory = paths.root / ignored
        directory.mkdir()
        (directory / "noise.js").write_text("x")

    tree = await container.store.get_tree(project, refresh=True)
    files_group = next(
        child for child in tree["root"]["children"] if child["id"] == "group:files"
    )
    names = {child["name"] for child in files_group["children"]}
    assert names == {"src", "README.md"}

    src = next(child for child in files_group["children"] if child["name"] == "src")
    assert src["kind"] == "directory"
    assert [child["name"] for child in src["children"]] == ["main.py"]
    assert src["children"][0]["kind"] == "file"
    assert src["children"][0]["ext"] == ".py"


async def test_the_metadata_directory_never_appears_in_the_file_tree(container):
    project = await container.projects.create("Demo")
    tree = await container.store.get_tree(project, refresh=True)
    files_group = next(
        child for child in tree["root"]["children"] if child["id"] == "group:files"
    )
    assert json.dumps(files_group) == json.dumps(
        {"id": "group:files", "name": "Files", "kind": "group", "children": []}
    )


async def test_memory_entries_round_trip(container):
    project = await container.projects.create("Demo")

    entry = await container.store.add_memory(
        project, text="Uses SQLite for the MVP", kind="decision", tags=["storage"]
    )
    assert entry["kind"] == "decision"
    assert container.store.paths(project).memory_entries.joinpath(
        f"{entry['id']}.json"
    ).is_file()

    listed = container.store.list_memory(project)
    assert [item["id"] for item in listed] == [entry["id"]]
    assert listed[0]["tags"] == ["storage"]

    # Newest first.
    second = await container.store.add_memory(project, text="Second note")
    assert [item["id"] for item in container.store.list_memory(project)] == [
        second["id"],
        entry["id"],
    ]

    assert container.store.delete_memory(project, entry["id"]) is True
    assert container.store.delete_memory(project, entry["id"]) is False
    assert [item["id"] for item in container.store.list_memory(project)] == [second["id"]]


async def test_memory_survives_a_refresh(container):
    project = await container.projects.create("Demo")
    await container.store.add_memory(project, text="Remember this")
    tree = await container.store.refresh(project)

    memory_group = next(
        child for child in tree["root"]["children"] if child["id"] == "group:memory"
    )
    assert len(memory_group["children"]) == 1
    assert memory_group["children"][0]["kind"] == "memory"
    assert memory_group["children"][0]["ref"].startswith("memory/entries/")


async def test_config_is_deep_merged_and_persisted(container):
    project = await container.projects.create("Demo")

    defaults = container.store.read_config(project)
    assert defaults["tree"]["max_depth"] is None
    assert defaults["memory"]["auto_capture"] is True

    updated = container.store.write_config(project, {"memory": {"auto_capture": False}})
    # Untouched siblings survive the merge.
    assert updated["memory"] == {
        "max_entries": defaults["memory"]["max_entries"],
        "auto_capture": False,
    }
    assert updated["tree"] == defaults["tree"]

    reread = container.store.read_config(project)
    assert reread["memory"]["auto_capture"] is False


async def test_initialize_is_idempotent_and_preserves_configuration(container):
    project = await container.projects.create("Demo")
    container.store.write_config(project, {"memory": {"auto_capture": False}})

    # Opening the same project again must not clobber per-project configuration.
    container.store.initialize(project, origin="opened")
    assert container.store.read_config(project)["memory"]["auto_capture"] is False


async def test_refresh_records_tasks_and_sessions(container):
    project = await container.projects.create("Demo")
    async with container.session_factory() as session:
        conversations = ConversationRepository(session)
        conversation = await conversations.get_or_create_for_project(project.id)
        await conversations.add_message(
            conversation_id=conversation.id, role="user", content="hello"
        )
        await TaskRepository(session).create(
            project_id=project.id, instruction="add a feature", task_type="CODING"
        )
        await session.commit()

    tree = await container.store.refresh(project)

    tasks_group = next(
        child for child in tree["root"]["children"] if child["id"] == "group:tasks"
    )
    assert tasks_group["children"][0]["name"] == "add a feature"
    assert tasks_group["children"][0]["kind"] == "task"

    sessions_group = next(
        child for child in tree["root"]["children"] if child["id"] == "group:sessions"
    )
    assert sessions_group["children"][0]["messages"] == 1


async def test_record_task_writes_a_portable_detail_file(container):
    project = await container.projects.create("Demo")
    async with container.session_factory() as session:
        task = await TaskRepository(session).create(
            project_id=project.id, instruction="do the thing", task_type="CODING"
        )
        task_id = task.id
        await session.commit()

    record = await container.store.record_task(project, task_id)
    assert record is not None
    assert record["instruction"] == "do the thing"

    path = container.store.paths(project).tasks_dir / f"{task_id}.json"
    assert path.is_file()
    assert _read(path)["instruction"] == "do the thing"


async def test_record_session_writes_the_transcript(container):
    project = await container.projects.create("Demo")
    async with container.session_factory() as session:
        conversations = ConversationRepository(session)
        conversation = await conversations.get_or_create_for_project(project.id)
        await conversations.add_message(
            conversation_id=conversation.id, role="user", content="hi there"
        )
        await session.commit()
        conversation_id = conversation.id

    record = await container.store.record_session(project, conversation_id)
    assert record is not None
    assert record["messages"][0]["content"] == "hi there"

    path = container.store.paths(project).sessions_dir / f"{conversation_id}.json"
    assert path.is_file()


async def test_refresh_preserves_records_written_by_another_installation(container):
    """Portability: an index entry with an on-disk detail file is not dropped."""
    project = await container.projects.create("Demo")
    paths = container.store.paths(project)

    foreign_id = "foreign-task-1"
    (paths.tasks_dir / f"{foreign_id}.json").write_text(
        json.dumps({"id": foreign_id, "instruction": "from another machine"})
    )
    paths.tasks_index.write_text(
        json.dumps(
            {
                "version": 1,
                "tasks": [
                    {
                        "id": f"task:{foreign_id}",
                        "name": "from another machine",
                        "kind": "task",
                        "ref": f"tasks/{foreign_id}.json",
                    }
                ],
            }
        )
    )

    tree = await container.store.refresh(project)
    tasks_group = next(
        child for child in tree["root"]["children"] if child["id"] == "group:tasks"
    )
    assert [node["id"] for node in tasks_group["children"]] == [f"task:{foreign_id}"]


async def test_refresh_drops_index_entries_whose_detail_file_is_gone(container):
    project = await container.projects.create("Demo")
    paths = container.store.paths(project)
    paths.tasks_index.write_text(
        json.dumps(
            {
                "version": 1,
                "tasks": [
                    {"id": "task:ghost", "name": "ghost", "kind": "task", "ref": "tasks/ghost.json"}
                ],
            }
        )
    )
    tree = await container.store.refresh(project)
    tasks_group = next(
        child for child in tree["root"]["children"] if child["id"] == "group:tasks"
    )
    assert tasks_group["children"] == []


async def test_summary_reports_stored_state(container):
    project = await container.projects.create("Demo")
    paths = container.store.paths(project)
    (paths.root / "src").mkdir()
    (paths.root / "src" / "main.py").write_text("x")
    await container.store.add_memory(project, text="a note")

    summary = await container.store.summary(project)
    assert summary["project_id"] == project.id
    assert summary["location"] == "managed"
    assert summary["metadata_exists"] is True
    assert summary["file_count"] == 1
    assert summary["directory_count"] == 1
    assert summary["memory_count"] == 1
    assert summary["tree_generated_at"] is not None


async def test_unwritable_project_directory_is_reported_clearly(container):
    if os.name != "posix" or os.geteuid() == 0:
        pytest.skip("requires a non-root POSIX user")

    project = await container.projects.create("Demo")
    paths = container.store.paths(project)
    paths.manifest.unlink()

    try:
        paths.meta.chmod(0o500)
        with pytest.raises(ProjectPathError, match="cannot write project metadata"):
            container.store.initialize(project, origin="created")
    finally:
        paths.meta.chmod(0o700)
