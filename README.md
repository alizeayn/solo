# Solo

**A local-first, voice-first AI workspace for working on real projects with a
coding agent** — from the browser, without living in a terminal.

> **Status: Phase 1 complete.** The application shell, the project model and the
> full task pipeline are implemented, tested and deployable. The coding agent is
> a **deterministic simulator** in this phase: it emits realistic progress
> events but does not modify files. Real Pi RPC, OpenRouter and ElevenLabs voice
> arrive in later phases — see [Roadmap](#roadmap).

---

## Table of contents

- [What Solo does](#what-solo-does)
- [Quick start](#quick-start)
- [Create, Open and Import](#create-open-and-import)
- [Project state on disk](#project-state-on-disk)
- [Configuration](#configuration)
- [Security model](#security-model)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Managing the install](#managing-the-install)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Documentation](#documentation)
- [License](#license)

---

## What Solo does

You open a browser, point Solo at a project, and talk to it — by typing now, by
voice later. Solo talks to a coding agent, shows you what it is doing in plain
language, answers questions while work is running, and keeps a durable record of
everything in a folder you can read.

| Capability | Status |
|---|---|
| One-command install (native or Docker) | ✅ |
| **Create Project** — new folder with Solo state | ✅ |
| **Open Project** — adopt an existing folder in place, nothing copied | ✅ |
| **Import ZIP** — extract into Solo's workspaces folder | ✅ |
| Per-project config, memory, sessions, tasks and a state tree | ✅ |
| Server-side directory browser for opening projects | ✅ |
| Single-user auth, hashed password, HttpOnly cookie | ✅ |
| Encrypted API keys, masked in every response, redacted from logs | ✅ |
| Settings UI with real "Test connection" for OpenRouter / ElevenLabs / Pi | ✅ |
| Dark, responsive, tiled Dockview workspace with 3 panels | ✅ |
| Live task events over WebSocket; panel layout persistence | ✅ |
| Question vs. steer vs. stop vs. new-task routing | ✅ |
| Restart recovery: interrupted tasks become `RECOVERY_REQUIRED` | ✅ |
| Real Pi RPC subprocess | 🔜 Phase 2 |
| OpenRouter summaries, routing and project Q&A | 🔜 Phase 3 |
| ElevenLabs live voice | 🔜 Phase 4 |
| Spoken progress announcements | 🔜 Phase 5 |

---

## Quick start

### Prerequisites

| Path | Needs |
|---|---|
| **Native** (default when Docker is unavailable) | Python **3.10+**, Node.js **20+**, `curl` |
| **Docker** | Docker Engine + Compose v2 |

You do **not** need an API key to install and explore Solo. Credentials are
optional and are entered later in Settings.

### One command

```bash
git clone https://github.com/alizeayn/solo.git
cd solo
./install.sh
```

`install.sh` picks the best available path:

- **Docker** when the daemon is reachable → builds an image and starts a
  container.
- **Native** otherwise → creates a virtualenv, installs dependencies, builds the
  web UI, seeds an admin password and starts the server.

Either way it prints a URL, a username, and a **one-time password**:

```
──────────────────────────────────────────────────────────────
 Solo is running
──────────────────────────────────────────────────────────────
 Local:  http://127.0.0.1:8080
 LAN:    http://192.168.1.20:8080
 User:   admin
 Pass:   hBGsaHp32fW5NQvGmGaroDXI
──────────────────────────────────────────────────────────────
```

Open that URL, sign in, and you are in. The password is shown once and is
deleted automatically after the first successful start.

Force a specific path when you want it:

```bash
./install.sh --native     # no Docker, ever
./install.sh --docker     # require Docker
./install.sh --no-start   # prepare everything, start nothing
```

### What the installer creates

| Location | What |
|---|---|
| `venv/` | Python virtualenv (native install only) |
| `frontend/dist/` | The built web UI |
| `data/app.db` | SQLite database (projects, tasks, events, messages) |
| `data/master.key` | Encryption key for stored credentials, mode `600` |
| `data/secrets.enc` | Encrypted API keys |
| `data/workspaces/` | Projects created or imported by Solo |
| `.env` | Operational settings, mode `600` (no secrets) |

Everything lives inside the repository folder, so uninstalling is `rm -rf`.
Only `data/` and `.env` matter when upgrading.

### Then

1. **Settings** → add your OpenRouter key (and ElevenLabs key + Agent ID when
   you want voice). Use **Test connection** to confirm.
2. **Create Project** or **Open Project**.
3. Type a request in the Conversation panel and watch the Activity panel.

---

## Create, Open and Import

Solo treats these three as genuinely different operations.

### Create Project

Creates a **new folder** and initialises it with Solo state.

- Choose a name, and either use Solo's managed workspaces folder or pick any
  parent folder on the machine.
- The folder is created and given a `.solo/` directory holding the project's
  configuration, memory, sessions, task history and state tree.
- Refuses to write into a non-empty existing folder, so nothing is overwritten.

### Open Project

Adopts a **folder you already have**, exactly where it is.

- Browse the server's filesystem (directories only) or type a path.
- **Nothing is copied, moved, uploaded or archived.** Solo reads the project in
  place and only adds a `.solo/` directory for its own state.
- If the folder already contains a `.solo/project.json` — for example from
  another Solo installation or another machine — Solo **adopts that identity**
  and keeps the recorded memory, sessions and task history.
- Opening the same folder twice returns the same project rather than creating a
  duplicate.
- Removing an opened project from Solo only unregisters it. **Your files are
  never deleted** — the end-to-end test asserts this byte-for-byte.

### Import ZIP

The only path that copies files: a `.zip` archive is extracted into Solo's
managed workspaces folder. It is protected against path traversal, absolute
paths, symlink entries and decompression bombs, and nothing inside is executed.

---

## Project state on disk

Every project is self-describing. Solo writes a structured, human-readable
store inside the project root:

```
<project-root>/
├── .solo/
│   ├── project.json          identity: id, name, origin, timestamps
│   ├── config.json           per-project configuration
│   ├── .gitignore            keeps Solo state out of your repository
│   ├── state/
│   │   └── tree.json         the structured project state tree
│   ├── memory/
│   │   ├── index.json
│   │   └── entries/<id>.json your notes, decisions and facts
│   ├── sessions/
│   │   ├── index.json
│   │   └── <id>.json         full conversation transcripts
│   └── tasks/
│       ├── index.json
│       └── <id>.json         task, changed files and normalised events
└── … your project files, untouched
```

The **state tree** is the single structured view of a project: its file tree
plus its tasks, memory and sessions as labelled branches.

```json
{
  "version": 1,
  "generated_at": "2026-10-10T15:37:37Z",
  "project": { "id": "2704abd6…", "name": "Existing Repo", "location": "external" },
  "root": {
    "id": "root", "name": "Existing Repo", "kind": "project",
    "children": [
      { "id": "group:files",    "kind": "group", "name": "Files",
        "children": [ { "kind": "directory", "name": "src", "children": [
          { "kind": "file", "name": "main.py", "path": "src/main.py" } ] } ] },
      { "id": "group:tasks",    "kind": "group", "name": "Tasks",
        "children": [ { "kind": "task", "name": "add a health endpoint",
                        "status": "COMPLETED", "ref": "tasks/<id>.json" } ] },
      { "id": "group:memory",   "kind": "group", "name": "Memory",   "children": [] },
      { "id": "group:sessions", "kind": "group", "name": "Sessions", "children": [] }
    ]
  }
}
```

Browse it in the UI under **Inspector → Project state**, where you can also add
memory entries and edit the per-project configuration (tree depth and entry
limits, excluded folders, memory limits, session retention, auto-refresh).

**Why a folder instead of only a database?** The store travels with the project.
Copy the folder, or clone it on another machine, open it, and its history comes
with it. SQLite remains the fast query index; the files are the durable record.

Writing to `.solo/` is by design: `initialize` fails with a clear message if the
project folder is not writable, and later syncs log a warning instead of
breaking a running task.

---

## Configuration

Operational settings live in `.env` (created from `.env.example`). **Never put
API keys in this file.**

| Variable | Default | Purpose |
|---|---|---|
| `APP_PORT` | `8080` | The single user-facing port |
| `APP_HOST` | `0.0.0.0` | Bind address |
| `APP_DATA_DIR` | `./data` | Database, encryption key, secrets, workspaces |
| `APP_ENV` | `development` | `production` is for deployed installs |
| `SESSION_TTL_HOURS` | `168` | Session lifetime |
| `SESSION_COOKIE_SECURE` | *(auto)* | `Secure` cookie flag; auto = only over HTTPS |
| `MAX_UPLOAD_MB` | `200` | ZIP upload limit |
| `MAX_ZIP_ENTRIES` / `MAX_UNCOMPRESSED_MB` | `20000` / `2048` | Extraction guards |
| `LOG_LEVEL` | `INFO` | `DEBUG`…`ERROR` (secrets stay redacted) |
| `AGENT_BACKEND` | `mock` | `mock` now; `pi` from Phase 2 |
| `METADATA_DIR_NAME` | `.solo` | Name of the per-project state folder |
| `PROJECT_ROOTS` | *(empty)* | Extra roots Open Project may read (`:`-separated) |
| `ALLOW_ANY_PROJECT_PATH` | `true` | Set `false` to restrict opening to allowed roots |
| `ADMIN_PASSWORD` | – | One-time bootstrap password (used by the installer) |
| `FRONTEND_DIST` | – | Built UI for the backend to serve |

**Provider credentials are not environment variables.** They are entered in
Settings, encrypted with Fernet, stored in `data/secrets.enc`, and keyed by
`data/master.key` (mode `600`). The API only ever returns
`{"configured": true, "masked": "****abcd"}`.

### Changing the port

```bash
# edit .env, then
./solo.sh restart                 # native
docker compose up -d              # Docker
```

---

## Security model

Solo can run a coding agent against your files, so it is protected by default.

- **Authentication is mandatory.** Every API route except `/api/health` and the
  first-run `/api/auth/*` endpoints requires a session. The WebSocket validates
  the same cookie before accepting the connection.
- **Passwords** are hashed with `scrypt` (per-password salt, constant-time
  comparison). Only `scrypt$…` strings are stored.
- **Sessions** are 256-bit random tokens; only their SHA-256 digest is stored.
- **Secrets** are Fernet-encrypted before they reach the database. The key lives
  in a separate `600` file, so a stolen database alone is not enough.
- **Log redaction** scrubs registered secret values and credential-shaped
  patterns from every log record.
- **Opened projects are a trust boundary.** Opening a folder lets Solo read it
  (and, from Phase 2, let the agent write in it). The path policy:
  - paths are fully resolved, so a symlink cannot be used to escape a rule;
  - `/proc`, `/sys`, `/dev`, `/etc`, `/boot`, `/run`, `/root` are always
    rejected, on every deployment;
  - the Solo `data/` directory is always rejected — it holds the master key;
  - by default any other readable folder is allowed (local-first, single user);
  - set `ALLOW_ANY_PROJECT_PATH=false` and list `PROJECT_ROOTS` to lock it down
    — **recommended if you expose Solo beyond your own machine.**
- **The browser never supplies a filesystem path** that Solo has not shown it:
  the directory browser lists directory names only, and every path is validated
  again server-side.
- **Upload safety.** ZIP extraction rejects `..`, absolute paths, drive-letter
  prefixes and symlink entries, and enforces entry-count and size limits.
- **CSRF.** `HttpOnly` + `SameSite=Lax` cookies, plus a same-origin check on
  state-changing requests.
- **Response headers**: `nosniff`, `X-Frame-Options: DENY`, `no-referrer`.
- **Container**: non-root user, `no-new-privileges`.

> **HTTPS.** The session cookie is marked `Secure` automatically when the
> request arrives over HTTPS. Before exposing Solo on the public internet, put
> it behind a TLS reverse proxy or a tunnel — see
> [docs/deployment.md](docs/deployment.md). Plain HTTP on a public IP is not
> safe for entering API keys.

---

## Testing

```bash
# Backend — 194 tests, 91% coverage
cd backend && ../venv/bin/python -m pytest --cov=app --cov-report=term-missing

# Frontend — 39 tests
cd frontend && npm test

# Type checking
cd frontend && npm run typecheck

# End-to-end against a real running server — 53 checks
./scripts/e2e.sh
```

The end-to-end script starts a real server on a throwaway port and proves the
whole path: health → login → create → open in place → state tree → memory →
config → question → coding task → live events → steering → persisted state → SPA
served → removing an opened project leaves files byte-for-byte unchanged.

Coverage includes task-state transitions, credential redaction and encryption at
rest, ZIP extraction safety, the project path policy, provider-adapter error
handling, restart recovery, and every Create/Open/Import flow.

---

## Project layout

```
.
├── solo.sh                 native install and lifecycle (install/start/stop/logs/update/doctor)
├── install.sh              one-command installer (auto | --docker | --native)
├── docker-compose.yml      single-service Docker deployment
├── Dockerfile              two-stage build: Node builds the UI, Python serves it
├── backend/
│   └── app/
│       ├── adapters/       coding-agent contract + simulator + Pi probe
│       ├── api/            HTTP + WebSocket routers
│       ├── repositories/   all database access
│       ├── services/       auth, settings, projects, project store, paths, orchestration
│       ├── config.py       environment-driven settings
│       ├── domain.py       task/event/intent vocabulary
│       ├── models.py       SQLAlchemy schema
│       ├── security.py     hashing, tokens, secret cipher
│       └── main.py         app factory
├── frontend/
│   └── src/
│       ├── components/     header, auth, settings, project dialog, directory browser, Dockview
│       ├── panels/         Conversation, Activity, Inspector, Project state
│       ├── state/          workspace provider
│       └── utils/          formatting helpers
├── scripts/                dev.sh, e2e.sh, backup.sh, restore.sh
├── docs/                   architecture, projects, deployment, development, API
└── project-report/         engineering report per phase
```

---

## Managing the install

### Native

```bash
./solo.sh status      # is it running and healthy?
./solo.sh start
./solo.sh stop
./solo.sh restart
./solo.sh logs        # follow the log
./solo.sh update      # git pull, reinstall deps, rebuild UI, restart
./solo.sh doctor      # check prerequisites without changing anything
```

Logs: `data/solo.log`. PID: `data/solo.pid`.

### Docker

```bash
docker compose logs -f
docker compose restart
docker compose down
docker compose up -d --build     # update
./scripts/backup.sh              # archive database + key + secrets + workspaces
./scripts/restore.sh <archive>   # restore (asks for confirmation)
```

### Development

```bash
python3 -m venv venv && ./venv/bin/pip install -r backend/requirements-dev.txt
(cd frontend && npm ci)
./scripts/dev.sh          # backend :8080 + Vite :5173 with /api proxied
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `port 8080 is already in use` | Change `APP_PORT` in `.env`, then `./solo.sh restart`. |
| `Node.js 20+ and npm are required` | Install Node, or use `./install.sh --docker`. |
| `Python 3.10+ is required` | Install a newer Python, or use `./install.sh --docker`. |
| Docker warning, native install used | Add your user to the `docker` group and re-login: `sudo usermod -aG docker $USER`. |
| Sign-in succeeds then immediately 401 | Cookies blocked, or a `Secure` cookie over plain HTTP. Solo auto-detects the scheme; clear cookies and check `SESSION_COOKIE_SECURE`. |
| `that location is not allowed` | The folder is a blocked system path, the Solo `data/` directory, or outside `PROJECT_ROOTS` when `ALLOW_ANY_PROJECT_PATH=false`. |
| `cannot write project metadata` | The project folder is not writable by the user running Solo. |
| `git` shows `.solo/` as untracked | Inside a `.solo/` folder, a generated `.gitignore` normally hides it. Delete that file if you *want* to commit project state. |
| Pi badge is grey | The `pi` binary is not on `PATH`. Expected in this phase; relevant from Phase 2. |
| Task shows `RECOVERY_REQUIRED` | Solo restarted while a task was in flight. It never assumes interrupted work succeeded. |
| Voice control is disabled | Live voice arrives in Phase 4; the control is disabled with a label rather than pretending to work. |
| Layout looks broken | `localStorage.removeItem('solo.layout.v1')` and reload. |

---

## Roadmap

| Phase | Scope |
|---|---|
| **1 ✅** | Deployable shell: auth, settings, tiled UI, task pipeline, tests, Docker + native install |
| **1.5 ✅** | Project model: Create / Open in place / Import, `.solo` state store, state tree, memory, per-project config |
| **2** | Pi RPC subprocess: JSONL over stdio, request correlation, steering, cancellation, real file and test events |
| **3** | OpenRouter: structured intent classification, bounded context, project Q&A, progress summaries |
| **4** | ElevenLabs: signed-URL voice session, live transcript, text fallback |
| **5** | Spoken progress: contextual updates, TTS queue, interruption handling |
| **6** | Hardening: real-server smoke test, migrations, reverse-proxy guide |

Out of scope for the MVP: multi-user accounts, teams/billing, a plugin
marketplace, vector memory, concurrent writers per project, and a code editor.

---

## Documentation

- [docs/architecture.md](docs/architecture.md) — modules, data model, event flow
- [docs/projects.md](docs/projects.md) — the project model and state store
- [docs/deployment.md](docs/deployment.md) — Docker, HTTPS, backup/restore, updates
- [docs/development.md](docs/development.md) — workflow, conventions, adding an adapter
- [docs/api.md](docs/api.md) — REST + WebSocket reference
- [project-report/](project-report/) — engineering report, per phase

---

## License

[MIT](LICENSE)
