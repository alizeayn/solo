"""Per-project state store.

Every project owns a metadata directory inside its root
(``<project-root>/.solo`` by default) holding a structured, human-inspectable
representation of that project:

```
.solo/
├── project.json          identity: id, name, origin, timestamps
├── config.json           per-project configuration (tree/memory/session limits)
├── .gitignore            keeps Solo state out of the user's repository
├── state/
│   └── tree.json         the structured project state tree (files + activity)
├── memory/
│   ├── index.json        ordered index of memory entries
│   └── entries/<id>.json one file per memory entry
├── sessions/
│   ├── index.json
│   └── <session-id>.json full transcript of one conversation
└── tasks/
    ├── index.json
    └── <task-id>.json    task, its changed files and its normalised events
```

Design notes
------------
* **The store lives with the project.** Copying or moving a project directory
  carries its Solo state with it, and opening a project on another machine
  restores its history.
* **SQLite remains the fast query index.** The store is the durable, portable
  and inspectable mirror; nothing in the request path depends on parsing files.
* **Writes are atomic** (temp file + ``os.replace``) so an interrupted write
  cannot leave truncated JSON.
* **Sync failures never break a task.** If the project directory becomes
  read-only, the store logs a warning and the application keeps working.
* **Bounded by construction.** File-tree depth, entry counts and the number of
  retained task/session records are all capped.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import Settings
from ..domain import MemoryKind
from ..models import Project
from ..repositories import (
    ConversationRepository,
    EventRepository,
    TaskRepository,
)
from .project_paths import ProjectPathError, resolve_project_root

logger = logging.getLogger(__name__)

#: Version of the on-disk metadata layout.
METADATA_VERSION = 1
#: Version of the generated state tree.
STATE_VERSION = 1

#: Retained detail records (the index always lists everything).
MAX_TASK_RECORDS = 50
MAX_SESSION_RECORDS = 20
MAX_MEMORY_ENTRIES = 500
MAX_EVENTS_PER_TASK_RECORD = 500

#: Directories never included in the file tree.
DEFAULT_EXCLUDES: frozenset[str] = frozenset(
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

METADATA_GITIGNORE = """\
# Solo project state (generated).
#
# Delete this file, or replace the pattern below, if you want to commit your
# project's memory, sessions and task history along with the code.
*
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _write_json(path: Path, payload: Any) -> None:
    """Write JSON atomically so a crash cannot leave a truncated file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _safe_write_json(path: Path, payload: Any) -> bool:
    """Write JSON, logging rather than raising on a read-only project."""
    try:
        _write_json(path, payload)
        return True
    except OSError:
        logger.warning("could not write project metadata: %s", path, exc_info=True)
        return False


def _truncate(text: str, limit: int = 80) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else f"{text[: limit - 1].rstrip()}…"


def _merge_index_nodes(
    previous: list[dict],
    incoming: list[dict],
    meta_dir: Path,
) -> list[dict]:
    """Union freshly derived nodes with detail files already on disk.

    This is what makes a project portable: opening a directory that carries
    Solo state from another installation keeps the task and session entries
    whose detail files still exist, even though the local database does not
    know about them.
    """
    seen = {node.get("id") for node in incoming}
    preserved: list[dict] = []
    for node in previous:
        node_id = node.get("id")
        if not node_id or node_id in seen:
            continue
        ref = node.get("ref")
        if not ref or not (meta_dir / ref).is_file():
            continue
        preserved.append(node)
        seen.add(node_id)
    return [*incoming, *preserved]


# --------------------------------------------------------------------------- #
# Paths and configuration
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StorePaths:
    """Resolved locations inside a project's metadata directory."""

    root: Path
    metadata_dir_name: str

    @property
    def meta(self) -> Path:
        return self.root / self.metadata_dir_name

    @property
    def manifest(self) -> Path:
        return self.meta / "project.json"

    @property
    def config(self) -> Path:
        return self.meta / "config.json"

    @property
    def gitignore(self) -> Path:
        return self.meta / ".gitignore"

    @property
    def state_dir(self) -> Path:
        return self.meta / "state"

    @property
    def tree(self) -> Path:
        return self.state_dir / "tree.json"

    @property
    def memory_dir(self) -> Path:
        return self.meta / "memory"

    @property
    def memory_entries(self) -> Path:
        return self.memory_dir / "entries"

    @property
    def memory_index(self) -> Path:
        return self.memory_dir / "index.json"

    @property
    def sessions_dir(self) -> Path:
        return self.meta / "sessions"

    @property
    def sessions_index(self) -> Path:
        return self.sessions_dir / "index.json"

    @property
    def tasks_dir(self) -> Path:
        return self.meta / "tasks"

    @property
    def tasks_index(self) -> Path:
        return self.tasks_dir / "index.json"


def default_config(settings: Settings) -> dict:
    """Default per-project configuration. ``None`` means "use app defaults"."""
    return {
        "version": 1,
        "tree": {
            "max_depth": None,
            "max_entries": None,
            "exclude": [],
        },
        "memory": {
            "max_entries": MAX_MEMORY_ENTRIES,
            "auto_capture": True,
        },
        "sessions": {
            "max_sessions": MAX_SESSION_RECORDS,
        },
        "state": {
            "auto_refresh": True,
        },
        "agent": {
            "backend": None,
            "provider": None,
            "model": None,
        },
    }


def _deep_merge(base: dict, patch: dict) -> dict:
    """Recursively merge *patch* into a copy of *base*."""
    merged = dict(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


# --------------------------------------------------------------------------- #
# File tree
# --------------------------------------------------------------------------- #
def build_file_tree(
    root: Path,
    *,
    metadata_dir_name: str,
    excludes: set[str],
    max_depth: int,
    max_entries: int,
) -> tuple[dict, bool]:
    """Return ``(root_node, truncated)`` for the project's file tree."""
    skip = set(excludes) | {metadata_dir_name}
    budget = {"used": 0}
    truncated = {"value": False}

    def walk(directory: Path, relative: str, depth: int) -> dict:
        node: dict[str, Any] = {
            "id": f"dir:{relative}" if relative else "dir:",
            "name": directory.name if relative else root.name,
            "kind": "directory",
            "path": relative or ".",
            "children": [],
        }
        if depth >= max_depth:
            truncated["value"] = True
            return node

        try:
            with os.scandir(directory) as iterator:
                raw_entries = list(iterator)
        except OSError:
            return node

        directories: list[os.DirEntry] = []
        files: list[os.DirEntry] = []
        for entry in raw_entries:
            if entry.name in skip:
                continue
            if budget["used"] >= max_entries:
                truncated["value"] = True
                break
            try:
                if entry.is_dir(follow_symlinks=False):
                    directories.append(entry)
                elif entry.is_file(follow_symlinks=False):
                    files.append(entry)
            except OSError:  # pragma: no cover - broken entry
                continue

        directories.sort(key=lambda item: item.name.lower())
        files.sort(key=lambda item: item.name.lower())

        for entry in directories:
            budget["used"] += 1
            child_relative = f"{relative}/{entry.name}" if relative else entry.name
            node["children"].append(
                walk(Path(entry.path), child_relative, depth + 1)
            )

        for entry in files:
            budget["used"] += 1
            child_relative = f"{relative}/{entry.name}" if relative else entry.name
            try:
                size: int | None = entry.stat().st_size
            except OSError:  # pragma: no cover
                size = None
            node["children"].append(
                {
                    "id": f"file:{child_relative}",
                    "name": entry.name,
                    "kind": "file",
                    "path": child_relative,
                    "size": size,
                    "ext": Path(entry.name).suffix.lower() or None,
                }
            )

        return node

    return walk(root, "", 0), truncated["value"]


def _compose_tree(
    project: Project,
    *,
    file_tree: dict,
    file_truncated: bool,
    tasks: list[dict],
    memory: list[dict],
    sessions: list[dict],
) -> dict:
    """Combine file and activity nodes into one structured project state tree."""
    return {
        "version": STATE_VERSION,
        "generated_at": _now(),
        "project": {
            "id": project.id,
            "name": project.name,
            "slug": project.slug,
            "location": project.location,
            "root": project.root_path,
            "metadata_dir": project.metadata_dir,
        },
        "truncated": file_truncated,
        "root": {
            "id": "root",
            "name": project.name,
            "kind": "project",
            "children": [
                {
                    "id": "group:files",
                    "name": "Files",
                    "kind": "group",
                    "children": file_tree.get("children", []),
                },
                {
                    "id": "group:tasks",
                    "name": "Tasks",
                    "kind": "group",
                    "children": tasks,
                },
                {
                    "id": "group:memory",
                    "name": "Memory",
                    "kind": "group",
                    "children": memory,
                },
                {
                    "id": "group:sessions",
                    "name": "Sessions",
                    "kind": "group",
                    "children": sessions,
                },
            ],
        },
    }


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
class ProjectStoreService:
    """Create, read and maintain per-project state."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings

    # -- paths ----------------------------------------------------------- #
    def paths(self, project: Project) -> StorePaths:
        root = resolve_project_root(self._settings, project)
        return StorePaths(
            root=root,
            metadata_dir_name=project.metadata_dir or self._settings.metadata_dir_name,
        )

    # -- lifecycle ------------------------------------------------------- #
    def initialize(self, project: Project, *, origin: str) -> dict:
        """Create (or adopt) the metadata directory for *project*.

        Raises :class:`ProjectPathError` when the project directory is not
        writable, because a project without a store cannot record its state.
        """
        paths = self.paths(project)
        try:
            paths.meta.mkdir(parents=True, exist_ok=True)
            for directory in (
                paths.state_dir,
                paths.memory_entries,
                paths.sessions_dir,
                paths.tasks_dir,
            ):
                directory.mkdir(parents=True, exist_ok=True)

            manifest = _read_json(paths.manifest) or {
                "version": METADATA_VERSION,
                "id": project.id,
                "origin": origin,
                "created_at": _now(),
            }
            manifest.update(
                {
                    "version": METADATA_VERSION,
                    "id": project.id,
                    "name": project.name,
                    "origin": manifest.get("origin", origin),
                    "root": str(paths.root),
                    "updated_at": _now(),
                }
            )
            _write_json(paths.manifest, manifest)

            if not paths.config.exists():
                _write_json(paths.config, default_config(self._settings))
            if not paths.memory_index.exists():
                _write_json(paths.memory_index, {"version": 1, "entries": []})
        except OSError as exc:
            raise ProjectPathError(
                f"cannot write project metadata in {paths.root}: {exc.strerror or exc}"
            ) from exc

        # A missing .gitignore is cosmetic: never fail a project over it.
        if self._settings.metadata_write_gitignore and not paths.gitignore.exists():
            try:
                paths.gitignore.write_text(METADATA_GITIGNORE, encoding="utf-8")
            except OSError:  # pragma: no cover - read-only edge case
                logger.debug("could not write metadata .gitignore", exc_info=True)
        return manifest

    def read_manifest(self, project: Project) -> dict | None:
        return _read_json(self.paths(project).manifest)

    def read_manifest_at(self, root: Path) -> dict | None:
        """Read the manifest for a raw directory, without a Project record."""
        return _read_json(
            root / self._settings.metadata_dir_name / "project.json"
        )

    def read_config(self, project: Project) -> dict:
        stored = _read_json(self.paths(project).config, {}) or {}
        return _deep_merge(default_config(self._settings), stored)

    def write_config(self, project: Project, patch: dict) -> dict:
        merged = _deep_merge(self.read_config(project), patch)
        merged["version"] = 1
        _write_json(self.paths(project).config, merged)
        return merged

    # -- memory ---------------------------------------------------------- #
    def list_memory(self, project: Project, *, limit: int = 200) -> list[dict]:
        entries = (_read_json(self.paths(project).memory_index, {}) or {}).get(
            "entries", []
        )
        return list(reversed(entries))[:limit]

    async def add_memory(
        self,
        project: Project,
        *,
        text: str,
        kind: str = MemoryKind.NOTE.value,
        tags: list[str] | None = None,
        source: str = "user",
        task_id: str | None = None,
    ) -> dict:
        import uuid

        paths = self.paths(project)
        config = self.read_config(project)
        limit = int(config.get("memory", {}).get("max_entries") or MAX_MEMORY_ENTRIES)

        index = _read_json(paths.memory_index, {"version": 1, "entries": []}) or {
            "version": 1,
            "entries": [],
        }
        entry = {
            "id": uuid.uuid4().hex,
            "kind": kind,
            "text": text.strip(),
            "tags": [tag for tag in (tags or []) if tag],
            "source": source,
            "task_id": task_id,
            "created_at": _now(),
        }
        _write_json(paths.memory_entries / f"{entry['id']}.json", entry)

        entries = list(index.get("entries", []))
        entries.append(entry)
        index["entries"] = entries[-limit:]
        index["updated_at"] = _now()
        _write_json(paths.memory_index, index)
        return entry

    def delete_memory(self, project: Project, entry_id: str) -> bool:
        paths = self.paths(project)
        index = _read_json(paths.memory_index, {"version": 1, "entries": []}) or {
            "version": 1,
            "entries": [],
        }
        entries = [item for item in index.get("entries", []) if item.get("id") != entry_id]
        if len(entries) == len(index.get("entries", [])):
            return False
        index["entries"] = entries
        index["updated_at"] = _now()
        _write_json(paths.memory_index, index)
        try:
            (paths.memory_entries / f"{entry_id}.json").unlink(missing_ok=True)
        except OSError:  # pragma: no cover
            logger.debug("could not remove memory entry file", exc_info=True)
        return True

    # -- detail records -------------------------------------------------- #
    async def record_task(self, project: Project, task_id: str) -> dict | None:
        """Write ``tasks/<id>.json`` for one task, with files and events."""
        paths = self.paths(project)
        async with self._session_factory() as session:
            tasks = TaskRepository(session)
            task = await tasks.get(task_id)
            if task is None:
                return None
            files = await tasks.list_files(task_id)
            events = await EventRepository(session).list_for_task(
                task_id, limit=MAX_EVENTS_PER_TASK_RECORD
            )
            record = {
                "id": task.id,
                "task_type": task.task_type,
                "status": task.status,
                "instruction": task.instruction,
                "progress_summary": task.progress_summary,
                "result_summary": task.result_summary,
                "error": task.error,
                "created_at": _iso(task.created_at),
                "updated_at": _iso(task.updated_at),
                "completed_at": _iso(task.completed_at),
                "files": [
                    {"path": item.path, "change_type": item.change_type}
                    for item in files
                ],
                "events": [
                    {
                        "id": event.id,
                        "type": event.type,
                        "message": event.message,
                        "data": event.data,
                        "created_at": _iso(event.created_at),
                    }
                    for event in events
                ],
            }
        _safe_write_json(paths.tasks_dir / f"{task_id}.json", record)
        return record

    async def record_session(
        self, project: Project, conversation_id: str
    ) -> dict | None:
        """Write ``sessions/<id>.json``: the full transcript of a conversation."""
        paths = self.paths(project)
        async with self._session_factory() as session:
            conversations = ConversationRepository(session)
            conversation = await conversations.get(conversation_id)
            if conversation is None:
                return None
            messages = await conversations.list_messages(conversation_id, limit=1000)
            record = {
                "id": conversation.id,
                "title": conversation.title,
                "created_at": _iso(conversation.created_at),
                "updated_at": _iso(conversation.updated_at),
                "messages": [
                    {
                        "id": message.id,
                        "role": message.role,
                        "content": message.content,
                        "task_id": message.task_id,
                        "created_at": _iso(message.created_at),
                    }
                    for message in messages
                ],
            }
        _safe_write_json(paths.sessions_dir / f"{conversation_id}.json", record)
        return record

    # -- tree ------------------------------------------------------------ #
    async def get_tree(self, project: Project, *, refresh: bool = False) -> dict:
        paths = self.paths(project)
        if not refresh:
            cached = _read_json(paths.tree)
            if isinstance(cached, dict) and cached.get("root"):
                return cached
        return await self.refresh(project)

    async def refresh(self, project: Project) -> dict:
        """Rebuild ``state/tree.json`` and the index files from live state."""
        paths = self.paths(project)
        config = self.read_config(project)
        tree_config = config.get("tree", {})

        excludes = set(DEFAULT_EXCLUDES) | set(tree_config.get("exclude") or [])
        file_tree, file_truncated = build_file_tree(
            paths.root,
            metadata_dir_name=paths.metadata_dir_name,
            excludes=excludes,
            max_depth=int(tree_config.get("max_depth") or self._settings.max_tree_depth),
            max_entries=int(
                tree_config.get("max_entries") or self._settings.max_tree_entries
            ),
        )

        async with self._session_factory() as session:
            tasks = await TaskRepository(session).list(
                project_id=project.id, limit=MAX_TASK_RECORDS
            )
            conversations = await ConversationRepository(session).list_for_project(
                project.id
            )
            conversations_repo = ConversationRepository(session)
            message_counts = {
                conversation.id: await conversations_repo.message_count(conversation.id)
                for conversation in conversations
            }

        db_task_nodes = [
            {
                "id": f"task:{task.id}",
                "name": _truncate(task.instruction),
                "kind": "task",
                "status": task.status,
                "task_type": task.task_type,
                "updated_at": _iso(task.updated_at),
                "ref": f"tasks/{task.id}.json",
            }
            for task in tasks
        ]
        task_nodes = self._merge_index_nodes(
            project, paths.tasks_index, db_task_nodes, "tasks"
        )

        memory_entries = self.list_memory(project, limit=MAX_MEMORY_ENTRIES)
        memory_nodes = [
            {
                "id": f"memory:{entry['id']}",
                "name": _truncate(entry.get("text", "")),
                "kind": "memory",
                "memory_kind": entry.get("kind"),
                "created_at": entry.get("created_at"),
                "ref": f"memory/entries/{entry['id']}.json",
            }
            for entry in memory_entries
        ]

        session_nodes = [
            {
                "id": f"session:{conversation.id}",
                "name": conversation.title or "Session",
                "kind": "session",
                "messages": message_counts.get(conversation.id, 0),
                "updated_at": _iso(conversation.updated_at),
                "ref": f"sessions/{conversation.id}.json",
            }
            for conversation in conversations[:MAX_SESSION_RECORDS]
        ]
        session_nodes = self._merge_index_nodes(
            project, paths.sessions_index, session_nodes, "sessions"
        )

        tree = _compose_tree(
            project,
            file_tree=file_tree,
            file_truncated=file_truncated,
            tasks=task_nodes,
            memory=memory_nodes,
            sessions=session_nodes,
        )

        _safe_write_json(paths.tree, tree)
        _safe_write_json(
            paths.tasks_index,
            {"version": 1, "updated_at": _now(), "tasks": task_nodes},
        )
        _safe_write_json(
            paths.sessions_index,
            {"version": 1, "updated_at": _now(), "sessions": session_nodes},
        )
        manifest = _read_json(paths.manifest, {}) or {}
        manifest["updated_at"] = _now()
        manifest["id"] = project.id
        manifest["name"] = project.name
        _safe_write_json(paths.manifest, manifest)
        return tree

    def _merge_index_nodes(
        self,
        project: Project,
        index_path: Path,
        incoming: list[dict],
        key: str,
    ) -> list[dict]:
        """Union DB-derived index nodes with detail files already on disk."""
        previous = list((_read_json(index_path, {}) or {}).get(key, []))
        return _merge_index_nodes(previous, incoming, self.paths(project).meta)

    # -- summary --------------------------------------------------------- #
    async def summary(self, project: Project, *, refresh: bool = False) -> dict:
        """Compact, JSON-safe description of a project's stored state."""
        paths = self.paths(project)
        config = self.read_config(project)

        excludes = set(DEFAULT_EXCLUDES) | set(config.get("tree", {}).get("exclude") or [])
        file_tree, _ = build_file_tree(
            paths.root,
            metadata_dir_name=paths.metadata_dir_name,
            excludes=excludes,
            max_depth=int(config.get("tree", {}).get("max_depth") or self._settings.max_tree_depth),
            max_entries=int(
                config.get("tree", {}).get("max_entries") or self._settings.max_tree_entries
            ),
        )

        def count(node: dict) -> tuple[int, int]:
            files = directories = 0
            for child in node.get("children", []):
                if child.get("kind") == "directory":
                    directories += 1
                    sub_files, sub_dirs = count(child)
                    files += sub_files
                    directories += sub_dirs
                else:
                    files += 1
            return files, directories

        file_count, directory_count = count(file_tree)

        async with self._session_factory() as session:
            tasks = await TaskRepository(session).list(project_id=project.id, limit=500)
            conversations = await ConversationRepository(session).list_for_project(
                project.id
            )

        status_counts: dict[str, int] = {}
        for task in tasks:
            status_counts[task.status] = status_counts.get(task.status, 0) + 1

        return {
            "project_id": project.id,
            "name": project.name,
            "location": project.location,
            "root": str(paths.root),
            "metadata_dir": str(paths.meta),
            "metadata_exists": paths.manifest.is_file(),
            "file_count": file_count,
            "directory_count": directory_count,
            "task_count": len(tasks),
            "task_status_counts": status_counts,
            "session_count": len(conversations),
            "memory_count": len(self.list_memory(project, limit=10_000)),
            "tree_generated_at": (_read_json(paths.tree, {}) or {}).get("generated_at"),
            "config": config,
        }
