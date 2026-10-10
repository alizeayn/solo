# 16 — Phase 1.5 Summary

**Stage:** Summary
**Date:** 2026-10-10
**Milestone:** Solo, the project model, and public readiness
**Status:** ✅ Complete and verified

---

## 1. What changed and why

Four things were fixed before Phase 2, because each changes the shape of the
product rather than extending it.

### The project is now called **Solo**

Renamed across 13 artefact types: README, FastAPI title and dev-root payload,
`pyproject.toml`, `package.json`, `index.html`, the UI brand and login heading,
Dockerfile, compose image and container name, the installer banner, and every
document. The Docker volume name (`solo-data`) and the cookie name
(`solo_session`) were deliberately left alone so an existing installation is not
orphaned. `PROJECT_SPEC.md` was left verbatim: it is the requirements document,
not product output.

*Why now:* a name appears in package metadata, container names and documentation
that strangers read. Changing it after Phase 2 means touching everything twice.

### Create Project and Open Project are now genuinely different

| | Create Project | Open Project |
|---|---|---|
| What it does | Makes a new folder and initialises it | Adopts a folder where it already is |
| Copies files | n/a | **Never** |
| Location | Managed workspaces folder, or a parent you choose | Absolute path you browse to |
| Refuses | A non-empty target folder | Blocked or unwritable locations |
| On delete | Removes the folder (managed) | Only unregisters; **files are never touched** |

| | Import ZIP |
|---|---|
| What it does | Extracts an archive into the managed workspaces folder |
| Copies files | Yes — by definition, and it is the only operation that does |

*Why now:* this redefines what a "project" is — a directory on disk rather than
a row in a database — which affects the entity, the path policy, the state store
and every API that touches a project. Building Phase 2 on top of the old model
would have meant rebuilding the adapter integration afterwards.

### Project state lives with the project, in a structured tree

```
<project-root>/.solo/
├── project.json      identity (adopted when re-opening an existing store)
├── config.json       per-project configuration
├── .gitignore        keeps Solo state out of your repository
├── state/tree.json   the structured project state tree
├── memory/           index + one file per entry
├── sessions/         index + one transcript per conversation
└── tasks/            index + one record per task (files + events)
```

The state tree is one structure containing the file tree plus the project's
activity as labelled branches (`Files`, `Tasks`, `Memory`, `Sessions`). Browse
it in **Inspector → Project state**, alongside memory and per-project
configuration.

*Why now:* portability. A project folder carries its own history, so it can be
copied to another machine and opened there. Adding this after real task history
exists would mean a backfill.

### Installation is one command that actually runs

`./install.sh` now auto-detects the environment:

- **Docker** when the daemon is reachable → image + container.
- **Native** otherwise → venv, dependencies, UI build, password, running server.

`./solo.sh` manages the native install afterwards: `install | start | stop |
restart | status | logs | update | doctor`.

*Why now:* the previous installer assumed Docker and had **never been executed
on a machine without it**.

---

## 2. How project directories, memory, sessions, configuration and state are managed

| Concern | Where it lives | Written when |
|---|---|---|
| Identity | `.solo/project.json` | On create/open/import, then touched on refresh |
| **Configuration** | `.solo/config.json` | On save; deep-merged so sections cannot clobber each other |
| **Memory** | `.solo/memory/index.json` + `entries/<id>.json` | On add; index rebuilt on delete |
| **Sessions** | `.solo/sessions/index.json` + `<id>.json` | After each message, as a full transcript |
| **Tasks** | `.solo/tasks/index.json` + `<id>.json` | When a task starts and again when it settles |
| **State tree** | `.solo/state/tree.json` | On task start/settle, memory change, and on demand |

Bounds (all configurable per project): tree depth 10, 5 000 entries, 50 task
records, 20 session records, 500 events per task, 500 memory entries.
Exclusions cover `.git`, `node_modules`, `venv`, `dist`, caches and the
metadata directory itself.

Properties that matter:

- **Atomic writes** (temp file + `os.replace`) — no truncated JSON.
- **Portable** — an existing `project.json` id is adopted on open, and index
  nodes whose detail files still exist are preserved even when the local
  database does not know about them.
- **Never breaks work** — initialisation fails loudly with a clear message; a
  later sync to a read-only folder only logs a warning.
- **Ordered for observability** — a finished task is written to disk *before* its
  terminal status is broadcast, so a UI showing "completed" can always read the
  record.

---

## 3. What changed in the installation process, README and Quick Start

**Installer**
- `install.sh` rewritten: auto-detect, `--docker`, `--native`, `--no-start`.
- `solo.sh` added: full native lifecycle, with `doctor` for prerequisites.
- Prerequisite *versions* checked and reported (Python 3.10+, Node 20+).
- Port conflict detected **before** starting.
- One-time password written `600`, printed once, consumed and deleted on first
  boot — verified on the real install.
- Docker detection now tests `docker info`, not merely the presence of the
  binary.

**README** — restructured for a stranger: what Solo does with an honest status
table, prerequisites, the one-command install with example output, Create vs.
Open vs. Import, the `.solo` layout with a real `tree.json` sample, a complete
configuration table, the security model including the Open Project trust
boundary, testing commands, day-2 management, and a troubleshooting table.

**Quick Start** — now verified, not assumed: dependencies, one command, and the
first three UI steps. **No API key is required to install or explore**, because
the agent is simulated — which is exactly what makes the repository easy for
someone else to try.

**Docs** — `docs/projects.md` added (the project model in full);
`architecture.md`, `deployment.md`, `development.md`, `api.md` and
`.env.example` updated.

---

## 4. Tests run and results

| Suite | Result |
|---|---|
| Backend (pytest) | **194 passed**, 0 failed, **91 %** coverage (was 123 / 89 %) |
| Frontend (Vitest) | **39 passed**, 0 failed (was 22) |
| TypeScript `strict` | **0 errors** |
| End-to-end (real uvicorn + real SQLite) | **53 passed**, 0 failed (was 26) |
| Native install, clean checkout | ✅ install → build → start → login → create → open → task → memory → config |
| Shell scripts (`bash -n` × 6) | ✅ |
| Compose configuration | ✅ |

**286 automated checks, all passing.**

New test files: `test_project_paths.py` (path policy, blocked paths, symlink
escapes, allow-list mode, managed vs external, browsing), `test_project_store.py`
(`.solo` layout, tree structure, exclusions, memory, config merge, idempotent
init, records, index union, read-only handling), `test_api_project_open.py`
(open in place, idempotency, foreign-state adoption, delete semantics,
tree/memory/config/summary endpoints, filesystem browser),
`DirectoryBrowser.test.tsx`, `ProjectDialog.test.tsx`.

**Four defects found and fixed** (D-09…D-12), three of them by *executing*
something that had only been documented — including a critical shell bug that
made the one-command install do nothing at all. See
[defect-log-0014.md](../04-defects/defect-log-0014.md).

### Remaining limitations

1. The coding agent is still a **simulator** — it modifies nothing.
2. The **Docker image still has not been built** (D-08: daemon socket not
   accessible to this user). The native path was executed end to end instead.
3. `ALLOW_ANY_PROJECT_PATH` defaults to permissive — correct locally, needs
   changing before wider exposure. **Flagged for your confirmation.**
4. No browser-driven UI automation; component tests plus a real-server
   API-level end-to-end run cover the path.
5. No schema migration framework (additive-only).

---

## 5. How to install, launch and test on your machine

```bash
# 1. One command (uses Docker if available, otherwise installs natively)
cd ~/Desktop/solo
./install.sh
```

The installer prints the URL, `admin`, and a one-time password. Then:

```bash
./solo.sh status     # running and healthy?
./solo.sh logs       # follow the log
./solo.sh stop       # stop
./solo.sh start      # start again
./solo.sh update     # after a git pull
```

Open the printed URL (default <http://127.0.0.1:8080>), sign in, then:

1. **Settings** → paste an OpenRouter key → **Test connection** (optional).
2. **+ Create Project** for a new folder, or **Open Project** to adopt a folder
   you already have — for example `~/code/my-service`. Nothing is copied.
3. Type a request in **Conversation** and watch **Coding Agent Activity**.
4. Inspect **Inspector → Project state** for the state tree, memory and config.

To verify the installation itself:

```bash
./scripts/e2e.sh                      # 53 checks against a real server
cd backend && ../venv/bin/python -m pytest    # 194 tests
cd frontend && npm test                       # 39 tests
```

---

## 6. How someone else installs and tests it from the public repository

Once the repository is public, anyone can do this:

```bash
git clone https://github.com/alizeayn/solo.git
cd solo
./install.sh
```

- **Prerequisites:** Python 3.10+ and Node 20+, or Docker. Nothing else.
- **No API key is needed** to install, explore the UI, create a project, open an
  existing folder, or run a task against the simulator.
- Optional credentials are added later in **Settings**, stored encrypted
  server-side, and never returned to the browser.

```bash
# Docker route
./install.sh --docker
docker compose logs -f

# Verify the build
./scripts/e2e.sh
```

They can also read the model without running anything:
[docs/projects.md](../docs/projects.md) explains Create/Open/Import and the
`.solo` store; [docs/api.md](../docs/api.md) has the endpoint reference.

**Before making the repository public**, note that per the audit in report 13 §5
there are no secrets, credentials or generated artefacts in version control.

---

## 7. Recommended next steps

1. **Confirm the path-policy default** (report 11 §4). Today
   `ALLOW_ANY_PROJECT_PATH=true` lets any signed-in user open any readable
   folder. Keep it for a personal install; switch to `false` + `PROJECT_ROOTS`
   if Solo will be reachable by others.
2. **Close D-08** when convenient: `sudo usermod -aG docker $USER`, re-login,
   then `docker compose build && docker compose up -d` and
   `curl -fsS localhost:8080/api/health`.
3. **Make the repository public** — the README, quick start and secrets audit
   are ready.
4. **Then start Phase 2** (Pi RPC). The seams are in place: one adapter class,
   one factory, and `AGENT_BACKEND=pi` already wired.

---

## 8. Conclusion

The milestone is complete: Solo is named consistently, works with projects where
they already live, keeps a portable and inspectable record of each one, installs
with a single command on a machine without Docker, and is documented well enough
for someone else to clone and try.

The most valuable outcome is not the new code but the corrected assumptions. Two
of the four defects fixed here concerned things that had been *written down* and
never *executed* — a documented one-command install that silently did nothing,
and a security setting that broke sign-in, both of which had been "verified" only
by having been typed. The habit worth keeping is the one that found them: run
the thing you documented, from the state a stranger would start in.

The second-order effect matters for what comes next. Because a project is now a
directory with its own configuration, memory, sessions and state tree, Phase 2's
Pi adapter has somewhere durable to read context from and write results to, and
Phase 3's OpenRouter layer has a bounded snapshot to work from — without either
of them needing to invent a memory model.
