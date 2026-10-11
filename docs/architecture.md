# Architecture

The MVP is a **modular monolith**: one FastAPI application serving a REST API, a
WebSocket and the built React frontend from a single origin. Modules are
separated by responsibility, not by deployment.

---

## 1. Request and event flow

```
                     ┌──────────────────────── browser ────────────────────────┐
                     │  React + TypeScript + Dockview                          │
                     │  WorkspaceProvider  ── useWebSocket ──┐                 │
                     └──────────┬───────────────────────────-┼─────────────────┘
                       REST     │                            │ live events
                                ▼                            ▼
                     ┌──────────────────────────────────────────────────────┐
                     │ FastAPI (single origin, session-authenticated)       │
                     │  api/ ── services/ ── repositories/ ── SQLite        │
                     │                 └── adapters/ ── coding agent        │
                     └──────────────────────────────────────────────────────┘
```

1. The browser sends a message or starts a task over REST.
2. `OrchestratorService` classifies the intent and persists a task.
3. The adapter runs the task and emits **normalized** `AgentEvent`s.
4. The orchestrator persists each event, updates task state, and publishes it
   on the in-process `EventBus`.
5. Subscribed WebSockets push the message to the browser.
6. Panels render from state; nothing in the UI is authoritative.

---

## 2. Module map

| Module | Responsibility |
|---|---|
| `config.py` | Environment-driven settings (`pydantic-settings`). Secrets are *not* here. |
| `domain.py` | Task statuses, event types, intents, message roles, settings keys. |
| `models.py` | SQLAlchemy 2.0 declarative schema. |
| `db.py` | Async engine/session factory; SQLite PRAGMAs (FK on, WAL). |
| `security.py` | scrypt hashing, session tokens, Fernet `SecretCipher`, masking. |
| `logging_setup.py` | Log configuration + `RedactionFilter`. |
| `repositories/` | **All** database access. One class per aggregate. |
| `services/` | Business logic (see below). |
| `adapters/` | Provider integration behind a stable contract. |
| `services/pi_config.py` | Pi providers, credentials (via Pi's `auth.json`), model discovery and validation. |
| `services/openrouter.py` | Thin OpenRouter transport: key check, model list, JSON-constrained completions. |
| `services/orchestrator_brain.py` | The Orchestrator's reasoning: intent, planning, prioritisation, summaries, Q&A. |
| `services/orchestration_state.py` | Durable per-project working memory: queue, priorities, dependencies, notes. |
| `services/checks.py` | Pyright integration — the verification half of the harness. |
| `services/narration.py` | **Voice-native output.** Decides what is worth saying, orders it, coalesces stale lines, rate limits, and yields on barge-in. Phase 4 attaches an audio transport to it. |
| `services/account_service.py` | Username and password changes, with current-password confirmation and session revocation. |
| `services/pi_runtime.py` | Solo's own isolated Pi Agent: locate, install, verify, never `PATH`. |
| `api/pi.py`, `api/orchestrator.py`, `api/orchestration.py` | Settings-UI endpoints for Pi, OpenRouter and the plan. |
| `api/` | HTTP + WebSocket routers; validation and status-code mapping. |
| `container.py` | Builds and owns long-lived dependencies (the only place that picks concrete implementations). |
| `main.py` | App factory: lifespan, routers, middleware, static SPA. |

### Services

| Service | Responsibility |
|---|---|
| `AuthService` | First-run bootstrap, setup, login/logout, session resolution. |
| `SettingsService` | Encrypted storage, masking and live connection tests. |
| `ProjectService` | Create / open-in-place / import / delete; registers and initialises the per-project store. |
| `ProjectStoreService` | The `.solo` state store: manifest, config, memory, sessions, task records and the state tree. |
| `project_paths.py` | **The only place a path is judged.** Blocked list, optional allow-list, symlink-safe resolution, directory browsing. |
| `api/fs.py` | Directory listing for the Open Project browser (directories only). |
| `archive.py` | `safe_extract_zip` — the upload threat model lives here. |
| `project_scan.py` | Bounded project tree scanning and language summary. |
| `context.py` | Bounded `ContextSnapshot` and the Phase-1 offline answer path. |
| `intent.py` | Deterministic `IntentRouter` (Phase 3 adds an LLM classifier behind the same contract). |
| `event_bus.py` | In-process fan-out to WebSocket subscribers, with slow-consumer handling. |
| `orchestrator.py` | Task lifecycle, message routing, single-writer enforcement, persistence + broadcast. |

---

## 3. Data model

```
users ──< auth_sessions
projects ──< conversations ──< messages
projects ──< tasks ──< task_files
                └──< task_events
                └──< raw_logs
app_settings (key/value; secret rows are encrypted)
```

Each `projects` row points at a directory on disk and is accompanied by a
`.solo/` state store inside it. See [projects.md](projects.md) for the full
model.

Project rows carry two location fields:

- `location` — `managed` (created inside `APP_DATA_DIR/workspaces/`, with
  `root_path` a slug) or `external` (an existing directory, with `root_path` an
  absolute path).
- `metadata_dir` — the state directory name inside the project root.

Notable choices:

- **IDs are opaque hex strings** (`uuid4().hex`) for projects, conversations,
  tasks and messages, so they are safe in URLs and never encode a path.
- **`Task.status` is a string** matching `domain.TaskStatus`, keeping the DB
  readable and making new states a non-breaking addition.
- **`meta` / `data` JSON columns** carry structured, non-secret context. The
  ORM attribute is named `meta` because `metadata` is reserved by SQLAlchemy.
- **`raw_logs`** exists so verbose diagnostics are retained for debugging but
  never fed to a model wholesale. `raw_log_max_chars` caps each row.
- All access goes through repositories, so a PostgreSQL migration is an engine
  URL change plus dialect review — not a business-logic rewrite.

---

## 4. Project model

A project is a **directory on disk**. Solo adds a `.solo/` state store to it and
records a row in SQLite for indexing.

```
<project-root>/.solo/
├── project.json      identity (adopted when re-opening an existing store)
├── config.json       per-project configuration (deep-merged on update)
├── .gitignore        keeps Solo state out of the user's repository
├── state/tree.json   the structured project state tree
├── memory/           index + one file per entry
├── sessions/         index + one transcript per conversation
└── tasks/            index + one record per task (files + events)
```

Key properties:

- **Self-describing and portable.** Copy a folder, open it elsewhere, and its
  memory, sessions and task history come with it. On open, an existing
  `project.json` id is adopted unless another project already claims it.
- **Union on refresh.** Index nodes whose detail files still exist are preserved
  even when the local database does not know about them, so opening a project
  from another installation does not erase its history.
- **Bounded and exclusion-aware.** Depth, entry counts, retained records and
  memory size are all capped and configurable per project.
- **Atomic writes, best-effort sync.** Temp file + `os.replace`. A read-only
  project logs a warning instead of breaking a task; only initialisation fails
  loudly.
- **Ordered for observability.** A finished task is written to disk *before* its
  terminal status is broadcast, so a UI showing "completed" can always read the
  record.

### Path policy

`project_paths.py` is the single decision point:

1. resolve fully (symlinks followed) before any check;
2. must exist and be a directory;
3. always-blocked set (`/proc`, `/sys`, `/dev`, `/etc`, `/boot`, `/run`, `/root`,
   `/var/lib/docker`, `/var/lib/solo`) plus the Solo data directory;
4. optional allow-list via `ALLOW_ANY_PROJECT_PATH=false` + `PROJECT_ROOTS`;
5. managed projects additionally confined to the workspaces directory.

Browsers receive directory names only, and every path is re-validated on the
way back in.

---

## 5. Coding agent and orchestrator

The backend is a swap of one adapter, but Phase 2 added a decision layer above it
and a verification step beside it.

```
Chat ─► Orchestrator ─► OrchestrationState ─► TaskService ─► CodingAgentAdapter
          (OpenRouter +      (queue, notes,      (lifecycle,      ├── Mock (simulator)
           rules fallback)    priorities)         events)         └── Pi (RPC)
                                                                        │
                        ChecksService (Pyright) ◄── changed files ──────┘
```

- **`CodingAgentAdapter` is unchanged.** `PiCodingAgentAdapter` implements the
  same protocol as the simulator, so task lifecycle, event storage, the
  WebSocket and the UI needed no changes.
- **Process model:** one long-lived `pi --mode rpc` subprocess per project.
  Sessions are keyed by the resolved project directory. See
  [pi-agent.md](pi-agent.md).
- **Decision layer:** the Orchestrator model classifies, plans and summarises;
  the deterministic `IntentRouter` remains the permanent fallback so a missing
  key or a provider outage degrades rather than breaks. See
  [orchestrator.md](orchestrator.md).
- **Verification:** Pyright runs after a task settles, over the files the agent
  changed, and reports diagnostics as a `check.result` event.
- **Post-settle work is asynchronous.** The terminal status is broadcast first;
  summarisation, checks and queue advancement follow. A slow model can never
  delay the moment the user is told a task finished.

---

## 6. Task lifecycle

```
QUEUED ──▶ RUNNING ──┬──▶ COMPLETED
                     ├──▶ FAILED
                     ├──▶ CANCEL_REQUESTED ──▶ CANCELLED
                     ├──▶ WAITING_FOR_INPUT / PAUSE_REQUESTED / PAUSED
                     └──▶ RECOVERY_REQUIRED   (process died while in flight)
```

Rules enforced in code:

- **One active modifying task per project.** `TaskRepository.find_active`
  backs both the API guard (HTTP 409) and the intent router's decision to steer
  instead of starting a second writer.
- **Cancellation is a request, not a fact.** `cancel_task` sets
  `CANCEL_REQUESTED` and asks the adapter to stop; `CANCELLED` is only written
  when the adapter confirms.
- **Terminal states are sticky.** `_set_status` refuses to overwrite a terminal
  status, which closes the race where a shutdown cancellation lands just after
  completion.
- **Never assume success.** On startup, any non-terminal task is marked
  `RECOVERY_REQUIRED` with an explanatory error.

---

## 7. Event vocabulary

The rest of the app never parses provider protocol output. Each adapter
translates its records into these types (`domain.EventType`):

`task.created`, `task.status_changed`, `run.started`, `run.finished`,
`tool.started`, `tool.updated`, `tool.finished`, `file.changed`, `test.result`,
`progress.summary`, `error`, `message.received`, `assistant.message`.

Every event is persisted **before** it is broadcast, so a dropped WebSocket
never loses data — the UI can always re-fetch from REST.

---

## 8. Intent routing

`IntentRouter.classify(content, has_active_task)` returns one of
`CHAT_OR_EXPLAIN`, `STEER_ACTIVE_TASK`, `STOP_ACTIVE_TASK`,
`START_CODING_TASK`, `NEEDS_CLARIFICATION`.

Precedence (highest first):

1. Explicit stop/cancel command.
2. Steering marker (`also`, `instead`, `wait`, …) — only while a task runs.
3. Informational question (`what`, `why`, `how`, `explain`, `status`, …).
   These never start or steer a task, even if they contain a verb like
   "changed" or "add".
4. A request containing a coding verb.
5. Plain chat.

This precedence exists because an earlier version treated *"what files changed
so far?"* as a steering instruction. Deterministic rules are preferred where
they are unambiguous; Phase 3 adds an OpenRouter classifier **behind the same
contract**, with Pydantic-validated output.

---

## 9. Adapter contract

```python
class CodingAgentAdapter(Protocol):
    name: str
    async def start(self) -> None: ...
    async def run(self, *, task_id, prompt, cwd, on_event) -> AgentResult: ...
    async def steer(self, *, task_id, instruction) -> None: ...
    async def cancel(self, *, task_id) -> None: ...
    async def stop(self) -> None: ...
    async def health(self) -> dict: ...
```

- `MockCodingAgentAdapter` (Phase 1) emits a realistic, ordered event stream and
  performs **no** file modification. Its delay is configurable so tests run
  fast.
- `PiCodingAgentAdapter` (Phase 2) is present as a stub whose methods fail
  loudly rather than pretending to work. `build_adapter` is the single
  switch-over point; an unknown backend raises instead of silently degrading.

The orchestrator is unaware of which adapter is active.

---

## 10. Frontend state

`WorkspaceProvider` holds the active project, its tasks, messages and the live
event feed, and mirrors backend state rather than owning it.

- **The backend owns task state.** Closing, dragging or hiding a Dockview panel
  cannot affect a task — panels only render.
- **Selection lives in refs** for the WebSocket handler, so changing the
  selected task does not tear down and rebuild the socket.
- **Optimistic-free by design.** After sending a message the client re-fetches
  the transcript instead of guessing; the user's own message is not broadcast.
- **Layout persistence is non-critical.** `solo.layout.v1` in local storage is
  validated on load; corrupt or incompatible JSON is discarded and the default
  three-panel layout is rebuilt.

---

## 11. Appearance

Solo ships a dark and a light theme. Every colour is a CSS custom property defined
once per theme under `:root` and `:root[data-theme="light"]`; components consume
only those variables, so no component knows which theme is active.

`hooks/useTheme.ts` resolves a preference (`dark`, `light`, `system`) to an
effective theme and applies it as `data-theme` on `<html>`. The preference is
cached in `localStorage` and stored in Solo's settings: the cache exists so
`index.html` can apply the theme **before first paint** (no flash of the wrong
appearance), and the server copy exists so the choice follows the account to
another browser. `localStorage` is a cache of the server value, never the source
of truth. `DockLayout` picks the matching Dockview theme explicitly.

## 12. Extension points

| To add… | Change |
|---|---|
| A coding-agent backend | Implement the adapter protocol, register it in `build_adapter`. |
| An LLM-backed classifier | Implement the `classify` contract, inject it into `OrchestratorService`. |
| An intent or task type | Add to `domain.py`; the router and orchestrator switch on the enum. |
| A new panel | Add a component, register it in `DockLayout`'s `components` map. |
| A new event type | Add to `domain.EventType`; the timeline renders unknown types gracefully. |
| A project state node kind | Emit it from `_compose_tree` in `project_store.py`; the tree view renders unknown kinds. |
| A reasoning or voice model | Implement `OrchestratorBrain`'s four methods, or add a second consumer of `OrchestrationState`. |
| A different verification tool | Implement the `CheckResult` shape in `services/checks.py`; the UI renders any `tool`/`outcome`. |
| A storage backend | Swap the engine in `db.py`; repositories are the only DB consumers. |


---

## Voice

Voice is an architectural layer, not a feature bolted onto the chat.

`NarrationService` turns agent activity into short, ordered, non-overlapping
spoken lines and hands them to a **transport**. `ElevenLabsTransport` implements
that protocol using ElevenLabs text to speech; the default transport records
instead, which is what makes the whole pipeline testable without audio hardware
or an API key.

The important separation is between **activity** and **milestones**:

| | Pi Agent Activity | Orchestrator Milestones |
|---|---|---|
| Answers | what is the agent *doing* | what does the work *mean* |
| Unit | an event | a phase transition |
| Consumer | Activity panel | Milestone panel **and** the voice channel |

Reading raw activity aloud would recite tool calls. The voice channel consumes
the same structured milestone objects the UI renders — never raw events, and never
re-derived from text. Speech input is symmetrical: transcription produces text
that is posted to the existing message endpoint, so the agent pipeline is
untouched by the fact that the text was spoken.

See [voice.md](voice.md).
