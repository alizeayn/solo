"""Bounded project scanning.

Kept deliberately cheap and defensive: the project tree is untrusted input and
may contain huge or unusual directories. All scans are depth- and count-bounded.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import os

IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        "dist",
        "build",
        ".next",
        ".idea",
        ".vscode",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "target",
        "vendor",
    }
)

_LANGUAGE_BY_EXT = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".sh": "Shell",
    ".sql": "SQL",
    ".html": "HTML",
    ".css": "CSS",
    ".md": "Markdown",
    ".json": "JSON",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".toml": "TOML",
}

MAX_SCAN_FILES = 5000


def scan_project_files(
    root: Path,
    *,
    max_files: int = MAX_SCAN_FILES,
    max_depth: int = 12,
) -> list[str]:
    """Return relative paths of regular files under *root*, bounded in size."""
    results: list[str] = []
    root = Path(root)
    if not root.is_dir():
        return results
    root_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        if len(current.parts) - root_depth >= max_depth:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(
            d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")
        )
        for filename in sorted(filenames):
            results.append(str(current.joinpath(filename).relative_to(root)))
            if len(results) >= max_files:
                return results
    return results


def summarize_project(root: Path, *, max_files: int = MAX_SCAN_FILES) -> dict:
    """Return a compact, JSON-serialisable summary of a project tree."""
    files = scan_project_files(root, max_files=max_files)
    languages: Counter[str] = Counter()
    for rel in files:
        ext = Path(rel).suffix.lower()
        language = _LANGUAGE_BY_EXT.get(ext)
        if language:
            languages[language] += 1
    return {
        "file_count": len(files),
        "languages": dict(languages.most_common(8)),
        "sample_files": files[:20],
    }
