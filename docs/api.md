# API reference

Base URL: the application origin. Interactive schema: `GET /api/docs`
(OpenAPI JSON at `/api/openapi.json`).

**Authentication.** Every endpoint below except `GET /api/health` and the
`/api/auth/*` endpoints requires the `solo_session` cookie issued by
`/api/auth/login` or `/api/auth/setup`. Unauthenticated requests receive
`401 {"detail": "authentication required"}`. Mutating requests carrying a
cross-origin `Origin` header are rejected with `403`.

**Secrets.** No response ever contains a raw API key. Secrets are reported as
`{"configured": true, "masked": "****abcd"}`.

---

## Pi Agent configuration

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/pi/status` | Runtime, backend, saved provider/model, live sessions |
| `GET` | `/api/pi/runtime?verify=` | Solo's own runtime: installed, verified, source, dirs, node |
| `POST` | `/api/pi/runtime/install?force=&verify=` | Install or upgrade Solo's isolated Pi Agent |
| `POST` | `/api/pi/runtime/verify` | Start the runtime and run a command |
| `GET` | `/api/pi/providers` | Providers known to Pi plus a curated fallback list |
| `GET` | `/api/pi/models?provider=&refresh=` | Pi's resolved catalog |
| `POST` | `/api/pi/models/refresh` | Runs `pi update --models` |
| `GET` | `/api/pi/providers/{id}/auth` | `{ready, reason, auth_type}` — never the credential |
| `PUT` | `/api/pi/providers/{id}/credential` | `{api_key}` → writes Pi's `auth.json` (mode `600`) |
| `DELETE` | `/api/pi/providers/{id}/credential` | Removes the stored credential |
| `POST` | `/api/pi/providers/{id}/credential/from-orchestrator` | Copies Solo's OpenRouter key, so it is entered once |
| `POST` | `/api/pi/providers/{id}/test?model=&deep=` | `deep=false` checks presence; `deep=true` makes a real request |

```json
{"ok": true, "state": "verified", "message": "opencode-go / claude-haiku-5-5 answered a real request successfully.", "model": "claude-haiku-5-5", "latency_ms": 1840}
```

`state` is `not_configured`, `configured`, `verified` or `failed`. A provider is
never reported `verified` unless a real request succeeded.

### Runtime provenance

```json
{
  "installed": true, "verified": true, "available": true,
  "source": "managed", "isolated": true,
  "executable": "/…/data/pi-runtime/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js",
  "runtime_dir": "/…/data/pi-runtime",
  "agent_dir": "/…/data/pi/agent",
  "node": "/usr/bin/node",
  "version": "1.1.0",
  "detail": "Solo's isolated Pi Agent is installed at /…/data/pi-runtime."
}
```

`source` is `managed` (Solo's own copy), `external` (an explicit `PI_EXECUTABLE`
override) or `none`. `isolated` is true only for `managed`. The executable is
never resolved through `PATH`; a bare command name in `PI_EXECUTABLE` is refused
and reported in `detail`.

### Saving a credential also refreshes the catalog

`PUT /api/pi/providers/{id}/credential` writes Pi's own `auth.json`, then runs
`pi update --models` and reports the model count in `detail`. This is what makes
an isolated agent directory usable without a terminal step. The credential file
is always Solo's; `~/.pi/agent` is never touched.

---

## Project files (Writing panel and uploads)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/projects/{id}/files?path=` | Read a text file |
| `PUT` | `/api/projects/{id}/files` | `{path, content, overwrite}` — create or replace |
| `POST` | `/api/projects/{id}/files/upload` | `multipart/form-data`: `file`, optional `directory`, `overwrite` |
| `GET` | `/api/projects/{id}/files/limits` | Advisory size limits for the UI |

```json
{"path": "docs/notes.md", "content": "# Notes", "size": 7, "truncated": false, "binary": false}
```

`binary` is true when the file is not valid UTF-8 text; `content` is then empty.
`truncated` is true when the file is larger than the read limit.

| Status | Cause |
|---|---|
| `400` | traversal or an absolute path; the project metadata directory or `.git`; a hidden upload name; over the size limit |
| `413` | upload larger than the configured limit |
| `409` | the project directory is not accessible |

Paths are resolved inside the project root, symlinks are followed and re-checked,
nothing is executed, and `content` is written atomically so an interrupted save
cannot truncate a file.

---

## Orchestrator (OpenRouter)

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/orchestrator/status` | Enabled, configured, masked key, call/failure counts, last error and latency |
| `PUT` | `/api/orchestrator/config` | `{model?, enabled?}` |
| `GET` | `/api/orchestrator/models?search=` | OpenRouter's catalog |
| `POST` | `/api/orchestrator/test?model=&deep=` | `deep=true` runs one real completion → `verified` |

---

## Orchestration state and checks

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/projects/{id}/orchestration` | The plan queue, notes and summary |
| `POST` | `/api/projects/{id}/orchestration/plan` | `{instruction}` — decompose into a plan |
| `POST` | `/api/projects/{id}/orchestration/notes` | Record an instruction without executing it |
| `POST` | `/api/projects/{id}/orchestration/queue/{plan_id}/skip` | Mark a step skipped |
| `DELETE` | `/api/projects/{id}/orchestration/queue/{plan_id}` | Remove a queued step |
| `POST` | `/api/projects/{id}/orchestration/advance` | Start the next ready step now |
| `GET` | `/api/checks/status` | Whether Pyright is available |
| `POST` | `/api/projects/{id}/checks` | Run Pyright now; returns diagnostics |

```json
{
  "summary": {"queue_size": 2, "status_counts": {"done": 1, "pending": 1}, "pending_notes": 0, "next": {"title": "Write tests"}},
  "state": {"project_id": "…", "active_task_id": null, "queue": [], "notes": []}
}
```

---

## Account

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/account` | Username, role, creation date, signed-in session count |
| `PUT` | `/api/account/username` | `{new_username, current_password}` — the password is required even when authenticated |
| `PUT` | `/api/account/password` | `{current_password, new_password}` — revokes every **other** session, keeps this one |
| `POST` | `/api/account/sessions/revoke` | Sign out other devices without changing the password |

```json
{"username": "admin", "role": "owner", "created_at": "2026-10-10T12:00:00Z",
 "active_sessions": 2, "has_session": true}
```

The current password is required for both changes: a session proves the browser
signed in at some point, not that the person at the keyboard owns the account, and
this account can run code and edit files. A password is only ever stored as a
salted scrypt hash and is never returned.

---

## Voice

Solo's direction is voice-native: the conversation is the interface and speech is
its primary output. These endpoints expose the **narration pipeline** — what Solo
would say, in what order, and whether it is yielding to the user.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/voice/state` | Transport, whether audio is attached, queue depth, drops, recent lines |
| `GET` | `/api/voice/history?limit=` | What Solo has said and is about to say |
| `POST` | `/api/voice/interrupt` | `{reason}` — barge-in: stop speech, drop lower-priority lines |
| `POST` | `/api/voice/resume` | Resume after the user stops speaking |

```json
{"transport": "recording", "audio_available": false, "listening": false,
 "queued": 0, "dropped": 3, "spoken": 7, "phase": "narration-foundation",
 "recent": [{"text": "The task is complete.", "kind": "outcome", "spoken": true}]}
```

`audio_available` is **false** until an audio transport is attached, and the UI
shows the lines instead of claiming playback. Ordering, coalescing, rate limiting
and barge-in are real and tested. A `narration` WebSocket channel carries each
line as it is queued and again when it is delivered.

---

## Health

### `GET /api/health`

Public. No secrets.

```json
{
  "status": "ok",
  "version": "0.1.0",
  "database": true,
  "workspaces_dir": true,
  "coding_agent": "mock",
  "pi_version": "1.1.0"
}
```

`status` is `"degraded"` when the database or the workspaces directory is
unusable.

---

## Authentication

| Method | Path | Body | Result |
|---|---|---|---|
| `GET` | `/api/auth/status` | – | `{initialized, authenticated, username}` |
| `POST` | `/api/auth/setup` | `{username, password}` (password ≥ 8) | `201`, sets cookie. `409` if already initialized |
| `POST` | `/api/auth/login` | `{username, password}` | `200`, sets cookie. `401` on bad credentials |
| `POST` | `/api/auth/logout` | – | `200`, clears cookie |
| `GET` | `/api/auth/me` | – | `{initialized, authenticated, username}` |

The cookie is `HttpOnly`, `SameSite=Lax`, and `Secure` when `APP_ENV=production`.
Only a SHA-256 digest of the token is stored server-side.

---

## Settings

### `GET /api/settings`

```json
{
  "openrouter_api_key": { "configured": true, "masked": "**********cdef" },
  "elevenlabs_api_key": { "configured": false, "masked": null },
  "openrouter_model": "anthropic/claude-3.5-sonnet",
  "elevenlabs_agent_id": "agent_123",
  "elevenlabs_tts_voice_id": "voice_abc",
  "pi_provider": "openrouter",
  "pi_model": "anthropic/claude-3.5-sonnet",
  "pi_base_url": null,
  "pi_reuse_openrouter_key": false,
  "voice_enabled": true,
  "progress_speech_enabled": true,
  "pi_version": "1.1.0",
  "pi_rpc_available": false
}
```

### `PUT /api/settings`

Partial update — omitted fields are left unchanged.

- A non-empty string for a secret key stores it encrypted.
- An **empty string** clears a secret.
- `null` clears a plain value.

```json
{ "openrouter_api_key": "sk-or-v1-…", "openrouter_model": "…", "voice_enabled": false }
```

### `DELETE /api/settings/secret/{key}`

`key` ∈ `openrouter_api_key`, `elevenlabs_api_key`. Returns the updated
settings. `404` for an unknown key.

### `POST /api/settings/test/{provider}`

`provider` ∈ `openrouter`, `elevenlabs`, `pi`. Performs a real request against
the provider (OpenRouter `GET /api/v1/key`, ElevenLabs `GET /v1/user`, or a
local `pi --version` probe).

```json
{ "ok": true, "message": "OpenRouter key is valid (personal).", "detail": null }
```

Failures return `ok: false` with a human-readable message and a detail string
that never contains the secret.

---

## Projects

A project is a directory on disk plus a `.solo/` state store inside it. See
[projects.md](projects.md) for the full model.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/projects` | Includes a bounded `file_count` per project |
| `POST` | `/api/projects` | `{name, parent?}` — create; omit `parent` for the managed folder |
| `POST` | `/api/projects/open` | `{path, name?}` — adopt an existing directory in place |
| `POST` | `/api/projects/upload` | `multipart/form-data`: `file` (`.zip`), optional `name` |
| `GET` | `/api/projects/{id}` | `404` if unknown |
| `DELETE` | `/api/projects/{id}?remove_files=` | `204`. Defaults: `true` for managed, `false` for opened in place |
| `GET` | `/api/projects/{id}/summary` | Counts, paths and the effective configuration |
| `GET` | `/api/projects/{id}/tree?refresh=` | The structured project state tree |
| `GET` | `/api/projects/{id}/config` | Per-project configuration |
| `PUT` | `/api/projects/{id}/config` | Deep-merged partial update |
| `GET` | `/api/projects/{id}/memory?limit=` | Memory entries, newest first |
| `POST` | `/api/projects/{id}/memory` | `{text, kind?, tags?}` |
| `DELETE` | `/api/projects/{id}/memory/{entry_id}` | `204` / `404` |

```json
{
  "id": "c6495e44…",
  "name": "e2e-demo",
  "slug": "e2e-demo",
  "source": "created",
  "status": "ready",
  "location": "managed",
  "root": "/data/workspaces/e2e-demo",
  "metadata_dir": ".solo",
  "is_managed": true,
  "file_count": 12,
  "created_at": "2026-10-10T12:00:00Z",
  "updated_at": "2026-10-10T12:00:00Z"
}
```

`location` is `managed` (created inside Solo's workspaces folder, `root_path` a
slug) or `external` (an existing directory, `root_path` absolute). `source` is
`created`, `opened` or `imported`.

### Create

```json
{ "name": "my-service" }
{ "name": "my-service", "parent": "/home/you/projects" }
```

A non-empty target folder is refused with `400`. `parent` is validated against
the path policy.

### Open in place

```json
{ "path": "/home/you/code/my-service", "name": "My Service" }
```

Nothing is copied. Solo adds `.solo/` and reads the project where it is.
Idempotent: re-opening the same directory returns the same project. If the
directory already contains `.solo/project.json`, its `id` is adopted (unless
another project already claims it), so history from another installation is
preserved.

| Status | Cause |
|---|---|
| `400` | path missing, not a directory, blocked, outside `PROJECT_ROOTS`, or the folder is not writable |

### State tree

```json
{
  "version": 1,
  "generated_at": "2026-10-10T15:37:37Z",
  "truncated": false,
  "project": { "id": "…", "name": "My Service", "location": "external" },
  "root": {
    "id": "root", "name": "My Service", "kind": "project",
    "children": [
      { "id": "group:files", "name": "Files", "kind": "group", "children": [] },
      { "id": "group:tasks", "name": "Tasks", "kind": "group", "children": [] },
      { "id": "group:memory", "name": "Memory", "kind": "group", "children": [] },
      { "id": "group:sessions", "name": "Sessions", "kind": "group", "children": [] }
    ]
  }
}
```

Node `kind` is one of `project`, `group`, `directory`, `file`, `task`, `memory`,
`session`. Activity nodes carry a `ref` pointing at their detail file under
`.solo/`. `?refresh=true` rebuilds the tree from live state before returning.

### Memory

```json
{
  "id": "ffb3dd3f…", "kind": "decision", "text": "Uses SQLite",
  "tags": ["db"], "source": "user", "task_id": null,
  "created_at": "2026-10-10T15:37:36Z"
}
```

`kind` ∈ `note`, `decision`, `fact`, `todo`.

### Configuration

`PUT` is a **deep merge**, so saving one section cannot erase another.

```json
{
  "tree":     { "max_depth": 6, "max_entries": 2000, "exclude": ["vendor"] },
  "memory":   { "max_entries": 500, "auto_capture": true },
  "sessions": { "max_sessions": 20 },
  "state":    { "auto_refresh": true }
}
```

A `null` value means "use the application default".

### Upload errors

| Status | Cause |
|---|---|
| `400` | not a `.zip`; not a valid archive; traversal/symlink entry; empty archive |
| `413` | exceeds `MAX_UPLOAD_MB` |

A single wrapping directory in the archive is stripped, so `myapp/src/main.py`
extracts to `<workspace>/src/main.py`. Nothing is executed during extraction.

---

## Filesystem browser

### `GET /api/fs/list?path=`

Lists **directories only** for the Open Project dialog. Omit `path` for the
default root (the home directory).

```json
{
  "path": "/home/you/code",
  "parent": "/home/you",
  "roots": ["/home/you", "/data/workspaces"],
  "entries": [
    { "name": "my-service", "path": "/home/you/code/my-service",
      "hidden": false, "is_project": true }
  ],
  "truncated": false
}
```

`is_project` marks a directory that already contains Solo metadata. Blocked and
out-of-allow-list locations return `400` with a human-readable `detail`.

---

## Messages

### `GET /api/projects/{project_id}/messages?limit=200`

Full transcript for the project's conversation, oldest first.

### `POST /api/projects/{project_id}/messages`

```json
{ "content": "how many files are there?" }
```

The orchestrator classifies the message and acts:

```json
{
  "intent": "CHAT_OR_EXPLAIN",
  "message": { "id": "…", "role": "assistant", "content": "…", "task_id": "…" },
  "task_id": "…"
}
```

| `intent` | Effect |
|---|---|
| `CHAT_OR_EXPLAIN` | Creates a completed `QUESTION` task and answers from a bounded snapshot. Does **not** interrupt a running task |
| `STEER_ACTIVE_TASK` | Sends the instruction to the active task |
| `STOP_ACTIVE_TASK` | Requests cancellation; `CANCELLED` follows only on confirmation |
| `START_CODING_TASK` | Starts a coding task (never a second writer for the same project) |
| `NEEDS_CLARIFICATION` | Asks the user to rephrase |

---

## Tasks

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/tasks?project_id=&limit=100` | Newest first |
| `POST` | `/api/tasks` | `{project_id, instruction}` → `201`. `409` if a task is already active for the project |
| `GET` | `/api/tasks/{id}` | Task plus its changed files |
| `GET` | `/api/tasks/{id}/events?limit=200` | Normalized events, oldest first |
| `POST` | `/api/tasks/{id}/cancel` | Sets `CANCEL_REQUESTED`; `CANCELLED` only when the adapter confirms |
| `POST` | `/api/tasks/{id}/steer` | `{instruction}`; `409` if the task is not active |

```json
{
  "id": "16af0384…",
  "project_id": "c6495e44…",
  "conversation_id": "…",
  "parent_task_id": null,
  "task_type": "CODING",
  "status": "COMPLETED",
  "instruction": "add a health endpoint",
  "progress_summary": "Completed.",
  "result_summary": "Completed: add a health endpoint. 1 file changed, tests passed.",
  "error": null,
  "created_at": "2026-10-10T12:00:00Z",
  "updated_at": "2026-10-10T12:00:02Z",
  "completed_at": "2026-10-10T12:00:02Z",
  "files": [{ "path": "src/main.py", "change_type": "modified", "created_at": "…" }]
}
```

### Task statuses

`QUEUED`, `RUNNING`, `WAITING_FOR_INPUT`, `PAUSE_REQUESTED`, `PAUSED`,
`CANCEL_REQUESTED`, `CANCELLED`, `COMPLETED`, `FAILED`, `RECOVERY_REQUIRED`.

Terminal: `COMPLETED`, `CANCELLED`, `FAILED`. On startup, any non-terminal task
becomes `RECOVERY_REQUIRED` — the app never assumes an interrupted task
succeeded.

### Event types

| `file.changed`, `test.result`, `check.result`, `progress.summary`, `state.updated`, `error`, `message.received`, `assistant.message`.

Events carry a `data` payload whose shape depends on `type` — for example
`file.changed` has `{path, change_type, tool}` and `check.result` has the full
Pyright result including `diagnostics`.

```json
{
  "id": 42,
  "task_id": "16af0384…",
  "project_id": "c6495e44…",
  "type": "file.changed",
  "message": "Modified src/main.py",
  "data": { "path": "src/main.py", "change_type": "modified" },
  "created_at": "2026-10-10T12:00:01Z"
}
```

---

## WebSocket

`GET /api/ws` (upgrade). Authenticated by the same session cookie; a `?token=`
query parameter is accepted as a fallback for non-browser clients. A rejected
handshake closes with code **4401** before any data is sent.

Every frame is an envelope:

```json
{ "channel": "event", "payload": { … } }
```

| `channel` | `payload` |
|---|---|
| `ready` | `{user, coding_agent}` — sent once on connect |
| `event` | an `EventOut` object |
| `task` | a `TaskOut` object (status/result changed) |
| `message` | a `MessageOut` object (assistant messages) |
| `narration` | a narration line, as it is queued and again when delivered |
| `voice` | barge-in notices: `{event: "interrupt"|"resume", ...}` |
| `orchestration` | the current `summary` of the project's orchestration state |

The bus drops the oldest frame for a slow subscriber rather than blocking the
publisher; clients can always re-fetch over REST, because events are persisted
before they are broadcast.

---

## Error format

FastAPI's standard shape:

```json
{ "detail": "human-readable message" }
```

Validation failures return `422` with `detail` as a list of
`{loc, msg, type}` entries. The frontend client normalizes both into a single
message string.
