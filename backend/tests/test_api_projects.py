"""API tests for project creation, upload safety and lifecycle."""

from __future__ import annotations

import io
import zipfile

import pytest

from app.config import Settings
from app.services.project_paths import ProjectPathError
from app.services.project_service import resolve_project_root


def _zip_bytes(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_create_list_get_delete(authed):
    created = authed.post("/api/projects", json={"name": "My Project"})
    assert created.status_code == 201
    project = created.json()
    assert project["slug"] == "my-project"
    assert project["source"] == "created"
    assert project["file_count"] == 0

    listed = authed.get("/api/projects").json()
    assert [p["id"] for p in listed] == [project["id"]]

    fetched = authed.get(f"/api/projects/{project['id']}")
    assert fetched.status_code == 200

    assert authed.delete(f"/api/projects/{project['id']}").status_code == 204
    assert authed.get(f"/api/projects/{project['id']}").status_code == 404


def test_duplicate_names_get_unique_slugs(authed):
    first = authed.post("/api/projects", json={"name": "demo"}).json()
    second = authed.post("/api/projects", json={"name": "demo"}).json()
    assert first["slug"] == "demo"
    assert second["slug"] == "demo-2"


def test_blank_name_rejected(authed):
    assert authed.post("/api/projects", json={"name": "   "}).status_code == 400


def test_upload_extracts_archive(authed):
    payload = _zip_bytes(
        {"proj/README.md": "# hi", "proj/src/main.py": "print(1)", "proj/src/util.py": "x=2"}
    )
    response = authed.post(
        "/api/projects/upload",
        files={"file": ("proj.zip", payload, "application/zip")},
        data={"name": "Uploaded"},
    )
    assert response.status_code == 201, response.text
    project = response.json()
    assert project["source"] == "imported"
    assert project["location"] == "managed"
    assert project["is_managed"] is True
    # Single wrapping directory is stripped, so files land at the root.
    assert project["file_count"] == 3


def test_upload_rejects_non_zip_extension(authed):
    response = authed.post(
        "/api/projects/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_upload_rejects_corrupt_archive(authed):
    response = authed.post(
        "/api/projects/upload",
        files={"file": ("bad.zip", b"not a zip at all", "application/zip")},
    )
    assert response.status_code == 400


def test_upload_rejects_path_traversal(authed):
    payload = _zip_bytes({"../escape.txt": "pwned"})
    response = authed.post(
        "/api/projects/upload",
        files={"file": ("evil.zip", payload, "application/zip")},
        data={"name": "evil"},
    )
    assert response.status_code == 400


def test_upload_enforces_size_limit(authed):
    payload = _zip_bytes({"big.txt": "a" * 4096})
    # Patch the running app's settings to a 1 KB limit.
    authed.app.state.container.settings.max_upload_mb = 0  # 0 MB == 0 bytes
    response = authed.post(
        "/api/projects/upload",
        files={"file": ("big.zip", payload, "application/zip")},
    )
    assert response.status_code == 413


def test_unknown_project_returns_404(authed):
    assert authed.get("/api/projects/does-not-exist").status_code == 404


def test_resolve_project_root_rejects_escapes(tmp_path):
    settings = Settings(app_data_dir=tmp_path / "data")
    settings.ensure_directories()

    class FakeProject:
        location = "managed"
        root_path = "../../etc"

    with pytest.raises(ProjectPathError):
        resolve_project_root(settings, FakeProject())


def test_resolve_project_root_accepts_valid_path(tmp_path):
    settings = Settings(app_data_dir=tmp_path / "data")
    settings.ensure_directories()

    class FakeProject:
        location = "managed"
        root_path = "my-project"

    assert resolve_project_root(settings, FakeProject()) == (
        settings.workspaces_dir / "my-project"
    ).resolve()
