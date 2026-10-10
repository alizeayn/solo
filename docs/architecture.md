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
| `api/` | HTTP + WebSocket routers; validation and status-code mapping. |
| `container.py` | Builds and owns long-lived dependencies (the only place that picks concrete implementations). |
| `main.py` | App factory: lifespan, routers, middleware, static SPA. |

### Services

| Service | Responsibility |
|---|---|
| `AuthService` | First-run bootstrap, setup, login/logout, session resolution. |
| `SettingsService` | Encrypted storage, masking and live connection tests. |
| `ProjectService` | Create/import/list/delete projects; path-boundary enforcement. |
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

## 4. Task lifecycle

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

## 5. Event vocabulary

The rest of the app never parses provider protocol output. Each adapter
translates its records into these types (`domain.EventType`):

`task.created`, `task.status_changed`, `run.started`, `run.finished`,
`tool.started`, `tool.updated`, `tool.finished`, `file.changed`, `test.result`,
`progress.summary`, `error`, `message.received`, `assistant.message`.

Every event is persisted **before** it is broadcast, so a dropped WebSocket
never loses data — the UI can always re-fetch from REST.

---

## 6. Intent routing

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

## 7. Adapter contract

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

## 8. Frontend state

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

## 9. Extension points

| To add… | Change |
|---|---|
| A coding-agent backend | Implement the adapter protocol, register it in `build_adapter`. |
| An LLM-backed classifier | Implement the `classify` contract, inject it into `OrchestratorService`. |
| An intent or task type | Add to `domain.py`; the router and orchestrator switch on the enum. |
| A new panel | Add a component, register it in `DockLayout`'s `components` map. |
| A new event type | Add to `domain.EventType`; the timeline renders unknown types gracefully. |
| A storage backend | Swap the engine in `db.py`; repositories are the only DB consumers. |
