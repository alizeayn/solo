"""Tests for bounded project scanning."""

from __future__ import annotations

from app.services.project_scan import scan_project_files, summarize_project


def _build_tree(root):
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_text("print('hi')")
    (root / "src" / "app.ts").write_text("export {}")
    (root / "README.md").write_text("# hi")
    # Directories that must be ignored.
    for ignored in (".git", "node_modules", "venv", "__pycache__", ".venv"):
        directory = root / ignored
        directory.mkdir()
        (directory / "noise.py").write_text("x")
    (root / ".hidden").mkdir()
    (root / ".hidden" / "secret.py").write_text("x")


def test_scan_ignores_vendor_and_hidden_directories(tmp_path):
    _build_tree(tmp_path)
    files = scan_project_files(tmp_path)
    assert "src/main.py" in files
    assert "src/app.ts" in files
    assert "README.md" in files
    assert not any("noise.py" in f for f in files)
    assert not any(".hidden" in f for f in files)


def test_scan_respects_max_files(tmp_path):
    for i in range(10):
        (tmp_path / f"f{i}.py").write_text("x")
    assert len(scan_project_files(tmp_path, max_files=3)) == 3


def test_scan_of_missing_directory_is_empty(tmp_path):
    assert scan_project_files(tmp_path / "nope") == []


def test_summarize_reports_languages(tmp_path):
    _build_tree(tmp_path)
    summary = summarize_project(tmp_path)
    assert summary["file_count"] == 3
    assert summary["languages"]["Python"] == 1
    assert summary["languages"]["TypeScript"] == 1
    assert summary["languages"]["Markdown"] == 1
