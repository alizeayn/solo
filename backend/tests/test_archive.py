"""Tests for safe ZIP extraction (Zip Slip, symlinks, size limits)."""

from __future__ import annotations

import stat
import zipfile

import pytest

from app.config import Settings
from app.services.archive import ArchiveError, safe_extract_zip


def _zip(path, entries, *, symlinks=None):
    """Build a ZIP with the given text entries and optional symlink entries."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
        for name, target in (symlinks or {}).items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, target)
    return path


def test_extracts_regular_files(tmp_path):
    archive = _zip(tmp_path / "a.zip", {"readme.txt": "hello", "src/main.py": "x=1"})
    dest = tmp_path / "out"
    written = safe_extract_zip(archive, dest)
    assert written == 2
    assert (dest / "readme.txt").read_text() == "hello"
    assert (dest / "src" / "main.py").read_text() == "x=1"


def test_strips_single_wrapping_directory(tmp_path):
    archive = _zip(
        tmp_path / "a.zip",
        {"myapp/readme.txt": "hi", "myapp/src/main.py": "x=1"},
    )
    dest = tmp_path / "out"
    safe_extract_zip(archive, dest)
    assert (dest / "readme.txt").exists()
    assert (dest / "src" / "main.py").exists()
    assert not (dest / "myapp").exists()


@pytest.mark.parametrize(
    "name",
    ["../escape.txt", "nested/../../escape.txt", "/etc/passwd", "C:/windows/x"],
)
def test_rejects_path_traversal(tmp_path, name):
    archive = _zip(tmp_path / "a.zip", {name: "pwned"})
    with pytest.raises(ArchiveError):
        safe_extract_zip(archive, tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()


def test_rejects_symlink_entries(tmp_path):
    archive = _zip(tmp_path / "a.zip", {}, symlinks={"link": "/etc/passwd"})
    with pytest.raises(ArchiveError, match="symlink"):
        safe_extract_zip(archive, tmp_path / "out")


def test_rejects_non_zip(tmp_path):
    bogus = tmp_path / "not.zip"
    bogus.write_text("this is definitely not a zip file")
    with pytest.raises(ArchiveError):
        safe_extract_zip(bogus, tmp_path / "out")


def test_rejects_too_many_entries(tmp_path):
    archive = _zip(tmp_path / "a.zip", {f"f{i}.txt": "x" for i in range(20)})
    with pytest.raises(ArchiveError, match="too many entries"):
        safe_extract_zip(archive, tmp_path / "out", max_entries=5)


def test_rejects_oversized_uncompressed_payload(tmp_path):
    archive = _zip(tmp_path / "a.zip", {"big.txt": "a" * 5000})
    with pytest.raises(ArchiveError, match="too much data"):
        safe_extract_zip(archive, tmp_path / "out", max_uncompressed_bytes=1000)


def test_uses_settings_limits(tmp_path):
    settings = Settings(app_data_dir=tmp_path / "data", max_zip_entries=2)
    archive = _zip(tmp_path / "a.zip", {f"f{i}.txt": "x" for i in range(5)})
    with pytest.raises(ArchiveError):
        safe_extract_zip(archive, tmp_path / "out", settings=settings)
