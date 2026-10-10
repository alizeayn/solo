"""Tests for the project file endpoints (Writing panel and uploads).

These are a security boundary: every path is validated inside the project root,
Solo's own metadata directory is not writable, and nothing is executed.
"""

from __future__ import annotations

import io
import os

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.project_files import (
    ProjectFileError,
    ProjectFileService,
    safe_upload_name,
)
from tests.conftest import ADMIN


@pytest.fixture
def client(settings_factory):
    with TestClient(create_app(settings_factory())) as test_client:
        assert test_client.post("/api/auth/setup", json=ADMIN).status_code == 201
        yield test_client


class _Project:
    """Minimal stand-in for the ORM project used by the service tests."""

    def __init__(self, root: str) -> None:
        self.location = "external"
        self.root_path = root
        self.metadata_dir = ".solo"


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
def test_write_then_read_round_trip(tmp_path, settings_factory):
    service = ProjectFileService(settings_factory())
    project = _Project(str(tmp_path))

    written = service.write(project, "docs/notes.md", "# Hello\n")
    assert written.path == "docs/notes.md"
    assert (tmp_path / "docs" / "notes.md").read_text() == "# Hello\n"

    read = service.read(project, "docs/notes.md")
    assert read.content == "# Hello\n"
    assert read.binary is False
    assert read.truncated is False


@pytest.mark.parametrize(
    "path",
    ["../escape.txt", "docs/../../escape.txt", "/etc/passwd", "a/../../b"],
)
def test_traversal_is_rejected(tmp_path, settings_factory, path):
    service = ProjectFileService(settings_factory())
    project = _Project(str(tmp_path))
    with pytest.raises(ProjectFileError):
        service.write(project, path, "pwned")
    assert not (tmp_path.parent / "escape.txt").exists()


def test_the_metadata_directory_is_not_writable(tmp_path, settings_factory):
    service = ProjectFileService(settings_factory())
    project = _Project(str(tmp_path))
    with pytest.raises(ProjectFileError, match="metadata directory"):
        service.write(project, ".solo/state/tree.json", "{}")


def test_git_is_not_writable(tmp_path, settings_factory):
    service = ProjectFileService(settings_factory())
    project = _Project(str(tmp_path))
    with pytest.raises(ProjectFileError, match="not writable"):
        service.write(project, ".git/config", "[core]")


def test_symlink_escape_is_rejected(tmp_path, settings_factory):
    if os.name != "posix":
        pytest.skip("POSIX-only")
    outside = tmp_path.parent / "outside"
    outside.mkdir(exist_ok=True)
    root = tmp_path / "repo"
    root.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)

    service = ProjectFileService(settings_factory())
    project = _Project(str(root))
    with pytest.raises(ProjectFileError):
        service.write(project, "link/escaped.txt", "pwned")
    assert not (outside / "escaped.txt").exists()


def test_binary_files_are_reported_not_returned(tmp_path, settings_factory):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "logo.png").write_bytes(b"\x89PNG\x00\x01\x02")
    service = ProjectFileService(settings_factory())
    result = service.read(_Project(str(root)), "logo.png")
    assert result.binary is True
    assert result.content == ""


def test_large_files_are_truncated_on_read(tmp_path, settings_factory):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "big.txt").write_text("x" * 600_000)
    service = ProjectFileService(settings_factory())
    result = service.read(_Project(str(root)), "big.txt")
    assert result.truncated is True
    assert len(result.content) == 512 * 1024


def test_oversized_writes_are_rejected(tmp_path, settings_factory):
    service = ProjectFileService(settings_factory())
    with pytest.raises(ProjectFileError, match="editor limit"):
        service.write(_Project(str(tmp_path)), "big.txt", "x" * (1024 * 1024 + 1))


def test_overwrite_false_protects_an_existing_file(tmp_path, settings_factory):
    service = ProjectFileService(settings_factory())
    project = _Project(str(tmp_path))
    service.write(project, "keep.txt", "original")
    with pytest.raises(ProjectFileError, match="already exists"):
        service.write(project, "keep.txt", "replaced", overwrite=False)
    assert (tmp_path / "keep.txt").read_text() == "original"


def test_missing_file_reports_clearly(tmp_path, settings_factory):
    service = ProjectFileService(settings_factory())
    with pytest.raises(ProjectFileError, match="not a file"):
        service.read(_Project(str(tmp_path)), "nope.txt")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("notes.md", "notes.md"), ("a/b/notes.md", "notes.md"), ("C:\\x\\y.txt", "y.txt")],
)
def test_upload_names_are_reduced_to_a_basename(raw, expected):
    assert safe_upload_name(raw) == expected


@pytest.mark.parametrize("raw", ["", ".", "..", ".env", ".gitignore"])
def test_unsafe_upload_names_are_rejected(raw):
    with pytest.raises(ProjectFileError):
        safe_upload_name(raw)


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_api_write_and_read(client, make_project):
    project = make_project(client, "files-demo")
    url = f"/api/projects/{project['id']}/files"

    written = client.put(url, json={"path": "notes/todo.md", "content": "- item\n"})
    assert written.status_code == 200, written.text
    assert written.json()["path"] == "notes/todo.md"

    read = client.get(url, params={"path": "notes/todo.md"})
    assert read.status_code == 200
    assert read.json()["content"] == "- item\n"


def test_api_rejects_traversal(client, make_project):
    project = make_project(client, "files-demo")
    url = f"/api/projects/{project['id']}/files"
    response = client.put(url, json={"path": "../evil.txt", "content": "pwned"})
    assert response.status_code == 400
    assert "traversal" in response.json()["detail"]


def test_api_rejects_the_metadata_directory(client, make_project):
    project = make_project(client, "files-demo")
    url = f"/api/projects/{project['id']}/files"
    response = client.put(
        url, json={"path": ".solo/state/orchestration.json", "content": "{}"}
    )
    assert response.status_code == 400
    assert "metadata" in response.json()["detail"]


def test_api_upload_stores_the_file(client, make_project):
    project = make_project(client, "upload-demo")
    settings = client.app.state.container.settings
    root = settings.workspaces_dir / project["slug"]

    response = client.post(
        f"/api/projects/{project['id']}/files/upload",
        files={"file": ("notes.md", io.BytesIO(b"# uploaded"), "text/markdown")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["path"] == "notes.md"
    assert (root / "notes.md").read_text() == "# uploaded"


def test_api_upload_rejects_an_absolute_filename(client, make_project):
    project = make_project(client, "upload-demo")
    response = client.post(
        f"/api/projects/{project['id']}/files/upload",
        files={"file": ("../../evil.sh", io.BytesIO(b"rm -rf /"), "text/x-sh")},
    )
    # The name is reduced to a basename, so it lands harmlessly in the project.
    assert response.status_code == 201
    assert response.json()["path"] == "evil.sh"


def test_api_upload_rejects_a_hidden_filename(client, make_project):
    project = make_project(client, "upload-demo")
    response = client.post(
        f"/api/projects/{project['id']}/files/upload",
        files={"file": (".bashrc", io.BytesIO(b"x"), "text/plain")},
    )
    assert response.status_code == 400


def test_file_endpoints_require_authentication(settings_factory):
    with TestClient(create_app(settings_factory())) as anon:
        anon.post("/api/auth/setup", json=ADMIN)
        anon.post("/api/auth/logout")
        assert anon.get("/api/projects/x/files?path=a.txt").status_code == 401
        assert anon.put("/api/projects/x/files", json={"path": "a.txt"}).status_code == 401


def test_unknown_project_returns_404(client):
    assert client.get("/api/projects/nope/files?path=a.txt").status_code == 404


def test_written_file_appears_in_the_state_tree(client, make_project):
    project = make_project(client, "tree-demo")
    client.put(
        f"/api/projects/{project['id']}/files",
        json={"path": "src/written.py", "content": "x = 1\n"},
    )
    tree = client.get(f"/api/projects/{project['id']}/tree?refresh=true").json()
    assert "written.py" in __import__("json").dumps(tree)


def test_limits_are_reported(client, make_project):
    project = make_project(client, "limits-demo")
    body = client.get(f"/api/projects/{project['id']}/files/limits").json()
    assert body["max_write_bytes"] > 0
    assert body["max_upload_bytes"] > body["max_write_bytes"]
