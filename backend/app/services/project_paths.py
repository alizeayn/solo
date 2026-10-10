"""Filesystem policy for projects and the "Open Project" browser.

Security model
--------------
Solo can run a coding agent against a project, so a project root is a
*trust boundary*. This module is the single place that decides whether a path
may be used, and it is deliberately paranoid:

* The path is always resolved to its real location (symlinks followed) before
  any check, so a link cannot be used to escape a rule.
* A set of system directories is **always** rejected, on every deployment.
* The Solo data directory is always rejected: it holds the master encryption
  key and the encrypted secrets store, and must never be inside a project that
  the agent can edit.
* ``allow_any_project_path`` (default) mirrors the local-first, single-user
  design: any other readable directory is permitted. Setting it to ``False``
  restricts opening to ``PROJECT_ROOTS`` plus the home directory and the
  managed workspaces directory — the right setting for a shared or
  internet-facing deployment.
* When an opened project's metadata directory already contains a
  ``project.json``, its recorded absolute path must still match, so moving or
  swapping a directory does not silently attach the wrong history.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..config import Settings
from ..domain import ProjectLocation
from ..models import Project

#: Directories that are never valid project roots on POSIX systems.
_BLOCKED_POSIX: tuple[str, ...] = (
    "/proc",
    "/sys",
    "/dev",
    "/etc",
    "/boot",
    "/run",
    "/root",
    "/var/lib/docker",
    "/var/lib/solo",
)

#: Maximum directory entries returned by one browse request.
MAX_BROWSE_ENTRIES = 500


class ProjectPathError(ValueError):
    """Raised when a path may not be opened or browsed."""


# --------------------------------------------------------------------------- #
# Policy
# --------------------------------------------------------------------------- #
def blocked_roots(settings: Settings) -> list[Path]:
    """Directories (and their subtrees) that are never allowed."""
    blocked: list[Path] = []
    if os.name == "posix":
        blocked.extend(Path(item) for item in _BLOCKED_POSIX)
    # The Solo data directory contains the encryption key and the secrets store.
    blocked.append(settings.app_data_dir.expanduser().resolve())
    return blocked


def is_blocked(settings: Settings, path: Path) -> bool:
    """Return True if *path* is, or is inside, a blocked directory."""
    try:
        resolved = path.expanduser().resolve()
    except OSError:  # pragma: no cover - unresolvable path
        return True
    for blocked in blocked_roots(settings):
        if resolved == blocked or blocked in resolved.parents:
            return True
    return False


def default_browse_root(settings: Settings) -> Path:
    """Where the Open Project browser starts: the user's home directory."""
    home = Path.home()
    if home.is_dir() and not is_blocked(settings, home):
        return home.resolve()
    return settings.workspaces_dir.resolve()


def allowed_roots(settings: Settings) -> list[Path]:
    """Every root that may be browsed, in priority order, de-duplicated."""
    candidates = [
        default_browse_root(settings),
        settings.workspaces_dir.resolve(),
        *settings.configured_project_roots,
    ]
    ordered: list[Path] = []
    for candidate in candidates:
        if candidate not in ordered:
            ordered.append(candidate)
    return ordered


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def resolve_directory(settings: Settings, raw: str | None) -> Path:
    """Resolve a user-supplied directory, enforcing every policy rule."""
    if raw is None or not str(raw).strip():
        return default_browse_root(settings)

    candidate = Path(str(raw)).expanduser()
    if not candidate.is_absolute():
        candidate = default_browse_root(settings) / candidate

    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ProjectPathError(f"path does not exist: {raw}") from exc

    if not resolved.is_dir():
        raise ProjectPathError(f"not a directory: {raw}")
    if is_blocked(settings, resolved):
        raise ProjectPathError("that location is not allowed")
    if not settings.allow_any_project_path and not any(
        _is_within(resolved, root) for root in allowed_roots(settings)
    ):
        raise ProjectPathError(
            "that location is outside the allowed project roots"
        )
    return resolved


def resolve_project_root(settings: Settings, project: Project) -> Path:
    """Resolve a project's absolute root from its stored location.

    Managed projects are confined to the workspaces directory; external
    projects are absolute paths that must still satisfy the path policy.
    """
    if project.location == ProjectLocation.EXTERNAL.value:
        root = Path(project.root_path).expanduser()
        try:
            root = root.resolve(strict=False)
        except OSError as exc:  # pragma: no cover - unresolvable path
            raise ProjectPathError(f"project root is unusable: {exc}") from exc
        if is_blocked(settings, root):
            raise ProjectPathError("project root points at a disallowed location")
        return root

    base = settings.workspaces_dir.resolve()
    candidate = (base / project.root_path).resolve()
    if not _is_within(candidate, base):
        raise ProjectPathError(
            "project root escapes the managed workspaces directory"
        )
    return candidate


# --------------------------------------------------------------------------- #
# Browsing
# --------------------------------------------------------------------------- #
def metadata_path(settings: Settings, root: Path) -> Path:
    """Path to a project's metadata directory for a given root."""
    return root / settings.metadata_dir_name


def has_project_metadata(settings: Settings, root: Path) -> bool:
    """True when *root* contains an initialised Solo project store."""
    return (metadata_path(settings, root) / "project.json").is_file()


def list_directory(settings: Settings, raw: str | None) -> dict:
    """List the sub-directories of *raw* (or the default root) for the UI."""
    directory = resolve_directory(settings, raw)

    entries: list[dict] = []
    truncated = False
    try:
        with os.scandir(directory) as iterator:
            for entry in iterator:
                if len(entries) >= MAX_BROWSE_ENTRIES:
                    truncated = True
                    break
                child = Path(entry.path)
                try:
                    is_dir = entry.is_dir(follow_symlinks=True)
                except OSError:  # pragma: no cover - broken link
                    continue
                if not is_dir or is_blocked(settings, child):
                    continue
                entries.append(
                    {
                        "name": entry.name,
                        "path": str(child),
                        "hidden": entry.name.startswith("."),
                        "is_project": has_project_metadata(settings, child),
                    }
                )
    except PermissionError as exc:
        raise ProjectPathError("permission denied") from exc

    # Visible directories first, then hidden, each alphabetically.
    entries.sort(key=lambda item: (item["hidden"], item["name"].lower()))

    parent = directory.parent
    if parent == directory or is_blocked(settings, parent):
        parent = None

    return {
        "path": str(directory),
        "parent": str(parent) if parent is not None else None,
        "roots": [str(root) for root in allowed_roots(settings)],
        "entries": entries,
        "truncated": truncated,
    }
