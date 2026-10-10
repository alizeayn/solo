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

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/projects` | Includes a bounded `file_count` per project |
| `POST` | `/api/projects` | `{name}`; slug is derived and de-duplicated |
| `POST` | `/api/projects/upload` | `multipart/form-data`: `file` (`.zip`), optional `name` |
| `GET` | `/api/projects/{id}` | `404` if unknown |
| `DELETE` | `/api/projects/{id}` | `204`; removes the record and its directory |

```json
{
  "id": "c6495e44…",
  "name": "e2e-demo",
  "slug": "e2e-demo",
  "source": "created",
  "status": "ready",
  "file_count": 12,
  "created_at": "2026-10-10T12:00:00Z",
  "updated_at": "2026-10-10T12:00:00Z"
}
```

Upload errors:

| Status | Cause |
|---|---|
| `400` | not a `.zip`; not a valid archive; traversal/symlink entry; empty archive |
| `413` | exceeds `MAX_UPLOAD_MB` |

A single wrapping directory in the archive is stripped, so `myapp/src/main.py`
extracts to `<workspace>/src/main.py`. Nothing is executed during extraction.

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

`task.created`, `task.status_changed`, `run.started`, `run.finished`,
`tool.started`, `tool.updated`, `tool.finished`, `file.changed`, `test.result`,
`progress.summary`, `error`, `message.received`, `assistant.message`.

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
