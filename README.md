# Voice-First AI Workspace

A single-user, browser-based workspace for driving a coding agent through
**voice and text**. Open a project, ask for a change, watch meaningful progress,
ask questions while work is running, and collect the result — without living in
a terminal.

> **Implementation status: Phase 1 complete.**
> The deployable shell is built, tested and documented: authentication,
> settings, workspace management, a tiled Dockview UI, the full task/event
> pipeline and an end-to-end smoke test all pass.
> The **coding agent is a deterministic simulator** in this phase — it emits
> realistic events but does not modify files. Real Pi RPC (Phase 2), OpenRouter
> (Phase 3), ElevenLabs voice (Phase 4) and proactive TTS (Phase 5) are next.
> See [Roadmap](#roadmap).

---

## Table of contents

- [What works today](#what-works-today)
- [Quick start (Docker)](#quick-start-docker)
- [Quick start (development)](#quick-start-development)
- [Configuration](#configuration)
- [Security model](#security-model)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Roadmap](#roadmap)
- [Troubleshooting](#troubleshooting)
- [Documentation](#documentation)

---

## What works today

| Capability | Status |
|---|---|
| FastAPI + React/TypeScript app on **one origin** | ✅ |
| Dark, responsive UI with a tiled **Dockview** workspace | ✅ |
| Three panels: Conversation, Coding Agent Activity, Inspector | ✅ |
| Layout persistence + automatic fallback to a safe default | ✅ |
| Stacked tab layout on narrow screens | ✅ |
| Single-user auth, hashed password, HttpOnly session cookie | ✅ |
| Encrypted-at-rest API keys, masked in every response | ✅ |
| Settings UI with real "Test connection" for OpenRouter / ElevenLabs / Pi | ✅ |
| Create a project or import a ZIP (Zip-Slip, symlink and bomb safe) | ✅ |
| Task lifecycle with persisted state and normalized events | ✅ |
| Live push over WebSocket; survives panel moves/closes | ✅ |
| Intent routing: question vs. steer vs. stop vs. new task | ✅ |
| Restart recovery: in-flight tasks become `RECOVERY_REQUIRED` | ✅ |
| Docker Compose, `install.sh`, backup/restore scripts | ✅ |
| Real Pi RPC subprocess | 🔜 Phase 2 |
| OpenRouter summaries / Q&A / routing | 🔜 Phase 3 |
| ElevenLabs live voice | 🔜 Phase 4 |
| Proactive spoken progress + speech queue | 🔜 Phase 5 |

---

## Quick start (Docker)

Requirements: a Linux server with Docker and the Compose v2 plugin.

```bash
git clone https://github.com/alizeayn/solo.git
cd solo
./install.sh
```

`install.sh` will:

1. verify Docker and the Compose plugin,
2. create `.env` from `.env.example` (mode `0600`) if missing,
3. check that the chosen port is free,
4. generate a one-time admin password and print it — **it is shown once**,
5. build the image and start the service,
6. wait for the health check and print the URL.

Then open `http://<server-ip>:8080`, sign in as `admin`, and add your
credentials in **Settings**.

The generated password is written to `./initial-admin-password`, bind-mounted
into the container, consumed on first start and deleted automatically.

Day-to-day commands:

```bash
docker compose logs -f         # follow logs
docker compose restart         # restart
docker compose down            # stop
docker compose up -d --build   # update after git pull
./scripts/backup.sh            # archive database + secrets + workspaces
./scripts/restore.sh <archive> # restore (destructive, asks for confirmation)
```

> **HTTPS:** before exposing this on the public internet, put it behind a
> reverse proxy with a valid certificate or a secure tunnel. Plain HTTP on a
> public IP is not safe for entering API keys. See
> [docs/deployment.md](docs/deployment.md).

---

## Quick start (development)

Requirements: Python 3.12+, Node 20+, and the `pi` CLI on `PATH` (optional).

```bash
# Backend
python3 -m venv venv
./venv/bin/pip install -r backend/requirements-dev.txt

# Frontend
cd frontend && npm ci && cd ..

# Run both (backend :8080, Vite :5173 with /api proxied)
./scripts/dev.sh
```

Open `http://127.0.0.1:5173`. On first load the UI shows the setup screen and
asks you to create the admin password.

Run one side only with `./scripts/dev.sh backend` or `./scripts/dev.sh frontend`.

---

## Configuration

Operational settings live in `.env` (see `.env.example`). **No secrets belong
in this file.**

| Variable | Default | Purpose |
|---|---|---|
| `APP_PORT` | `8080` | Public port (the single user-facing origin) |
| `APP_HOST` | `0.0.0.0` | Bind address |
| `APP_DATA_DIR` | `./data` | SQLite DB, encryption key, secrets, workspaces |
| `APP_ENV` | `development` | `production` enables `Secure` cookies |
| `SESSION_TTL_HOURS` | `168` | Session lifetime |
| `MAX_UPLOAD_MB` | `200` | ZIP upload limit |
| `MAX_ZIP_ENTRIES` | `20000` | Extraction guard |
| `MAX_UNCOMPRESSED_MB` | `2048` | Decompression-bomb guard |
| `LOG_LEVEL` | `INFO` | `DEBUG`…`ERROR` |
| `AGENT_BACKEND` | `mock` | `mock` (Phase 1) or `pi` (Phase 2) |
| `ADMIN_PASSWORD` | – | One-time bootstrap password (used by `install.sh`) |
| `FRONTEND_DIST` | – | Directory of the built SPA for the backend to serve |

Provider credentials (OpenRouter key, ElevenLabs key, agent ID, Pi
provider/model) are entered in the **Settings** screen and stored server-side,
encrypted, in `<APP_DATA_DIR>/secrets.enc`, with the encryption key in a
separate `<APP_DATA_DIR>/master.key` (`0600`).

---

## Security model

The app can run code and edit files, so it is protected by default.

- **Authentication is mandatory.** Every API route except `/api/health` and the
  first-run `/api/auth/*` endpoints requires a session. The WebSocket handshake
  validates the same cookie before accepting the connection.
- **Passwords** are hashed with `scrypt` (per-password salt, constant-time
  comparison). Only `scrypt$…` strings are stored.
- **Sessions** are random 256-bit tokens; only their SHA-256 digest is stored,
  so a database leak yields no usable cookie.
- **Secrets** are Fernet-encrypted before insertion. The key lives in a
  separate file with `0600` permissions. A stolen database alone is not enough.
- **Secrets never leave the server.** The API returns only
  `{configured: true, masked: "****abcd"}`.
- **Log redaction** scrubs registered secret values and credential-shaped
  patterns (`sk-…`, `sk_…`, JWTs, `authorization:`/`api_key:` lines) from every
  log record.
- **Upload safety.** ZIP extraction rejects absolute paths, `..` traversal,
  symlink entries and drive-letter prefixes, and enforces entry-count and
  uncompressed-size limits. No archive content is ever executed.
- **Filesystem boundary.** Browser clients never send a path. Projects live
  under `<APP_DATA_DIR>/workspaces/`, and every resolved path is re-validated
  against that root.
- **CSRF.** Session cookies are `HttpOnly` + `SameSite=Lax`, and mutating
  requests carrying a cross-origin `Origin` header are rejected.
- **Middleware** sets `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY` and `Referrer-Policy: no-referrer`.
- **Container** runs as a non-root user with `no-new-privileges`.

---

## Testing

```bash
# Backend: 123 tests
cd backend && ../venv/bin/python -m pytest --cov=app --cov-report=term-missing

# Frontend: 22 tests
cd frontend && npm test

# Type checking
cd frontend && npm run typecheck

# End-to-end against a real running server (26 checks)
./scripts/e2e.sh
```

Coverage of the backend is ~89 %. The suite covers task-state transitions,
credential redaction, ZIP extraction safety, provider-adapter error handling,
intent routing, restart recovery and the core API surface. `scripts/e2e.sh`
proves the full path: login → project → question → coding task → live events →
follow-up steering → terminal status → persisted state → SPA served.

---

## Project layout

```
.
├── backend/
│   ├── app/
│   │   ├── adapters/       # CodingAgentAdapter contract + mock + Pi probe
│   │   ├── api/            # HTTP + WebSocket routers
│   │   ├── repositories/   # all database access
│   │   ├── services/       # auth, settings, projects, intents, orchestration
│   │   ├── config.py       # env-driven settings
│   │   ├── domain.py       # task/event/intent vocabulary
│   │   ├── models.py       # SQLAlchemy schema
│   │   ├── security.py     # hashing, tokens, secret cipher
│   │   └── main.py         # app factory
│   └── tests/              # 123 tests
├── frontend/
│   └── src/
│       ├── api/            # typed API client
│       ├── components/     # header, auth, settings, Dockview layout
│       ├── panels/         # the three workspace panels
│       ├── state/          # workspace provider
│       └── utils/          # formatting helpers
├── scripts/                # dev.sh, e2e.sh, backup.sh, restore.sh
├── docs/                   # architecture, deployment, development, API
├── install.sh              # one-command installer
├── docker-compose.yml
└── Dockerfile
```

---

## Roadmap

| Phase | Scope |
|---|---|
| **1 ✅** | Deployable shell: auth, settings, projects, Dockview UI, task/event pipeline, Docker, tests |
| **2** | Pi RPC subprocess: JSONL over stdio, request-id correlation, steering, cancellation, real file/test events |
| **3** | OpenRouter: structured intent classification, bounded context snapshots, project Q&A, progress summaries |
| **4** | ElevenLabs: signed-URL voice session, live transcript, text fallback |
| **5** | Live progress UX: contextual updates, TTS announcement queue, interruption handling |
| **6** | Hardening: restart recovery UX, installer idempotency, reverse-proxy docs, real-server smoke test |

Deliberately out of scope for the MVP: multi-user accounts, teams/billing, a
plugin marketplace, vector memory, concurrent writers per project, and a source
editor.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `port 8080 is already in use` | Change `APP_PORT` in `.env`, then `docker compose up -d`. |
| `permission denied … docker.sock` | Add your user to the `docker` group (`sudo usermod -aG docker $USER`) and re-login. |
| Page loads, all requests 401 | Session expired or cookie blocked. Sign in again; check `SESSION_TTL_HOURS`. |
| "Pi" badge is grey | The `pi` binary is not on `PATH` for the process running the app. Expected in the Phase 1 container. |
| Failed task with `RECOVERY_REQUIRED` | The app restarted while a task was in flight. The state was intentionally not assumed complete. |
| Voice control is disabled | Live voice arrives in Phase 4. The control is rendered disabled with a note rather than pretending to work. |
| Layout looks broken | Clear the stored layout: `localStorage.removeItem('solo.layout.v1')` and reload. |

---

## Documentation

- [docs/architecture.md](docs/architecture.md) — modules, data model, event flow
- [docs/deployment.md](docs/deployment.md) — Docker, HTTPS, backup/restore, updates
- [docs/development.md](docs/development.md) — dev workflow, conventions, adding an adapter
- [docs/api.md](docs/api.md) — REST + WebSocket reference

---

## License

[MIT](LICENSE)
