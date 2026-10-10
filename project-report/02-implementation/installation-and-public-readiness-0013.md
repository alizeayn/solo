# 13 — Installation, Documentation and Public Readiness

**Stage:** Implementation
**Date:** 2026-10-10

---

## 1. The problem with the previous installer

Phase 1 shipped `install.sh`, but it assumed Docker throughout and had **never
been executed on a machine without a working Docker daemon**. The README told a
new user to clone and run one command; nobody had verified that command end to
end from a clean checkout.

Three separate issues followed from that:

1. There was no path at all for a personal machine without Docker.
2. Docker required group membership and re-login, which the installer treated as
   a fatal error rather than a fork in the road.
3. The first real native run exposed a **script-aborting bug** (D-09) that would
   have hit every user.

---

## 2. Native install: `solo.sh`

A new lifecycle manager, `./solo.sh`, owns the non-Docker install:

```
./solo.sh install    Python + Node setup, build the UI, seed the password, start
./solo.sh start      start in the background
./solo.sh stop       stop
./solo.sh restart    restart
./solo.sh status     running? healthy?
./solo.sh logs       follow data/solo.log
./solo.sh update     git pull, reinstall, rebuild, restart
./solo.sh doctor     check prerequisites without changing anything
```

Design decisions:

- **Everything stays in the checkout.** `venv/`, `frontend/dist/`, `data/`.
  Uninstalling is `rm -rf`. Only `data/` and `.env` matter on upgrade.
- **Runs from the repository root** with `PYTHONPATH=<repo>/backend`, so `.env`
  and `./data` resolve to the same places the Docker install uses. The previous
  `dev.sh` ran from `backend/`, which silently put the database in
  `backend/data/` — fixed at the same time.
- **Idempotent.** Re-running reuses the venv, reinstalls dependencies, rebuilds
  the UI and restarts. It never regenerates a password once `data/app.db`
  exists.
- **Clear prerequisite failures.** Missing Python or Node produces the exact
  version required and points at `--docker` as the alternative.
- **Background process management.** PID in `data/solo.pid`, log in
  `data/solo.log`, health poll before reporting success, SIGTERM then SIGKILL on
  stop.

### The password on a fresh install

`data/initial-admin-password` is written `600`, printed once, read by the app at
startup, and **deleted** after the account is created. Verified on the real
install: the file was gone immediately afterwards.

## 3. Unified installer: `install.sh`

Rewritten to choose a path instead of assuming one:

```bash
./install.sh              # auto: Docker when usable, otherwise native
./install.sh --docker     # require Docker
./install.sh --native     # never use Docker
./install.sh --no-start   # prepare only
```

Auto-detection tests `docker info` and `docker compose version` — not merely the
presence of the binary, which is what made the original silent failure possible.
When Docker is installed but unreachable, it warns, explains the fix, and
proceeds natively rather than dying.

Both paths share the same behaviours: `.env` creation at `600`, a port-conflict
check before starting, one-time password generation, health polling, and a
printed summary with the URL, credentials and the next steps.

---

## 4. Documentation rewritten for a public audience

### README.md

Restructured around what a stranger needs, in order:

1. what Solo does, with an honest status table (simulator, not real agent yet);
2. prerequisites and the one-command install, with example output;
3. **Create vs. Open vs. Import** explained as three genuinely different things;
4. the `.solo` state store laid out, with a real `tree.json` sample;
5. configuration table covering every environment variable that matters,
   including `ALLOW_ANY_PROJECT_PATH` and `PROJECT_ROOTS`;
6. the security model, including the Open Project trust boundary and the HTTPS
   warning;
7. testing commands and what the suites prove;
8. project layout, day-2 management, and a troubleshooting table.

### New: `docs/projects.md`

The project model in full: the three entry points, managed vs. external
projects, the store layout with sample files, when state is written, the write
ordering guarantee, all bounds, the five-step path policy, direct API examples,
and a section on design decisions and their trade-offs.

### Updated

| Document | Change |
|---|---|
| `docs/architecture.md` | Project model section, new modules in the map, current section numbering |
| `docs/deployment.md` | Native and Docker paths, project path policy for shared servers, corrected data layout, backup caveat for in-place projects |
| `docs/development.md` | New test files, project-model conventions, eight documented regression traps, `solo.sh` commands |
| `docs/api.md` | Project endpoints, state tree, memory, config, summary and filesystem browser |
| `.env.example` | Grouped and commented: projects, agent, extraction guards, cookie security |

---

## 5. Public-repository readiness

### Secrets audit

| Check | Result |
|---|---|
| `.env` committed? | No — `.gitignore`d; only `.env.example` |
| `data/` (db, key, secrets, workspaces) committed? | No |
| `initial-admin-password` committed? | No — `.gitignore`d |
| `node_modules/`, `venv/`, `frontend/dist/` committed? | No |
| Any credential-shaped string in tracked files? | Scanned: none |
| `.dockerignore` excludes the same set? | Yes |
| Existing API keys in the local `data/secrets.enc`? | None stored |

Generated content (the built UI, `data/`) is deliberately not committed: a clone
builds its own, which keeps the repository source-only and avoids shipping stale
bundles.

### What a stranger needs

Only Python 3.10+ and Node 20+ (or Docker). **No API key is required to install
or explore** — credentials are optional and entered later in Settings. The
install instructions were executed from a clean state (`.env` and `data/`
removed) to confirm this.

---

## 6. Files touched in this phase

**Added (12)**

```
solo.sh
backend/app/services/project_paths.py
backend/app/services/project_store.py
backend/app/api/fs.py
backend/tests/test_project_paths.py
backend/tests/test_project_store.py
backend/tests/test_api_project_open.py
frontend/src/components/DirectoryBrowser.tsx
frontend/src/components/DirectoryBrowser.test.tsx
frontend/src/components/ProjectDialog.test.tsx
frontend/src/panels/ProjectStatePanel.tsx
docs/projects.md
```

**Modified (28)** — `install.sh`, `README.md`, `.env.example`, `.gitignore`,
`Dockerfile`, `docker-compose.yml`, `scripts/dev.sh`, `scripts/e2e.sh`,
`docs/{architecture,deployment,development,api}.md`, `backend/app/{config,domain,models,schemas,container,main}.py`,
`backend/app/api/{auth,projects}.py`, `backend/app/repositories/{projects,conversations}.py`,
`backend/app/services/{project_service,orchestrator}.py`,
`backend/{pyproject.toml,tests/conftest.py,tests/test_api_auth.py,tests/test_api_projects.py}`,
`frontend/{index.html,package.json}`, `frontend/src/{types.ts,styles.css}`,
`frontend/src/api/client.ts`, `frontend/src/components/{Header,LoginView,WorkspaceView,ProjectDialog}.tsx`,
`frontend/src/panels/InspectorPanel.tsx`.
