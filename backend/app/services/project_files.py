"""Safe file read/write/upload inside a project.

The Writing panel and the file-upload tile need to touch real project files, so
this is a **security boundary** like the ZIP extractor: every path is resolved
inside the project root, symlinks are followed and re-checked, sizes are capped,
and nothing is ever executed.

Deliberately narrow:

* text only, and only for reading (a binary file is reported, not returned);
* a maximum write size, so a mistaken paste cannot fill the disk;
* the project's own metadata directory (``.solo``) is never writable, so the
  state store cannot be corrupted from the UI.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from ..models import Project
from .project_paths import ProjectPathError, resolve_project_root

logger = logging.getLogger(__name__)

#: Largest file the editor will read back.
MAX_READ_BYTES = 512 * 1024
#: Largest single write accepted from the editor.
MAX_WRITE_BYTES = 1024 * 1024
#: Largest single uploaded file.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
#: Directories that may never be written through the API.
PROTECTED_DIRS = frozenset({".git"})


class ProjectFileError(ValueError):
    """Raised for an unsafe or unsupported file operation."""


@dataclass
class FileContent:
    path: str
    content: str
    size: int
    truncated: bool
    binary: bool


def _safe_target(root: Path, relative: str, *, metadata_dir: str = ".solo") -> Path:
    """Resolve *relative* inside *root*, rejecting anything that escapes."""
    cleaned = (relative or "").strip().replace("\\", "/")
    if not cleaned:
        raise ProjectFileError("a file path is required")
    if cleaned.startswith("/"):
        raise ProjectFileError("absolute paths are not allowed")
    parts = [part for part in cleaned.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ProjectFileError("path traversal is not allowed")
    if not parts:
        raise ProjectFileError("a file path is required")

    root_resolved = root.resolve()
    # The metadata directory holds Solo's own state; never let the UI write it.
    if parts[0] == metadata_dir:
        raise ProjectFileError("the project metadata directory is not writable here")
    if parts[0] in PROTECTED_DIRS:
        raise ProjectFileError(f"'{parts[0]}' is not writable here")

    candidate = (root_resolved / Path(*parts)).resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise ProjectFileError("the path escapes the project directory")
    return candidate


class ProjectFileService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def root(self, project: Project) -> Path:
        return resolve_project_root(self._settings, project)

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def read(self, project: Project, relative: str) -> FileContent:
        root = self.root(project)
        target = _safe_target(root, relative, metadata_dir=self._settings.metadata_dir_name)
        if not target.is_file():
            raise ProjectFileError(f"'{relative}' is not a file in this project")

        size = target.stat().st_size
        raw = target.read_bytes()[:MAX_READ_BYTES]
        truncated = size > len(raw)
        if b"\x00" in raw:
            return FileContent(
                path=str(target.relative_to(root)),
                content="",
                size=size,
                truncated=truncated,
                binary=True,
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return FileContent(
                path=str(target.relative_to(root)),
                content="",
                size=size,
                truncated=truncated,
                binary=True,
            )
        return FileContent(
            path=str(target.relative_to(root)),
            content=text,
            size=size,
            truncated=truncated,
            binary=False,
        )

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #
    def write(
        self,
        project: Project,
        relative: str,
        content: str,
        *,
        overwrite: bool = True,
    ) -> FileContent:
        root = self.root(project)
        target = _safe_target(root, relative, metadata_dir=self._settings.metadata_dir_name)
        payload = content.encode("utf-8")
        if len(payload) > MAX_WRITE_BYTES:
            raise ProjectFileError(
                f"content exceeds the {MAX_WRITE_BYTES // 1024} KB editor limit"
            )
        if target.exists() and not overwrite:
            raise ProjectFileError(f"'{relative}' already exists")

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Atomic replace, so an interrupted save cannot truncate the file.
            temporary = target.with_name(f".{target.name}.solo-tmp")
            temporary.write_bytes(payload)
            os.replace(temporary, target)
        except OSError as exc:
            raise ProjectFileError(
                f"could not write '{relative}': {exc.strerror or exc}"
            ) from exc

        return FileContent(
            path=str(target.relative_to(root)),
            content=content,
            size=len(payload),
            truncated=False,
            binary=False,
        )

    # ------------------------------------------------------------------ #
    # Upload
    # ------------------------------------------------------------------ #
    def save_upload(
        self,
        project: Project,
        relative: str,
        source: Path,
        *,
        overwrite: bool = True,
    ) -> FileContent:
        """Move an already-received upload into the project."""
        root = self.root(project)
        target = _safe_target(root, relative, metadata_dir=self._settings.metadata_dir_name)
        size = source.stat().st_size
        if size > MAX_UPLOAD_BYTES:
            raise ProjectFileError(
                f"'{relative}' exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit"
            )
        if target.exists() and not overwrite:
            raise ProjectFileError(f"'{relative}' already exists")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
        except OSError as exc:
            raise ProjectFileError(
                f"could not store '{relative}': {exc.strerror or exc}"
            ) from exc

        return FileContent(
            path=str(target.relative_to(root)),
            content="",
            size=size,
            truncated=False,
            binary=True,
        )


def safe_upload_name(filename: str) -> str:
    """Reduce a browser-supplied filename to a bare, safe name."""
    base = os.path.basename((filename or "").replace("\\", "/")).strip()
    if base in ("", ".", ".."):
        raise ProjectFileError("the uploaded file has no usable name")
    if base.startswith("."):
        raise ProjectFileError("hidden file names are not accepted")
    return base


__all__ = [
    "FileContent",
    "MAX_READ_BYTES",
    "MAX_UPLOAD_BYTES",
    "MAX_WRITE_BYTES",
    "PROTECTED_DIRS",
    "ProjectFileError",
    "ProjectFileService",
    "ProjectPathError",
    "safe_upload_name",
]
