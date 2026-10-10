# 12 — Project Model Implementation

**Stage:** Implementation
**Date:** 2026-10-10

---

## 1. Summary

A project is now **a directory on disk** with a Solo state store inside it,
rather than only a row in the database.

| Operation | Behaviour | Copies files |
|---|---|---|
| **Create Project** | New folder (managed workspaces folder, or a chosen parent), initialised with `.solo/` | n/a |
| **Open Project** | Existing folder adopted **in place**; only `.solo/` is added | **No** |
| **Import ZIP** | Archive extracted into the managed workspaces folder | Yes |

---

## 2. New and changed backend modules

### New

| Module | Lines | Responsibility |
|---|---|---|
| `services/project_paths.py` | ~250 | **The only place a path is judged.** Blocked set, allow-list, symlink-safe resolution, managed/external root resolution, directory listing |
| `services/project_store.py` | ~720 | The `.solo/` store: manifest, config, memory, sessions, task records, index union, state tree, summary |
| `api/fs.py` | ~40 | Directory listing endpoint for the Open Project browser |

### Changed

| Module | Change |
|---|---|
| `models.py` | `Project` gains `location` (`managed`/`external`) and `metadata_dir`; `root_path` widened to 1024 chars and now means "slug when managed, absolute path when external" |
| `domain.py` | `ProjectSource` → `created`/`opened`/`imported`; new `ProjectLocation` and `MemoryKind` enums |
| `config.py` | `metadata_dir_name`, `project_roots`, `allow_any_project_path`, `max_tree_depth`, `max_tree_entries`, `metadata_write_gitignore` |
| `repositories/projects.py` | `create()` takes `location`, `metadata_dir`, `project_id`; new `find_by_root()` |
| `repositories/conversations.py` | New `list_for_project()` and `message_count()` |
| `services/project_service.py` | Rewritten: `create(parent=…)`, `open_existing()`, `import_zip()`, location-aware `delete()` |
| `services/orchestrator.py` | New `_sync_project_store()`; writes the finished task **before** broadcasting the terminal status; records sessions on message; refreshes the tree on task start/settle |
| `api/projects.py` | Rewritten: `POST /open`, tree/summary/config/memory endpoints, `remove_files` on delete |
| `schemas.py` | `ProjectOut` gains `location`/`root`/`metadata_dir`/`is_managed`; new tree, memory, config, summary and filesystem schemas |
| `container.py` | Wires `ProjectStoreService` and injects it into `ProjectService` and `OrchestratorService` |

The previous `services/archive.py` (ZIP safety) and `services/project_scan.py`
(bounded scanning) were reused unchanged — the new store composes them.

---

## 3. The `.solo` state store

```
<project-root>/.solo/
├── project.json          identity: id, name, origin, root, timestamps
├── config.json           per-project configuration (deep-merged)
├── .gitignore            hides Solo state from git by default
├── state/tree.json       the structured project state tree
├── memory/index.json + memory/entries/<id>.json
├── sessions/index.json + sessions/<id>.json
└── tasks/index.json    + tasks/<id>.json
```

### Four properties that mattered

**Portability.** `project.json` carries an `id`, and opening a folder that
already has one **adopts** it (unless another project claims it). `refresh()`
**unions** task and session index nodes derived from the live database with
nodes already on disk whose detail files exist. Opening a project from another
installation — where the local database knows nothing about those tasks —
therefore keeps its history instead of erasing the index. Two tests cover this
directly (`test_refresh_preserves_records_written_by_another_installation`,
`test_refresh_drops_index_entries_whose_detail_file_is_gone`).

**Atomicity.** Every write is temp-file + `os.replace`, so an interrupted write
cannot leave truncated JSON.

**Never breaking work.** `initialize()` fails loudly (a project without a store
cannot record anything) with a clear `cannot write project metadata` message,
while later syncs use `_safe_write_json` and log a warning. A project folder
that becomes read-only does not stop a task.

**Observability ordering.** A finished task is written to disk *before* its
terminal status is published on the WebSocket, so a UI that shows "completed"
can always read the record.

### The state tree

One structure holding the file tree plus activity as labelled branches:

```
project
├── Files      directory/file nodes (bounded, exclusion-aware)
├── Tasks      status, type, ref → tasks/<id>.json
├── Memory     kind, ref → memory/entries/<id>.json
└── Sessions   message count, ref → sessions/<id>.json
```

Nodes reference detail files rather than duplicating them, keeping the tree an
index. Bounds: depth 10, 5 000 entries, 50 task records, 20 session records, 500
events per task, 500 memory entries — all configurable per project.

Excluded by default: `.git`, `node_modules`, `venv`, `.venv`, `__pycache__`,
`dist`, `build`, `.next`, `.idea`, `.vscode`, `.mypy_cache`, `.pytest_cache`,
`.ruff_cache`, `target`, `vendor`, plus the metadata directory itself.

---

## 4. The path policy

Aggregated into one module with a documented five-step order:

1. resolve fully (symlinks followed) **before** any check;
2. must exist and be a directory;
3. always-blocked: `/proc`, `/sys`, `/dev`, `/etc`, `/boot`, `/run`, `/root`,
   `/var/lib/docker`, `/var/lib/solo`, and the Solo `data/` directory;
4. optional allow-list (`ALLOW_ANY_PROJECT_PATH=false` + `PROJECT_ROOTS`);
5. managed projects additionally confined to the workspaces directory, and
   rejected if they resolve outside it.

The blocked set is *not* bypassable by configuration, so a misconfiguration
cannot expose `/etc` or the master key.

---

## 5. Frontend

### New components

| Component | Purpose |
|---|---|
| `components/DirectoryBrowser.tsx` | Server-side directory picker: navigation, parent, root jump, typed path, blocked-path errors. Reports a selection only on explicit navigation |
| `panels/ProjectStatePanel.tsx` | Inspector view of the state tree (collapsible), memory (add/delete) and per-project configuration (tree depth/entries/exclusions, memory limits, session retention, auto-refresh) |

### Changed

| Component | Change |
|---|---|
| `ProjectDialog.tsx` | Three tabs — **Create Project / Open Project / Import ZIP**. Create offers the managed folder or a chosen parent; Open explains that nothing is copied and uses the browser; no duplicate path input that could fight the browser |
| `Header.tsx` | Separate **+ Create Project** and **Open Project** actions; an "in place" chip for externally opened projects |
| `WorkspaceView.tsx` | Dialog state carries the initial tab; the empty state explains the Create/Open distinction |
| `InspectorPanel.tsx` | Two views: **Task** and **Project state** |
| `api/client.ts`, `types.ts` | New endpoints and types (tree, memory, config, summary, filesystem listing, open, `remove_files`) |
| `styles.css` | Tree, browser, stat grid, memory and config styles |

---

## 6. Naming

Renamed to **Solo** consistently:

| Artefact | Before | After |
|---|---|---|
| README title | Voice-First AI Workspace | **Solo** (voice-first as the tagline) |
| FastAPI title / dev root | Voice-First AI Workspace | `Solo` / `Solo API` |
| `backend/app/__init__.py` docstring | Voice-First… | `Solo — backend application package.` |
| `backend/pyproject.toml` name | `solo-backend` | `solo` |
| `frontend/package.json` name | `solo-frontend` | `solo` |
| `index.html` title | Voice-First AI Workspace | `Solo — voice-first AI workspace` |
| UI brand (header) | Voice-First Workspace | `Solo` |
| Login heading | Voice-First AI Workspace | `Solo` |
| Docker image / container | `solo-workspace:local` | `solo:local` / `solo` |
| Installer banner | Voice-First AI Workspace | `Solo` |
| Docker volume | `solo-data` | unchanged (avoids orphaning existing data) |
| Cookie name | `solo_session` | unchanged |

`PROJECT_SPEC.md` was left verbatim: it is the requirements document, not
product output.
