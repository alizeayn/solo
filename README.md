<div align="center">

# Solo

**A voice-first AI workspace for real software projects.**

Talk to a coding agent, watch it work, and keep every decision and change on your own machine.

[![Tests](https://img.shields.io/badge/tests-478%20passing-brightgreen)](#testing)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![Node](https://img.shields.io/badge/node-20%2B-green)](https://nodejs.org)

</div>

---

## Why Solo

Working with a coding agent usually means living in a terminal: reading a wall of
tool calls, losing context, scrolling back to find what changed, and re-explaining
your intent every few turns.

Solo takes the opposite position. **The conversation is the interface, and voice
is its primary channel.** You speak or type, the agent works inside your project,
and Solo tells you what mattered — in a sentence, not a log. Everything it knows
and everything it changed stays in a folder you own.

Three convictions shape the design:

**1. Voice-native, not voice-enabled.**
Speech is not a bolt-on. Agent activity flows through a narration pipeline that
decides what is worth saying, in what order, and what to drop when you start
talking. Today that pipeline records and displays; audio is the next chapter.
The architecture is already built around it.

**2. Your project stays yours.**
Solo does not copy your repository into a proprietary store. It adds a `.solo/`
directory next to your code, so state, memory and task history travel with the
project. Close Solo and your repository is exactly where you left it.

**3. Own your dependencies.**
Solo installs and runs its **own** Pi Agent in an isolated directory. If you
already use Pi for other work, Solo will never read, write or execute that
installation — and it never silently falls back to it.

---

## What it does

| | |
|---|---|
| 🎙 **Voice-first conversation** | A narration pipeline turns agent activity into short, ordered, non-overlapping lines. Barge-in drops what is no longer relevant. Audio playback arrives in the next release; the visible transcript and the pipeline are already real. |
| 🤖 **Real code changes** | The Pi Agent runs inside the project you opened and actually creates and modifies files — not a simulation. |
| ✅ **Verification built in** | Pyright checks the files the agent changed and reports type errors in the workspace. |
| 🧠 **An orchestrator that plans** | An OpenRouter model classifies intent, decomposes compound requests into an ordered, dependency-aware queue, and summarises what happened. Without a key it falls back to deterministic rules, so nothing stops working. |
| 🗂 **Projects in place** | Create a project or open an existing folder. Nothing is copied or uploaded. |
| 📁 **Portable project state** | Configuration, memory, sessions, task history and a structured state tree live in `<project>/.solo/`. |
| 🔐 **Secure by default** | Single-user authentication, encrypted credentials, path-boundary enforcement, log redaction, and an agent runtime you own. |
| 🎨 **Dark, light or automatic** | A full theme system, following your operating system if you prefer. |
| ⬆️ **Updates in place** | `./solo --update` rebuilds only what changed and keeps every project, credential and session. |

---

## How it works

```
  Voice / text
       │
       ▼
  ┌─────────────────┐   intent, plan, summary   ┌──────────────────┐
  │   Orchestrator  │ ────────────────────────► │ OpenRouter model │
  │  (task routing) │ ◄──────── JSON, validated │  (optional)      │
  └────────┬────────┘                           └──────────────────┘
           │ prioritised queue
           ▼
  ┌─────────────────┐   pi --mode rpc (JSONL)   ┌──────────────────┐
  │  Task pipeline  │ ────────────────────────► │  Pi Agent        │
  │  events · state │ ◄──── normalised events   │  (isolated)      │
  └────────┬────────┘                           └──────────────────┘
           │                                            │
           │                                            ▼
           │                                     your project files
           ▼
  ┌─────────────────┐
  │ Narrator        │  what is worth saying, in what order
  └────────┬────────┘
           ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ Workspace — Conversation · Voice · Activity · Write · Inspector │
  └─────────────────────────────────────────────────────────────┘
```

**Adapters keep providers replaceable.** The coding agent, the orchestration model
and the future voice transport each sit behind a small interface, so swapping one
never touches the core.

**Only milestones are spoken.** Tool calls are never narrated. Progress
summaries, errors, decisions and the final result are — and a newer summary
replaces a queued older one rather than saying "found the module" after "the
tests pass".

---

## Requirements

- **Python 3.10+** and **Node.js 20+** — or **Docker** with Compose v2.
- A model credential is **optional**. Solo works without one, using a built-in
  simulator and deterministic rules, so you can explore everything first.

---

## Installation

### One command

```bash
git clone https://github.com/alizeayn/solo.git
cd solo
./install.sh
```

The installer picks the best available path:

- **Docker** when the daemon is reachable — builds an image and starts a container.
- **Native** otherwise — creates a virtualenv, installs dependencies, builds the
  web UI, installs Solo's own Pi Agent, and starts the server.

Either way it prints the URL, the username `admin`, and a **one-time password**:

```
──────────────────────────────────────────────────────────────
 Solo is running  (version 2.2.0)
──────────────────────────────────────────────────────────────
 Local:  http://127.0.0.1:8080
 User:   admin
 Pass:   hBGsaHp32fW5NQvGmGaroDXI
──────────────────────────────────────────────────────────────
```

Force a specific path when you want it:

```bash
./install.sh --native     # never use Docker
./install.sh --docker     # require Docker
./install.sh --no-start   # prepare everything, start nothing
```

### Docker Compose

```bash
docker compose up -d --build
docker compose logs -f
```

State lives in the `solo-data` volume, so rebuilds keep your projects and
credentials.

### What the installer creates

| Path | Purpose |
|---|---|
| `venv/` | Python virtualenv (native install) |
| `frontend/dist/` | The built web UI |
| `data/app.db` | SQLite: projects, tasks, events, messages |
| `data/master.key` | Encryption key for stored credentials, mode `600` |
| `data/pi-runtime/` | **Solo's own Pi Agent** — never your desktop installation |
| `data/pi/agent/` | Pi's configuration *for Solo*: credentials, model catalog |
| `data/workspaces/` | Projects created or imported by Solo |
| `.env` | Operational settings, mode `600` (no secrets) |

Everything lives inside the checkout, so uninstalling is `rm -rf`. Only `data/`
and `.env` matter when upgrading.

---

## First run

1. Open the printed URL and sign in with the generated password.
2. **Settings → Account** — change the password if you like. Both the username and
   the password can be managed from the workspace.
3. **Settings → Orchestrator** — paste an OpenRouter key, test it, retrieve
   models, pick one. This model handles intent, planning and summaries.
4. **Settings → Pi Agent** — choose a provider, add its API key, verify it, pick a
   model. This is the model that writes your code.
5. **Create Project** or **Open Project**, then describe what you want.

---

## Configuration

### Models

Both models are configured in the workspace — no terminal, no config files.

**Orchestrator (OpenRouter)** — intent detection, task decomposition,
prioritisation, progress summaries, project questions. Disable it and Solo falls
back to deterministic rules.

**Pi Agent (the coding agent)** — provider, credentials and model. Saving a
credential writes it to Solo's own `auth.json` (mode `600`), exactly as Pi's
`/login` does, and refreshes Solo's model catalog. The UI distinguishes three
states and never claims more than was verified:

| State | Meaning |
|---|---|
| **not configured** | Pi has no credential for this provider |
| **configured** | A credential is stored and Pi reports it ready |
| **verified** | A real request succeeded with the selected model |

### Environment variables

`Solo` reads `.env`. **Never put API keys in it** — those live encrypted in the
database.

| Variable | Default | Purpose |
|---|---|---|
| `APP_PORT` | `8080` | The single user-facing port |
| `APP_HOST` | `0.0.0.0` | Bind address |
| `APP_DATA_DIR` | `./data` | Database, key, secrets, workspaces, Pi runtime |
| `APP_ENV` | `development` | `production` for deployed installs |
| `SESSION_TTL_HOURS` | `168` | Session lifetime |
| `SESSION_COOKIE_SECURE` | *(auto)* | `Secure` cookie flag; auto sets it only over HTTPS |
| `AGENT_BACKEND` | `auto` | `auto` uses Solo's Pi runtime when installed, else the simulator |
| `PI_EXECUTABLE` | *(empty)* | Optional escape hatch; must be an **absolute path**. A bare `pi` is refused, so Solo cannot silently use the host installation |
| `PI_RUNTIME_DIR` | `<data>/pi-runtime` | Where Solo installs its own Pi Agent |
| `PI_AGENT_DIR` | `<data>/pi/agent` | Pi's configuration for Solo — never `~/.pi/agent` |
| `PI_RUN_TIMEOUT_SECONDS` | `1800` | Wall-clock limit for one coding task |
| `ORCHESTRATOR_ENABLED` | `true` | Use the OpenRouter model for planning and summaries |
| `CHECKS_ENABLED` | `true` | Run Pyright after a task |
| `MAX_UPLOAD_MB` | `200` | Project ZIP import limit |
| `ALLOW_ANY_PROJECT_PATH` | `true` | Allow opening any readable directory (set `false` to restrict to `PROJECT_ROOTS`) |
| `LOG_LEVEL` | `INFO` | Secrets stay redacted at every level |

A full list with comments is in [`.env.example`](.env.example).

---

## Using Solo

### The workspace

A tiled interface you can rearrange freely. Layout is saved per browser, and
moving or closing a panel never affects the work in progress.

| Panel | What it is for |
|---|---|
| **Conversation** | The primary surface. Speak or type; the transcript and the voice control live here. |
| **Voice** | What the agent has said or is about to say, with barge-in controls. |
| **Activity** | The monitor: status, changed files, test results, static checks and the activity timeline. |
| **Write** | Open, edit, save or upload a file in the project. |
| **Inspector** | Task history, the orchestrator's plan, and the project's state tree, memory and configuration. |

Below 900 px the tiled layout becomes tabs.

### Working with the agent

Ask for a change:

> *"Create a module for configuration loading and write tests for it."*

Because that is two pieces of work, the Orchestrator decomposes it into an ordered,
dependency-aware plan, records it in the project's state, and runs the first step.
The rest run in sequence as each completes; a failed step stops the chain rather
than pressing on.

Ask a question at any time:

> *"Where is the config parsed?"*

Questions are answered from a bounded snapshot of the current project and task
state. They do not interrupt a running task.

Change direction mid-task:

> *"Also handle the `SOLO_CONFIG` environment variable."*

The instruction is steered into the running agent **and** recorded in the
project's working memory with how it was applied, so nothing you said is lost.

Stop cleanly:

> *"Stop."*

Cancellation is requested and confirmed — Solo never reports a task as cancelled
because a command was sent.

### Projects

Solo treats three operations as genuinely different:

| | **Create** | **Open** | **Import ZIP** |
|---|---|---|---|
| Does | Makes a new folder with Solo state | Adopts a folder **in place** | Extracts into the managed folder |
| Copies files | — | **Never** | Yes (the only path that does) |
| On delete | Removes the folder | **Only unregisters — your files are untouched** | Removes the folder |

Each project carries its own state:

```
<project-root>/.solo/
├── project.json      identity — portable to another machine
├── config.json       tree, memory and session settings
├── state/tree.json   the structured project state tree
├── memory/           decisions, facts and notes
├── sessions/         conversation transcripts
└── tasks/            task records with changed files and events
```

---

## Security

Solo can run code and edit files, so it is protected by default.

- **Authentication is mandatory.** Every API route except health and first-run
  setup requires a session; the WebSocket validates the same cookie before
  accepting the connection.
- **Passwords** are hashed with `scrypt` and compared in constant time. A session
  is a 256-bit token whose SHA-256 digest is the only thing stored.
- **Credential changes require the current password**, even from an authenticated
  session, and changing the password signs out every other device.
- **Secrets** are encrypted at rest with a key held in a separate `600` file, and
  are never returned to the browser — only `{configured: true, masked: "****abcd"}`.
- **Logs are redacted.** Credential-shaped strings and registered secret values
  never reach a log line.
- **Paths are a boundary.** Archive extraction rejects traversal, absolute paths,
  symlinks and bombs; file writes are confined to the project root; uploads
  cannot choose a location.
- **The Pi runtime is isolated.** Solo installs and invokes its own copy with an
  absolute path, never through `PATH`, and its configuration lives in Solo.

> **Before exposing Solo beyond your own machine:** put it behind HTTPS. Set
> `ALLOW_ANY_PROJECT_PATH=false` with an explicit `PROJECT_ROOTS` list, and use a
> reverse proxy with a valid certificate. See
> [docs/deployment.md](docs/deployment.md).

---

## Updating

```bash
cd ~/Desktop/solo
./solo --update          # or: ./solo.sh update
```

Projects, memory, sessions, credentials and workspace state all survive. The
updater backs up the database, key, secrets and `.env`, then **rebuilds only what
changed** — backend dependencies, frontend dependencies, the web UI, Solo's Pi
runtime and database migrations each have their own trigger. An update whose only
change is the version performs no rebuild steps at all.

```bash
./solo.sh version               # installed vs available, commits behind
./solo.sh update --no-restart   # apply changes, restart later
./solo.sh update --force        # allow a dirty tree or a diverged branch
```

If an update fails it **rolls back** the checkout and the data and restarts the
previous version rather than leaving a partial state. See
[docs/updating.md](docs/updating.md).

---

## Current status and limitations

Stated plainly, because a workspace that runs code should be honest about what it
does and does not do.

**Working and verified end to end:** authentication and account management;
project create/open/import; the isolated Pi Agent runtime executing real coding
tasks through chat; live activity events; task and orchestration state; the
prioritised plan queue; Pyright verification; dark/light themes; in-place updates.

**Not yet implemented:**

- **Audio.** The narration pipeline — what to say, in what order, what to drop —
  is real and covered by tests, but no audio transport is wired up yet. The Voice
  panel shows the lines and says so.
- **Real-time speech in.** Conversation is typed. Voice input and the ElevenLabs
  conversational session are the next milestone.
- **A version-compatibility gate in the updater.** It detects change and refuses a
  diverged branch, but does not yet refuse "this release is too new for this
  installation".
- **Solo is not a sandbox.** The agent runs with the permissions of the Solo
  process inside a directory you chose. Solo bounds *which* directories can be
  opened, not what the agent may do inside one.
- **The Docker image is built from source but not verified in this repository's
  test runs**, because CI has no Docker daemon. The native install path is
  verified end to end.

---

## Development

```bash
python3 -m venv venv
./venv/bin/pip install -r backend/requirements-dev.txt
(cd frontend && npm ci)

./scripts/dev.sh              # backend :8080 + Vite :5173, /api proxied
```

Backend only:

```bash
cd backend && ../venv/bin/uvicorn app.main:app --reload
```

API docs: <http://127.0.0.1:8080/api/docs>

### Testing

```bash
# Backend — 375 tests
cd backend && ../venv/bin/python -m pytest --cov=app

# Frontend — 103 tests
cd frontend && npm test && npm run typecheck

# End to end with the built-in simulator — 53 checks, no credentials needed
./scripts/e2e.sh

# End to end with the real Pi Agent — 39 checks (needs a model credential)
./scripts/e2e-live.sh
```

The suite covers task-state transitions, credential encryption and redaction,
archive and file-path safety, the Pi RPC protocol (against a protocol-accurate
fake), runtime isolation, the narration pipeline, the orchestration state machine
and account management. `e2e-live.sh` submits a real coding task and asserts the
file exists on disk — and passes with the globally installed `pi` removed from
`PATH`, which is the isolation guarantee.

---

## Project structure

```
.
├── backend/app/
│   ├── adapters/       Pi RPC client, event translator, session manager, simulator
│   ├── api/            HTTP + WebSocket routers
│   ├── repositories/   all database access
│   └── services/       auth, account, settings, projects, store, runtime,
│                       orchestrator, narration, checks
├── frontend/src/
│   ├── components/     header, auth, settings, project dialog, Dockview, voice
│   ├── panels/         Conversation, Activity, Write, Inspector, Plan, State
│   ├── hooks/          theme, WebSocket, media query, voice input, playback
│   └── state/          workspace and theme providers
├── docs/               architecture, projects, pi-agent, orchestrator, voice, api
├── ElevenLabs Docs/    verified ElevenLabs API notes (models, TTS, STT, voices)
├── "Pi Agent Docs"/    Pi protocol reference (v1.1.0) + integration notes
├── scripts/            dev, e2e, e2e-live, backup, restore
├── solo.sh             install, run, update
└── install.sh          one-command installer
```

---

## Roadmap

The direction is a workspace you talk to.

1. **Voice in and out** — the ElevenLabs conversational session, speech input,
   and audio playback for the narration pipeline that already exists.
2. **Deeper reasoning** — retrieval-backed project questions, and re-planning that
   consumes the mid-task instructions Solo already records.
3. **Longer memory** — semantic recall across sessions, building on the project
   store rather than replacing it.
4. **More agents** — the adapter contract already allows a second coding backend.

---

## Contributing

Issues and pull requests are welcome. Before opening a pull request:

```bash
cd backend && ../venv/bin/python -m pytest
cd frontend && npm test && npm run typecheck
./scripts/e2e.sh
```

Please keep the module boundaries intact: business logic in `services/`, database
access in `repositories/`, provider specifics in `adapters/`, and no new
dependency on a global tool. [docs/development.md](docs/development.md) documents
the conventions and the historical traps worth not repeating.

Commits follow [docs/commit-policy.md](docs/commit-policy.md): one commit per
*intent*, not per stage or per file, each one leaving the repository able to build
and start.

## Documentation

- [docs/architecture.md](docs/architecture.md) — modules, data model, event flow
- [docs/projects.md](docs/projects.md) — the project model and `.solo` store
- [docs/pi-agent.md](docs/pi-agent.md) — how Pi is integrated, isolated and configured
- [docs/orchestrator.md](docs/orchestrator.md) — planning, prioritisation and state
- [docs/voice.md](docs/voice.md) — the voice loop, ElevenLabs integration, and its limits
- [docs/updating.md](docs/updating.md) — in-place updates, versioning, rollback
- [docs/deployment.md](docs/deployment.md) — Docker, HTTPS, backup and restore
- [docs/api.md](docs/api.md) — REST and WebSocket reference
- [ElevenLabs Docs/](ElevenLabs%20Docs/) — verified ElevenLabs API notes (models, TTS, STT, voices)

## License

[MIT](LICENSE)
