"""Single source of truth for Solo's version.

The version lives in a ``VERSION`` file at the repository root so the shell
installer, the updater and the application all agree without parsing Python.

Semantic versioning, applied as:

* **MAJOR** — an incompatible change to stored data or configuration that needs
  manual action.
* **MINOR** — a new phase or feature (a new capability the user can use).
* **PATCH** — fixes and internal changes with no user-visible surface change.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

#: Used when the VERSION file cannot be found (e.g. an unusual packaging layout).
FALLBACK_VERSION = "0.0.0"

_SEMVER = re.compile(r"^\d+\.\d+\.\d+([-+].*)?$")


def version_file_candidates() -> list[Path]:
    """Places the VERSION file may live, most specific first.

    ``backend/app/version.py`` → ``parents[2]`` is the repository root in a
    checkout, and ``/app`` in the container image (where the file is copied).
    """
    here = Path(__file__).resolve()
    return [here.parents[2] / "VERSION", here.parents[1] / "VERSION"]


@lru_cache(maxsize=1)
def read_version() -> str:
    """Return Solo's version, or :data:`FALLBACK_VERSION`."""
    for candidate in version_file_candidates():
        try:
            raw = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if raw:
            return raw
    return FALLBACK_VERSION


def parse_version(value: str) -> tuple[int, int, int, str]:
    """Parse a version into ``(major, minor, patch, prerelease)``.

    Unparseable values sort lowest so a malformed version never looks newer.
    """
    candidate = (value or "").strip()
    if not _SEMVER.match(candidate):
        return (0, 0, 0, candidate or "unknown")
    core, _, suffix = candidate.partition("-")
    major, minor, patch = (int(part) for part in core.split("."))
    return (major, minor, patch, suffix)


def is_newer(candidate: str, current: str) -> bool:
    """True when *candidate* is a newer version than *current*."""
    return parse_version(candidate) > parse_version(current)


def describe_change(previous: str, current: str) -> str:
    """A short, human description of how the version changed."""
    old = parse_version(previous)
    new = parse_version(current)
    if old == new:
        return "no version change"
    if new[0] != old[0]:
        return f"major update {previous} → {current}"
    if new[1] != old[1]:
        return f"feature update {previous} → {current}"
    return f"patch update {previous} → {current}"
