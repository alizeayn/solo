"""Tests for the project path policy and the filesystem browser."""

from __future__ import annotations

import os

import pytest

from app.config import Settings
from app.domain import ProjectLocation
from app.services.project_paths import (
    ProjectPathError,
    allowed_roots,
    default_browse_root,
    is_blocked,
    list_directory,
    resolve_directory,
    resolve_project_root,
)


class _FakeProject:
    def __init__(self, location: str, root_path: str) -> None:
        self.location = location
        self.root_path = root_path


@pytest.fixture
def settings(tmp_path) -> Settings:
    value = Settings(app_data_dir=tmp_path / "data")
    value.ensure_directories()
    return value


# --------------------------------------------------------------------------- #
# Blocked paths
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(os.name != "posix", reason="POSIX-only blocked paths")
@pytest.mark.parametrize("path", ["/etc", "/proc", "/sys", "/dev", "/boot", "/root"])
def test_system_directories_are_blocked(settings, path):
    assert is_blocked(settings, __import__("pathlib").Path(path))


@pytest.mark.skipif(os.name != "posix", reason="POSIX-only blocked paths")
def test_system_subdirectories_are_blocked(settings):
    from pathlib import Path

    assert is_blocked(settings, Path("/etc/nginx"))


def test_the_solo_data_directory_is_always_blocked(settings):
    # It holds the master encryption key and the encrypted secrets store.
    assert is_blocked(settings, settings.app_data_dir)
    assert is_blocked(settings, settings.workspaces_dir)


def test_ordinary_directories_are_not_blocked(settings, tmp_path):
    assert not is_blocked(settings, tmp_path)


# --------------------------------------------------------------------------- #
# resolve_directory
# --------------------------------------------------------------------------- #
def test_empty_path_returns_the_default_root(settings):
    assert resolve_directory(settings, None) == default_browse_root(settings)
    assert resolve_directory(settings, "   ") == default_browse_root(settings)


def test_relative_path_resolves_against_the_default_root(settings, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.project_paths.Path.home", lambda: tmp_path)
    (tmp_path / "projects").mkdir()
    assert resolve_directory(settings, "projects") == (tmp_path / "projects").resolve()


def test_missing_path_is_rejected(settings, tmp_path):
    with pytest.raises(ProjectPathError, match="does not exist"):
        resolve_directory(settings, str(tmp_path / "nope"))


def test_a_file_is_not_a_directory(settings, tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("hi")
    with pytest.raises(ProjectPathError, match="not a directory"):
        resolve_directory(settings, str(target))


def test_blocked_directory_cannot_be_resolved(settings):
    if os.name != "posix":
        pytest.skip("POSIX-only")
    with pytest.raises(ProjectPathError, match="not allowed"):
        resolve_directory(settings, "/etc")


def test_symlink_escape_is_resolved_and_rejected(settings, tmp_path):
    if os.name != "posix":
        pytest.skip("POSIX-only")
    link = tmp_path / "sneaky"
    link.symlink_to("/etc")
    with pytest.raises(ProjectPathError, match="not allowed"):
        resolve_directory(settings, str(link))


def test_allow_list_mode_restricts_openable_roots(tmp_path):
    allowed = tmp_path / "allowed"
    other = tmp_path / "other"
    allowed.mkdir()
    other.mkdir()

    settings = Settings(
        app_data_dir=tmp_path / "data",
        allow_any_project_path=False,
        project_roots=str(allowed),
    )
    settings.ensure_directories()

    assert resolve_directory(settings, str(allowed)) == allowed.resolve()
    with pytest.raises(ProjectPathError, match="outside the allowed project roots"):
        resolve_directory(settings, str(other))


def test_project_roots_accepts_multiple_entries(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    settings = Settings(
        app_data_dir=tmp_path / "data",
        project_roots=f"{first}:{second}",
    )
    roots = allowed_roots(settings)
    assert first.resolve() in roots
    assert second.resolve() in roots


# --------------------------------------------------------------------------- #
# resolve_project_root
# --------------------------------------------------------------------------- #
def test_managed_project_is_confined_to_the_workspaces_directory(settings):
    project = _FakeProject(ProjectLocation.MANAGED.value, "demo")
    assert resolve_project_root(settings, project) == (
        settings.workspaces_dir / "demo"
    ).resolve()


def test_managed_project_cannot_escape(settings):
    project = _FakeProject(ProjectLocation.MANAGED.value, "../../etc")
    with pytest.raises(ProjectPathError, match="escapes"):
        resolve_project_root(settings, project)


def test_external_project_resolves_to_its_absolute_path(settings, tmp_path):
    project = _FakeProject(ProjectLocation.EXTERNAL.value, str(tmp_path))
    assert resolve_project_root(settings, project) == tmp_path.resolve()


def test_external_project_at_a_blocked_location_is_rejected(settings):
    if os.name != "posix":
        pytest.skip("POSIX-only")
    project = _FakeProject(ProjectLocation.EXTERNAL.value, "/etc")
    with pytest.raises(ProjectPathError, match="disallowed"):
        resolve_project_root(settings, project)


# --------------------------------------------------------------------------- #
# list_directory
# --------------------------------------------------------------------------- #
def test_list_directory_returns_only_directories(settings, tmp_path):
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / "file.txt").write_text("x")

    listing = list_directory(settings, str(tmp_path))
    names = [entry["name"] for entry in listing["entries"]]
    assert names == ["alpha", "beta"]
    assert listing["path"] == str(tmp_path.resolve())
    assert listing["parent"] == str(tmp_path.resolve().parent)


def test_list_directory_sorts_hidden_last(settings, tmp_path):
    (tmp_path / "zeta").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "alpha").mkdir()

    listing = list_directory(settings, str(tmp_path))
    assert [entry["name"] for entry in listing["entries"]] == [
        "alpha",
        "zeta",
        ".hidden",
    ]
    assert listing["entries"][-1]["hidden"] is True


def test_list_directory_marks_existing_solo_projects(settings, tmp_path):
    project_dir = tmp_path / "app"
    (project_dir / settings.metadata_dir_name).mkdir(parents=True)
    (project_dir / settings.metadata_dir_name / "project.json").write_text("{}")
    (tmp_path / "plain").mkdir()

    entries = {entry["name"]: entry for entry in list_directory(settings, str(tmp_path))["entries"]}
    assert entries["app"]["is_project"] is True
    assert entries["plain"]["is_project"] is False


def test_list_directory_hides_blocked_children(settings, tmp_path, monkeypatch):
    (tmp_path / "visible").mkdir()
    (tmp_path / "secret-root").mkdir()
    blocked = tmp_path / "secret-root"

    monkeypatch.setattr(
        "app.services.project_paths.blocked_roots", lambda _settings: [blocked]
    )
    names = [entry["name"] for entry in list_directory(settings, str(tmp_path))["entries"]]
    assert "visible" in names
    assert "secret-root" not in names


def test_list_directory_defaults_to_the_home_directory(settings, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.project_paths.Path.home", lambda: tmp_path)
    assert list_directory(settings, None)["path"] == str(tmp_path.resolve())
