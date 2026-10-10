"""API tests for Create / Open / Import and the project state store."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

METADATA = ".solo"


def _make_repo(tmp_path: Path, name: str = "myrepo") -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / "main.py").write_text("print(1)")
    (root / "README.md").write_text("# hi")
    return root


# --------------------------------------------------------------------------- #
# Open in place
# --------------------------------------------------------------------------- #
def test_open_existing_directory_in_place(authed, tmp_path):
    repo = _make_repo(tmp_path)

    response = authed.post("/api/projects/open", json={"path": str(repo), "name": "Repo"})
    assert response.status_code == 201, response.text
    project = response.json()

    assert project["location"] == "external"
    assert project["is_managed"] is False
    assert project["source"] == "opened"
    assert project["root"] == str(repo.resolve())
    assert project["file_count"] == 2

    # Solo state was added *inside* the project; nothing was copied or moved.
    assert (repo / METADATA / "project.json").is_file()
    assert (repo / METADATA / "state" / "tree.json").is_file()
    assert (repo / "main.py").read_text() == "print(1)"


def test_open_is_idempotent(authed, tmp_path):
    repo = _make_repo(tmp_path)

    first = authed.post("/api/projects/open", json={"path": str(repo)}).json()
    second = authed.post("/api/projects/open", json={"path": str(repo)}).json()

    assert first["id"] == second["id"]
    assert len(authed.get("/api/projects").json()) == 1


def test_open_accepts_a_trailing_symlink(authed, tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX-only")
    repo = _make_repo(tmp_path)
    link = tmp_path / "link-to-repo"
    link.symlink_to(repo)

    project = authed.post("/api/projects/open", json={"path": str(link)}).json()
    assert project["root"] == str(repo.resolve())


def test_open_rejects_a_missing_path(authed, tmp_path):
    response = authed.post("/api/projects/open", json={"path": str(tmp_path / "nope")})
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_open_rejects_a_file(authed, tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("hi")
    response = authed.post("/api/projects/open", json={"path": str(target)})
    assert response.status_code == 400
    assert "not a directory" in response.json()["detail"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only blocked paths")
def test_open_rejects_a_blocked_system_directory(authed):
    response = authed.post("/api/projects/open", json={"path": "/etc"})
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]


def test_open_rejects_the_solo_data_directory(authed):
    settings = authed.app.state.container.settings
    response = authed.post("/api/projects/open", json={"path": str(settings.app_data_dir)})
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"]


def test_open_adopts_state_written_by_another_installation(authed, tmp_path):
    """A directory carrying Solo state keeps its identity and history."""
    repo = _make_repo(tmp_path)
    meta = repo / METADATA
    (meta / "tasks").mkdir(parents=True)
    (meta / "tasks" / "foreign-1.json").write_text(
        json.dumps({"id": "foreign-1", "instruction": "built elsewhere"})
    )
    (meta / "tasks" / "index.json").write_text(
        json.dumps(
            {
                "version": 1,
                "tasks": [
                    {
                        "id": "task:foreign-1",
                        "name": "built elsewhere",
                        "kind": "task",
                        "ref": "tasks/foreign-1.json",
                    }
                ],
            }
        )
    )
    (meta / "project.json").write_text(
        json.dumps({"version": 1, "id": "adopted-project-id", "name": "Elsewhere"})
    )

    project = authed.post("/api/projects/open", json={"path": str(repo)}).json()
    assert project["id"] == "adopted-project-id"

    tree = authed.get(f"/api/projects/{project['id']}/tree?refresh=true").json()
    tasks_group = next(
        child for child in tree["root"]["children"] if child["id"] == "group:tasks"
    )
    assert [node["id"] for node in tasks_group["children"]] == ["task:foreign-1"]


# --------------------------------------------------------------------------- #
# Delete semantics
# --------------------------------------------------------------------------- #
def test_deleting_an_opened_project_never_deletes_the_users_files(authed, tmp_path):
    repo = _make_repo(tmp_path)
    project = authed.post("/api/projects/open", json={"path": str(repo)}).json()

    assert authed.delete(f"/api/projects/{project['id']}").status_code == 204

    assert repo.is_dir()
    assert (repo / "main.py").read_text() == "print(1)"
    assert authed.get("/api/projects").json() == []


def test_deleting_a_managed_project_removes_its_directory(authed, make_project):
    project = make_project(authed, "throwaway")
    settings = authed.app.state.container.settings
    root = settings.workspaces_dir / project["slug"]
    assert root.is_dir()

    assert authed.delete(f"/api/projects/{project['id']}").status_code == 204
    assert not root.exists()


def test_deleting_a_managed_project_can_keep_files(authed, make_project):
    project = make_project(authed, "keepme")
    settings = authed.app.state.container.settings
    root = settings.workspaces_dir / project["slug"]

    assert (
        authed.delete(f"/api/projects/{project['id']}?remove_files=false").status_code
        == 204
    )
    assert root.is_dir()


# --------------------------------------------------------------------------- #
# Create at a chosen parent
# --------------------------------------------------------------------------- #
def test_create_project_at_a_parent_directory(authed, tmp_path):
    parent = tmp_path / "work"
    parent.mkdir()

    project = authed.post(
        "/api/projects", json={"name": "New Thing", "parent": str(parent)}
    ).json()

    assert project["location"] == "external"
    assert project["is_managed"] is False
    assert project["root"] == str((parent / "new-thing").resolve())
    assert (parent / "new-thing" / METADATA / "project.json").is_file()


def test_create_project_refuses_a_non_empty_target(authed, tmp_path):
    parent = tmp_path / "work"
    (parent / "taken").mkdir(parents=True)
    (parent / "taken" / "existing.txt").write_text("x")

    response = authed.post(
        "/api/projects", json={"name": "Taken", "parent": str(parent)}
    )
    assert response.status_code == 400
    assert "not empty" in response.json()["detail"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only blocked paths")
def test_create_project_rejects_a_blocked_parent(authed):
    response = authed.post("/api/projects", json={"name": "Nope", "parent": "/etc"})
    assert response.status_code == 400


def test_create_defaults_to_the_managed_directory(authed):
    project = authed.post("/api/projects", json={"name": "Managed"}).json()
    assert project["location"] == "managed"
    assert project["is_managed"] is True
    settings = authed.app.state.container.settings
    assert project["root"] == str((settings.workspaces_dir / project["slug"]).resolve())


# --------------------------------------------------------------------------- #
# State store endpoints
# --------------------------------------------------------------------------- #
def test_tree_endpoint_returns_the_state_tree(authed, make_project):
    project = make_project(authed, "tree-demo")
    tree = authed.get(f"/api/projects/{project['id']}/tree").json()

    assert tree["version"] == 1
    assert tree["root"]["kind"] == "project"
    assert {child["id"] for child in tree["root"]["children"]} == {
        "group:files",
        "group:tasks",
        "group:memory",
        "group:sessions",
    }


def test_summary_endpoint(authed, make_project):
    project = make_project(authed, "summary-demo")
    summary = authed.get(f"/api/projects/{project['id']}/summary").json()

    assert summary["project_id"] == project["id"]
    assert summary["metadata_exists"] is True
    assert summary["tree_generated_at"]


def test_project_config_round_trip(authed, make_project):
    project = make_project(authed, "config-demo")
    url = f"/api/projects/{project['id']}/config"

    defaults = authed.get(url).json()
    assert defaults["tree"]["max_depth"] is None

    updated = authed.put(url, json={"memory": {"auto_capture": False}}).json()
    assert updated["memory"]["auto_capture"] is False
    assert updated["tree"] == defaults["tree"]

    assert authed.get(url).json()["memory"]["auto_capture"] is False


def test_memory_endpoints(authed, make_project):
    project = make_project(authed, "memory-demo")
    url = f"/api/projects/{project['id']}/memory"

    assert authed.get(url).json() == []

    created = authed.post(
        url, json={"text": "Uses SQLite for the MVP", "kind": "decision", "tags": ["db"]}
    )
    assert created.status_code == 201
    entry = created.json()
    assert entry["kind"] == "decision"

    listed = authed.get(url).json()
    assert [item["id"] for item in listed] == [entry["id"]]

    # A memory entry shows up in the state tree.
    tree = authed.get(f"/api/projects/{project['id']}/tree?refresh=true").json()
    memory_group = next(
        child for child in tree["root"]["children"] if child["id"] == "group:memory"
    )
    assert memory_group["children"][0]["id"] == f"memory:{entry['id']}"

    assert authed.delete(f"{url}/{entry['id']}").status_code == 204
    assert authed.delete(f"{url}/{entry['id']}").status_code == 404
    assert authed.get(url).json() == []


def test_state_endpoints_require_a_project(authed):
    assert authed.get("/api/projects/nope/tree").status_code == 404
    assert authed.get("/api/projects/nope/summary").status_code == 404
    assert authed.get("/api/projects/nope/config").status_code == 404
    assert authed.get("/api/projects/nope/memory").status_code == 404
    assert authed.post("/api/projects/nope/memory", json={"text": "x"}).status_code == 404


# --------------------------------------------------------------------------- #
# Live activity lands in the store
# --------------------------------------------------------------------------- #
def test_completed_task_is_recorded_in_the_project_store(
    authed, make_project, wait_for_terminal
):
    project = make_project(authed, "activity-demo")
    task = authed.post(
        "/api/tasks",
        json={"project_id": project["id"], "instruction": "add a health endpoint"},
    ).json()
    wait_for_terminal(authed, task["id"])

    settings = authed.app.state.container.settings
    meta = settings.workspaces_dir / project["slug"] / METADATA
    detail_path = meta / "tasks" / f"{task['id']}.json"

    # The record is rewritten in place as the task settles (RUNNING first,
    # then COMPLETED before the terminal status is broadcast). Poll the content
    # so the assertion cannot race the rewrite.
    deadline = time.monotonic() + 5
    detail: dict = {}
    while time.monotonic() < deadline:
        if detail_path.is_file():
            detail = json.loads(detail_path.read_text())
            if detail.get("status") == "COMPLETED":
                break
        time.sleep(0.02)

    assert detail.get("status") == "COMPLETED"
    assert detail["events"], "normalised events should be recorded"
    assert detail["result_summary"]

    tree = authed.get(f"/api/projects/{project['id']}/tree").json()
    tasks_group = next(
        child for child in tree["root"]["children"] if child["id"] == "group:tasks"
    )
    assert f"task:{task['id']}" in {node["id"] for node in tasks_group["children"]}


def test_conversation_is_recorded_as_a_session(authed, make_project):
    project = make_project(authed, "session-demo")
    authed.post(
        f"/api/projects/{project['id']}/messages",
        json={"content": "how many files are there?"},
    )

    settings = authed.app.state.container.settings
    sessions = settings.workspaces_dir / project["slug"] / METADATA / "sessions"
    files = [path for path in sessions.glob("*.json") if path.name != "index.json"]
    assert len(files) == 1

    record = json.loads(files[0].read_text())
    assert [message["role"] for message in record["messages"]] == ["user", "assistant"]


# --------------------------------------------------------------------------- #
# Filesystem browser
# --------------------------------------------------------------------------- #
def test_filesystem_browser_requires_authentication(client):
    assert client.get("/api/fs/list").status_code == 401


def test_filesystem_browser_lists_only_directories(authed, tmp_path, monkeypatch):
    root = tmp_path / "browse"
    root.mkdir()
    (root / "alpha").mkdir()
    (root / "beta").mkdir()
    (root / "note.txt").write_text("x")

    listing = authed.get("/api/fs/list", params={"path": str(root)}).json()
    assert listing["path"] == str(root.resolve())
    assert [entry["name"] for entry in listing["entries"]] == ["alpha", "beta"]
    assert listing["parent"] == str(root.resolve().parent)


def test_filesystem_browser_flags_solo_projects(authed, tmp_path):
    root = tmp_path / "browse"
    project_dir = root / "already-in-solo"
    (project_dir / METADATA).mkdir(parents=True)
    (project_dir / METADATA / "project.json").write_text("{}")

    listing = authed.get("/api/fs/list", params={"path": str(root)}).json()
    assert listing["entries"][0]["is_project"] is True


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only blocked paths")
def test_filesystem_browser_rejects_blocked_paths(authed):
    response = authed.get("/api/fs/list", params={"path": "/etc"})
    assert response.status_code == 400
