# Development

---

## 1. Environment

| Tool | Version used |
|---|---|
| Python | 3.12 |
| Node | 24 (20+ required by Vite 8) |
| Docker | 29 + Compose v2 (for deployment) |
| `pi` CLI | 1.1.0 (optional until Phase 2) |

```bash
python3 -m venv venv
./venv/bin/pip install -r backend/requirements-dev.txt
(cd frontend && npm ci)
```

---

## 2. Running

```bash
./scripts/dev.sh              # backend :8080 + Vite :5173
./scripts/dev.sh backend      # backend only (uvicorn --reload)
./scripts/dev.sh frontend     # frontend only
```

Vite proxies `/api` (including the WebSocket) to the backend, so the browser
always talks to a single origin — the same shape as production.

Backend only, without the script:

```bash
cd backend
../venv/bin/uvicorn app.main:app --reload --port 8080
```

Interactive API docs: <http://127.0.0.1:8080/api/docs>.

---

## 3. Tests

```bash
# Backend — 194 tests, ~91 % coverage
cd backend
../venv/bin/python -m pytest
../venv/bin/python -m pytest --cov=app --cov-report=term-missing
../venv/bin/python -m pytest tests/test_archive.py -v

# Frontend — 39 tests
cd frontend
npm test
npm run test:watch

# Type checking
cd frontend && npm run typecheck

# End-to-end against a real server — 53 checks
./scripts/e2e.sh
E2E_PORT=8123 ./scripts/e2e.sh
```

### Test layout

| File | Covers |
|---|---|
| `tests/test_security.py` | scrypt hashing, session tokens, `SecretCipher`, masking, redaction |
| `tests/test_archive.py` | Zip Slip, symlinks, entry/size limits, root stripping |
| `tests/test_intent.py` | Router precedence table |
| `tests/test_project_scan.py` | Ignored directories, bounds, language summary |
| `tests/test_project_paths.py` | Blocked paths, symlink escapes, allow-list mode, managed vs external roots, directory listing |
| `tests/test_project_store.py` | `.solo` layout, tree groups, exclusions, memory, config merge, idempotent init, task/session records, index union, read-only handling |
| `tests/test_api_auth.py` | Setup/login/logout, route protection, CSRF, cookie flags, WebSocket handshake |
| `tests/test_api_projects.py` | Create/list/delete, import validation, path boundaries |
| `tests/test_api_project_open.py` | Open in place, idempotency, blocked paths, adoption of foreign state, delete semantics, tree/memory/config/summary, filesystem browser |
| `tests/test_api_settings.py` | Masking, encryption at rest, clearing keys |
| `tests/test_api_tasks.py` | Lifecycle, conflicts, cancellation, steering, restart persistence |
| `tests/test_api_messages.py` | Chat / steer / stop / new-task routing |
| `tests/test_orchestrator.py` | Restart recovery, admin bootstrap |
| `tests/test_services_extra.py` | Provider error handling (stubbed HTTP), event bus, adapter failure, context snapshot |
| `tests/test_pi_runtime.py` | **Isolation**: `PATH` is never used, the agent directory is never `~/.pi/agent`, install/verify/failure handling |
| `tests/test_account_and_voice.py` | Account changes and the narration pipeline (ordering, coalescing, barge-in) |
| `tests/test_project_files.py` | File read/write/upload path safety |
| `frontend …/DirectoryBrowser.test.tsx` | Directory listing, navigation, blocked path surfacing, selection semantics |
| `frontend …/ProjectDialog.test.tsx` | Create (managed and custom location), open in place, import, validation |

Every test gets an isolated data directory and its own application instance
(`tests/conftest.py`), so nothing touches a real `data/`.

---

## 4. Conventions

**Backend**

- Business logic lives in `services/`; routers only validate and map to status
  codes. Database access lives in `repositories/` and nowhere else.
- Type hints everywhere; `from __future__ import annotations` at the top.
- Structured domain vocabulary in `domain.py` — no bare string literals for
  statuses, event types or intents in service code.
- Never log a secret. Register it with `logging_setup.register_secret` when it
  is read, and rely on `RedactionFilter` as the safety net.
- Persist before broadcasting. A WebSocket failure must never lose state.

**Frontend**

- The backend is the source of truth; the UI mirrors it.
- Panels render from `useWorkspace()` and hold no authoritative state.
- Secrets are write-only: send them, never read them back.
- Long comments explain *why*; the code already says *what*.

**Commits**

Conventional-commit style subject lines (`feat:`, `fix:`, `test:`, `docs:`),
imperative mood, one logical change per commit.

---

## 5. Adding a coding-agent adapter (Phase 2 pattern)

1. Create `backend/app/adapters/my_agent.py`.
2. Implement the protocol from `adapters/base.py`:

   ```python
   class MyAgentAdapter:
       name = "my-agent"

       async def start(self) -> None: ...
       async def run(self, *, task_id, prompt, cwd, on_event) -> AgentResult: ...
       async def steer(self, *, task_id, instruction) -> None: ...
       async def cancel(self, *, task_id) -> None: ...
       async def stop(self) -> None: ...
       async def health(self) -> dict: ...
   ```

3. Translate provider records into `AgentEvent`s using `domain.EventType`.
   Keep **all** protocol parsing in the adapter.
4. Register it in `adapters/__init__.py::build_adapter` and select it with
   `AGENT_BACKEND`.
5. Add tests with a fake transport; never call a real provider in the suite.

Two behaviours matter for correctness:

- `cancel()` must not lose a request that arrives **before** `run()` starts.
  The mock adapter creates-and-sets the cancellation event if it does not exist
  yet; a real adapter should queue an abort for a not-yet-started session.
- `steer()` must be safe to call while the run loop is awaiting.

---

## 6. Consistency rules worth remembering

Defects found during Phases 1 and 1.5 that are easy to reintroduce:

1. **Zip Slip via root stripping.** A `../escape.txt` entry was once treated as
   a "single wrapping directory" and stripped to a harmless `escape.txt`. Every
   member name is now validated *before* any root stripping, and
   `_common_root()` additionally rejects `".."`, `"."` and drive-letter roots.
2. **Terminal-state overwrite.** A shutdown cancellation landing immediately
   after completion rewrote `COMPLETED` to `CANCELLED`. `_set_status` now
   refuses to leave a terminal state, and `shutdown()` only cancels runners that
   are not already `done()`.
3. **Question routed as an instruction.** *"what files changed so far?"* was
   classified as a steering instruction because "changed" contains the coding
   verb "change". Informational questions now take precedence over verbs.
4. **Lazy relationship outside a greenlet.** `TaskDetailOut.model_validate(task)`
   tried to load `task.files` lazily and raised `MissingGreenlet`. Response
   models are built from `TaskOut` and relationships are loaded explicitly.
5. **Cancellation arrived too early.** `cancel()` used to do nothing when the
   run had not started yet, so an immediate cancel was silently dropped. It now
   creates-and-sets the event, and the same requirement is written into the
   Phase 2 adapter guidance below.
6. **`set -o pipefail` plus `head`.** `tr -dc … </dev/urandom | head -c 24`
   made `tr` die of SIGPIPE, which aborted the installer silently before it
   started the server. Use a bounded producer (`head -c … /dev/urandom`,
   `openssl rand`, or Python) or avoid the pipeline; see `generate_password()`
   in `install.sh` and `solo.sh`. The same trap applies to
   `… | grep -q` in `port_in_use()` — capture first, then `grep` a herestring.
7. **`Secure` cookies over plain HTTP.** Browsers reject them, so sign-in
   appeared to succeed and then failed every request on a plain-HTTP install.
   The flag is now auto-detected from the request scheme
   (`SESSION_COOKIE_SECURE` to override), never from `APP_ENV` alone.
8. **Browser overwriting user input.** `DirectoryBrowser` used to report its
   mount-time listing as a selection, clobbering a path the user had already
   typed. The initial listing is informational; only explicit navigation
   reports a selection.

---

## 7. Database changes

The MVP uses `Base.metadata.create_all` at startup (additive only). For a
schema change:

1. Edit `models.py`.
2. Delete a **development** `data/app.db` (never a real one).
3. Before shipping, add an explicit migration step to the release notes and
   note it in `docs/deployment.md`.

Because repositories are the only DB consumers, a move to PostgreSQL means
changing the engine URL in `db.py` plus a review of SQLite-specific defaults.

---

## 8. Useful commands

```bash
# Inspect the running app's schema
sqlite3 data/app.db ".schema"

# Watch live events for a task
curl -b cookies.txt localhost:8080/api/tasks/<id>/events | python3 -m json.tool

# Confirm no secret leaked into the database
grep -c "sk-or-v1" data/app.db    # must be 0

# Confirm restrictive permissions on the key
stat -c '%a %n' data/master.key   # 600

# Inspect a project's stored state without Solo
cat /path/to/project/.solo/state/tree.json | python3 -m json.tool
cat /path/to/project/.solo/config.json

# Native lifecycle
./solo.sh doctor && ./solo.sh status && ./solo.sh logs
```

---

## 9. Working on the project model

The project model has one rule that keeps it coherent: **`project_paths.py` is
the only module allowed to decide whether a path is acceptable.**

If you add anything that touches a project location:

1. Call `resolve_directory()` (user-supplied paths) or `resolve_project_root()`
   (stored project records).
2. Let `ProjectPathError` propagate — the API layer maps it to HTTP 400.
3. Add a test to `tests/test_project_paths.py`, including the escape attempt you
   are defending against.

When changing the state store:

- Bump `METADATA_VERSION` / `STATE_VERSION` in `project_store.py` if the on-disk
  shape changes, and read old files defensively (`_read_json` already returns a
  default on malformed input).
- Keep writes atomic (`_write_json`) and keep non-critical writes on the
  `_safe_write_json` path so a read-only project cannot break a task.
- Keep index nodes pointing at detail files via `ref`; the tree is an index, not
  a duplicate. `_merge_index_nodes` relies on this for portability.
- Respect the configured bounds; never add an unbounded scan or write.
