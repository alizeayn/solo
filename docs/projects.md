# The Solo project model

Solo is built around the idea that a *project* is a **folder on your disk**, not
a row in someone else's database. This document explains how projects are
created, opened, and how their state is stored and managed.

---

## 1. Three ways in

| Operation | What happens | Copies files? |
|---|---|---|
| **Create Project** | A new folder is created (in Solo's managed workspaces folder, or at a parent you choose) and initialised with a `.solo/` state directory. | No source to copy |
| **Open Project** | An existing folder is adopted **where it already is**. Solo reads it in place and adds only a `.solo/` directory. | **No** |
| **Import ZIP** | An archive is extracted into Solo's managed workspaces folder. | Yes (by definition) |

The distinction matters because the first two respect your existing layout.
Open Project is the primary workflow for real work: your repository stays where
your editor, git remote, tooling and muscle memory expect it.

---

## 2. Where decision-making lives

| Concern | Module |
|---|---|
| May this path be used at all? | `backend/app/services/project_paths.py` |
| Create / open / import / delete | `backend/app/services/project_service.py` |
| The `.solo/` state store | `backend/app/services/project_store.py` |
| Filesystem browsing for the UI | `backend/app/services/project_paths.py::list_directory` |
| Persisting the project record | `backend/app/repositories/projects.py` |

Everything that decides whether a path is acceptable lives in **one** module.
There is no second place where a path is trusted.

---

## 3. Managed vs. external projects

Every project record has a `location`:

- **`managed`** — Solo created the folder inside `APP_DATA_DIR/workspaces/`.
  `root_path` stores a slug relative to that directory.
- **`external`** — a folder that already existed. `root_path` stores an absolute
  path.

`resolve_project_root()` turns either form into an absolute path and re-checks
it. A managed project is confined to the workspaces directory; an external
project must still satisfy the path policy (see §6).

The distinction also drives deletion:

```python
delete(project_id, remove_files=None)
#   managed  -> the directory is removed   (remove_files defaults to True)
#   external -> only unregistered          (remove_files defaults to False)
```

An explicit `?remove_files=true` can override this, but the default is chosen so
that a careless click can never delete a user's repository.

---

## 4. The `.solo` state store

Layout, created on create/open/import:

```
<project-root>/.solo/
├── project.json          identity and manifest
├── config.json           per-project configuration
├── .gitignore            hides Solo state from git by default
├── state/tree.json       the structured project state tree
├── memory/index.json     ordered memory index
├── memory/entries/<id>.json
├── sessions/index.json
├── sessions/<id>.json    full transcripts
├── tasks/index.json
└── tasks/<id>.json       task + changed files + normalised events
```

### `project.json`

```json
{
  "version": 1,
  "id": "2704abd6eeb749f1afcbe7007ea86f3a",
  "name": "Existing Repo",
  "origin": "opened",
  "root": "/home/you/code/existing-repo",
  "created_at": "2026-10-10T15:37:31Z",
  "updated_at": "2026-10-10T15:37:39Z"
}
```

The `id` is what makes a project **portable**. When you open a folder that
already has a `.solo/project.json`, Solo adopts that id (provided no other
project already uses it), so history written by a different Solo installation on
a different machine stays attached to the same project.

### `config.json`

```json
{
  "version": 1,
  "tree":     { "max_depth": null, "max_entries": null, "exclude": [] },
  "memory":   { "max_entries": 500, "auto_capture": true },
  "sessions": { "max_sessions": 20 },
  "state":    { "auto_refresh": true },
  "agent":    { "backend": null, "provider": null, "model": null }
}
```

`null` means "use the application default", so raising an application default
lifts every project that has not overridden it. Updates are **deep-merged**, so
saving one section cannot erase another. The UI exposes tree depth/entries and
exclusions, memory limits, session retention and auto-refresh.

### `state/tree.json`

One structure containing both the file tree and the project's activity:

```
project
├── Files      (directory/file nodes, bounded and exclusion-aware)
├── Tasks      (one node per task: status, type, ref to tasks/<id>.json)
├── Memory     (one node per entry: kind, ref to memory/entries/<id>.json)
└── Sessions   (one node per conversation: message count, ref)
```

Nodes carry a `ref` pointing at the detail file, so the tree is an index rather
than a duplicate. It is written atomically (temp file + `os.replace`), so an
interrupted write cannot leave truncated JSON.

**Portability detail.** When refreshing, Solo *unions* the task and session
nodes derived from the live database with nodes already present in the index
whose detail files still exist. Opening a project from another installation —
where the local database knows nothing about those tasks — therefore preserves
its history instead of erasing the index.

### Bounds

Every scan is bounded so a huge or unusual directory cannot stall the app:

| Bound | Default | Setting |
|---|---|---|
| File-tree depth | 10 | `MAX_TREE_DEPTH`, per project `tree.max_depth` |
| File-tree entries | 5 000 | `MAX_TREE_ENTRIES`, per project `tree.max_entries` |
| Retained task records | 50 | `MAX_TASK_RECORDS` |
| Retained session records | 20 | `MAX_SESSION_RECORDS` |
| Events per task record | 500 | `MAX_EVENTS_PER_TASK_RECORD` |
| Memory entries | 500 | per project `memory.max_entries` |

Excluded from the file tree by default: `.git`, `node_modules`, `venv`,
`.venv`, `__pycache__`, `dist`, `build`, `.next`, `.idea`, `.vscode`,
`.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `target`, `vendor` — plus the
metadata directory itself.

---

## 5. When state is written

| Moment | What is written |
|---|---|
| Create / Open / Import | Full initialisation, then a tree refresh |
| Task starts running | Task record, then a tree refresh |
| Task reaches a terminal state | Task record **before** the status is broadcast, then a tree refresh |
| Message sent | Session transcript |
| Memory added or removed | Entry file, index, then a tree refresh |
| Config saved | `config.json` |
| On demand | `GET /tree?refresh=true` |

The ordering for terminal states is deliberate: a client that sees *"completed"*
can always read the finished record from disk.

**Failures never break work.** Sync is best-effort: a project folder that has
become read-only logs a warning and the application keeps running. Only
`initialize` fails loudly, because a project without a store cannot record
anything — that produces a clear `cannot write project metadata` error.

---

## 6. The path policy

`project_paths.py` is the only place a folder is judged. Rules, in order:

1. **Resolve first.** The path is expanded and fully resolved (symlinks
   followed) *before* any check, so a link cannot smuggle a location past a
   rule. A relative path resolves against the browser's default root.
2. **Must exist and be a directory.**
3. **Blocked, always:** `/proc`, `/sys`, `/dev`, `/etc`, `/boot`, `/run`,
   `/root`, `/var/lib/docker`, `/var/lib/solo` (POSIX), and the Solo
   `APP_DATA_DIR`. The last one matters: the data directory holds
   `master.key`, and a project root is somewhere an agent may eventually write.
4. **Allow-list, optional.** With `ALLOW_ANY_PROJECT_PATH=false`, a path must be
   inside `PROJECT_ROOTS`, the home directory, or the managed workspaces
   directory. This is the correct setting for a shared or internet-facing
   deployment.
5. **Managed projects** are additionally confined to `APP_DATA_DIR/workspaces/`
   and rejected if they resolve outside it.

The browser only ever receives **directory names** from `GET /api/fs/list` —
never file contents — and every path it sends back is validated again.

---

## 7. Using the API directly

```bash
# Create in the managed folder
curl -b cookies -X POST localhost:8080/api/projects \
  -H 'Content-Type: application/json' -d '{"name":"Demo"}'

# Create at a chosen parent
curl -b cookies -X POST localhost:8080/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"name":"Demo","parent":"/home/you/projects"}'

# Open an existing folder in place
curl -b cookies -X POST localhost:8080/api/projects/open \
  -H 'Content-Type: application/json' -d '{"path":"/home/you/code/app"}'

# Read the state tree
curl -b cookies "localhost:8080/api/projects/<id>/tree?refresh=true"

# Record a decision
curl -b cookies -X POST localhost:8080/api/projects/<id>/memory \
  -H 'Content-Type: application/json' \
  -d '{"text":"Uses SQLite","kind":"decision","tags":["db"]}'

# Tune the project's tree and memory limits
curl -b cookies -X PUT localhost:8080/api/projects/<id>/config \
  -H 'Content-Type: application/json' \
  -d '{"tree":{"max_depth":6},"memory":{"auto_capture":false}}'
```

Full reference: [docs/api.md](api.md).

---

## 8. Design decisions and their trade-offs

**State lives in the project, not only in the database.**
*Chosen because* the store travels with the project and is readable without
Solo. *Cost:* writes to disk on task transitions, and a read-only project cannot
record history (handled by logging rather than failing).

**SQLite remains authoritative for queries.**
The files are a durable mirror; nothing in the request path parses them. A
corrupt or missing store degrades gracefully to "no stored state" and is rebuilt
on the next refresh.

**`initialize` refuses a non-empty create target.**
Creating into an existing non-empty folder would silently mix projects. Open
Project exists for that case.

**A generated `.gitignore` inside `.solo/`.**
Solo state is hidden from git by default, but Solo never edits a repository's
own `.gitignore`. Delete the generated file if you want to commit memory and
task history with your code.

**`ALLOW_ANY_PROJECT_PATH` defaults to permissive.**
For a personal, single-user, local-first install this is the useful default and
is what "open a folder on my machine" means. It is **not** the right default for
an internet-facing deployment; set it to `false` and list `PROJECT_ROOTS`. This
is the single most important configuration decision when sharing Solo, and it is
called out in the README and in [deployment.md](deployment.md).
