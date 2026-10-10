"""Safe ZIP extraction for project import.

Threat model
------------
An uploaded archive is untrusted. We defend against:

* **Zip Slip / path traversal** — entry names containing ``..`` or absolute
  paths, and any resolved destination that escapes the target directory.
* **Symlinks** — entries whose Unix mode marks them as symbolic links are
  rejected outright, so a link cannot point outside the workspace.
* **Decompression bombs** — enforced limits on entry count and total
  uncompressed size.
* **Device/special files** — only regular files and directories are written.

Nothing here executes project content; extraction is purely file I/O.
"""

from __future__ import annotations

import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

from ..config import Settings


class ArchiveError(ValueError):
    """Raised when an archive is malformed or unsafe to extract."""


def _safe_member_path(base: Path, member_name: str) -> Path:
    """Resolve *member_name* under *base*, rejecting escapes."""
    # Normalise backslashes so Windows-authored archives cannot smuggle paths.
    normalised = member_name.replace("\\", "/")
    if normalised.startswith("/"):
        raise ArchiveError(f"unsafe absolute path in archive: {member_name!r}")
    pure = PurePosixPath(normalised)
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        raise ArchiveError(f"unsafe path in archive: {member_name!r}")
    # Reject drive-letter style prefixes (e.g. "C:/...").
    if pure.parts and ":" in pure.parts[0]:
        raise ArchiveError(f"unsafe path in archive: {member_name!r}")

    target = (base / Path(*pure.parts)).resolve()
    base_resolved = base.resolve()
    if base_resolved != target and base_resolved not in target.parents:
        raise ArchiveError(f"path escapes workspace: {member_name!r}")
    return target


def _common_root(names: list[str]) -> str | None:
    """Return the single shared top-level directory of *names*, if any."""
    roots: set[str] = set()
    for name in names:
        parts = PurePosixPath(name.replace("\\", "/").lstrip("/")).parts
        if not parts:
            continue
        roots.add(parts[0])
        if len(roots) > 1:
            return None
    if len(roots) != 1:
        return None
    root = next(iter(roots))
    if root in {".", ".."} or ":" in root:
        return None
    # Only strip when every entry actually lives under that directory.
    for name in names:
        parts = PurePosixPath(name.replace("\\", "/").lstrip("/")).parts
        if len(parts) < 2:
            return None
    return root


def safe_extract_zip(
    zip_path: Path,
    dest: Path,
    *,
    settings: Settings | None = None,
    max_entries: int | None = None,
    max_uncompressed_bytes: int | None = None,
    strip_single_root: bool = True,
) -> int:
    """Extract *zip_path* into *dest* safely.

    Returns the number of regular files written. Raises :class:`ArchiveError`
    on any safety violation.
    """
    settings = settings or Settings()
    max_entries = max_entries if max_entries is not None else settings.max_zip_entries
    max_bytes = (
        max_uncompressed_bytes
        if max_uncompressed_bytes is not None
        else settings.max_uncompressed_bytes
    )

    if not zip_path.exists():
        raise ArchiveError("archive not found")
    if not zipfile.is_zipfile(zip_path):
        raise ArchiveError("uploaded file is not a valid ZIP archive")

    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as archive:
        infos = archive.infolist()
        if len(infos) > max_entries:
            raise ArchiveError(
                f"archive contains too many entries ({len(infos)} > {max_entries})"
            )

        total = sum(info.file_size for info in infos)
        if total > max_bytes:
            raise ArchiveError(
                f"archive expands to too much data ({total} > {max_bytes} bytes)"
            )

        # Validate every entry name before any root-stripping happens, so a
        # "../" prefix can never be disguised as a wrapping directory.
        for info in infos:
            _safe_member_path(dest, info.filename)

        # Detect (and optionally strip) a single wrapping directory.
        root = _common_root([i.filename for i in infos]) if strip_single_root else None

        written = 0
        for info in infos:
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ArchiveError(f"archive contains a symlink: {info.filename!r}")
            if info.is_dir():
                continue

            name = info.filename
            if root is not None:
                parts = PurePosixPath(name.replace("\\", "/").lstrip("/")).parts
                name = "/".join(parts[1:])
                if not name:
                    continue

            target = _safe_member_path(dest, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, open(target, "wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 256)
            written += 1

    return written
