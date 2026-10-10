# 03 — Backend Implementation

**Stage:** Implementation
**Date:** 2026-10-10
**Location:** `backend/`

---

## 1. Statistics

| Metric | Value |
|---|---|
| Python modules | 33 |
| Lines of application code | 1 965 |
| Lines of test code | ~1 500 (11 test files) |
| Tests | 123 passing, 0 failing |
| Coverage | 89 % |
| Runtime dependencies | 9 (all pinned) |

---

## 2. Layering

Strict, one-directional:

```
api/  ──►  services/  ──►  repositories/  ──►  models/ + db.py
             │
             └──►  adapters/  (provider protocol isolated here)
```

- **`api/`** validates input, resolves the current user, maps domain errors to
  status codes. No business logic, no SQL.
- **`services/`** holds all business rules.
- **`repositories/`** is the only code that touches a SQLAlchemy session.
- **`adapters/`** is the only code that may know a provider's protocol.

`container.py` is the single place where concrete implementations are chosen,
which is what makes the test suite able to build an app against a temporary data
directory without touching global state.

---

## 3. Domain vocabulary (`domain.py`)

Frozen first, because everything else switches on it.

- **`TaskStatus`** — 10 values, plus `TERMINAL_STATUSES` and `ACTIVE_STATUSES`
  frozen sets. The active set backs the single-writer rule.
- **`TaskType`** — `CODING`, `QUESTION`, `CONTEXT_LOOKUP`.
- **`Intent`** — the five routing outcomes.
- **`EventType`** — 13 normalized event types. No provider string ever reaches
  the database.
- **Settings keys** — split into `SECRET_SETTING_KEYS` (encrypted) and
  `PLAIN_SETTING_KEYS`, so the settings service cannot accidentally store a
  secret in plaintext or encrypt a model name.

---

## 4. Security primitives (`security.py`)

| Function | Implementation | Property |
|---|---|---|
| `hash_password` | scrypt, n=2¹⁴, r=8, p=1, 16-byte salt | Memory-hard; self-describing `scrypt$n$r$p$salt$hash` format |
| `verify_password` | Recompute + `hmac.compare_digest` | Constant-time; malformed hashes return `False` rather than raising |
| `new_session_token` | `secrets.token_urlsafe(32)` | 256 bits of entropy |
| `hash_token` | SHA-256 hex | Only the digest is persisted |
| `SecretCipher` | Fernet; key created with `O_CREAT|O_EXCL` at `0600` | Possession of the DB alone is insufficient |
| `mask_secret` | Reveals the last 4 characters only | Enough to identify a key, not to use it |

`SecretDecryptionError` is raised (and caught by `try_decrypt`) when the key and
ciphertext do not match — the expected outcome of a partial restore.

---

## 5. Log redaction (`logging_setup.py`)

Two layers, deliberately conservative:

1. **Registered values** — every secret read from the settings store is passed
   to `register_secret`, and exact matches are replaced with `***`.
2. **Patterns** — `sk-…`, `sk_…`, JWTs, and
   `authorization|api_key|token|secret|password = …` lines.

A `RedactionFilter` rewrites the record's message before any handler formats it,
so a redaction cannot be bypassed by a later formatter. `verify_password` never
logs its input, and the connection-test detail strings were written to avoid
including the credential.

---

## 6. Persistence

### Schema (9 tables)

`users`, `auth_sessions`, `app_settings`, `projects`, `conversations`,
`messages`, `tasks`, `task_files`, `task_events`, `raw_logs`.

Design notes:

- `ON DELETE CASCADE` is enforced via `PRAGMA foreign_keys=ON` set on every
  connection; WAL mode is enabled for concurrent read/write.
- The `Message` JSON column is named `meta`, not `metadata`, because
  `metadata` is reserved by SQLAlchemy's declarative API.
- `raw_logs` retains verbose diagnostics under a per-row character cap so that
  debugging detail exists without being fed to a model wholesale.

### Repositories

`UserRepository`, `AuthSessionRepository`, `SettingsRepository`,
`ProjectRepository`, `ConversationRepository`, `TaskRepository`,
`EventRepository`.

Two methods carry real business weight:

- `TaskRepository.find_active(project_id)` — the single-writer guard.
- `TaskRepository.mark_in_flight_for_recovery()` — called once at startup;
  converts any non-terminal task to `RECOVERY_REQUIRED`. The application never
  assumes an interrupted task succeeded.

---

## 7. Upload safety (`services/archive.py`)

`safe_extract_zip` defends against four classes of attack, each with a dedicated
test:

| Threat | Defence |
|---|---|
| Zip Slip / `..` traversal | Every member name is validated **before** any root stripping via `_safe_member_path`, which resolves under the destination and rejects anything outside it |
| Absolute paths (`/etc/passwd`) | Rejected explicitly (previously they were silently stripped — see D-03) |
| Symlink entries | Rejected by checking the Unix mode bits (`S_ISLNK`) in `external_attr` |
| Decompression bombs | Entry-count and total-uncompressed-size limits, both configurable |
| Windows-style paths | Backslashes normalised; drive-letter prefixes (`C:/…`) rejected |

A single wrapping directory is stripped for usability (`myapp/src/main.py` →
`src/main.py`) — but only after validation, which is exactly the ordering bug
recorded as **D-01**.

No archive content is executed at any point.

---

## 8. Orchestration (`services/orchestrator.py`)

The largest and most consequential module (~540 lines). Responsibilities:

1. **Task creation** — rejects a second modifying task for a project with
   `TaskConflictError` (surfaced as HTTP 409).
2. **Execution** — runs the adapter, forwarding events through
   `_on_agent_event`, which persists side effects (changed files, progress) and
   then broadcasts.
3. **Status transitions** — `_set_status` publishes a `task` frame *and* writes
   a `task.status_changed` event. It **refuses to leave a terminal state**,
   which closes the completion-vs-shutdown race (D-02).
4. **Message routing** — `handle_user_message` classifies and dispatches to
   chat / steer / cancel / new task / clarification.
5. **Shutdown** — cancels only runners that are not already `done()`.

Every mutation is written to SQLite **before** the WebSocket broadcast, so a
dropped socket can never lose state; the client can always re-read over REST.

---

## 9. Intent routing (`services/intent.py`)

Deterministic and fully unit-tested. Precedence, highest first:

1. Explicit stop/cancel command (regex anchored at the start).
2. Steering marker (`also`, `instead`, `wait`, …) — only while a task runs.
3. Informational question (`what`, `why`, `how`, `explain`, `status`, …).
   **Never** starts or steers a task, even when it contains a coding verb.
4. A request containing a coding verb.
5. Plain chat.

Rule 3's position was learned from a real defect (**D-04**): *"what files
changed so far?"* contains "changed", which contains the coding verb "change",
and was therefore routed as a steering instruction mid-task. Deterministic rules
take precedence because they cannot hallucinate; Phase 3 adds an LLM classifier
behind the same `classify` contract, validated by Pydantic, used only where the
deterministic rules are genuinely ambiguous.

---

## 10. Adapters

`adapters/base.py` defines the contract and three small dataclasses
(`AgentEvent`, `AgentResult`, `EventCallback`).

**`MockCodingAgentAdapter`** emits a fixed, believable sequence — project
inspection, a read, a progress summary, a file change, a test run, completion —
sampling real filenames from the project directory so the UI looks plausible.
It performs **no** file modification. Its step delay is configurable
(`MOCK_STEP_DELAY`) so the test suite runs with zero delay while concurrency
tests use a realistic pause.

**`PiCodingAgentAdapter`** is a deliberate stub. Every method raises
`RuntimeError("Pi RPC integration is scheduled for Phase 2 …")` rather than
pretending to work, and `build_adapter` raises on an unknown backend instead of
silently degrading to the simulator. A `probe_pi_runtime()` helper (used by the
health endpoint and the Settings screen) detects the `pi` binary and reads its
version — it never raises, reporting `available: false` instead.

---

## 11. API surface

| Router | Endpoints |
|---|---|
| `health` | `GET /api/health` (public, secret-free) |
| `auth` | `status`, `setup`, `login`, `logout`, `me` |
| `settings` | `GET`, `PUT`, `DELETE /secret/{key}`, `POST /test/{provider}` |
| `projects` | `GET`, `POST`, `POST /upload`, `GET/{id}`, `DELETE/{id}` |
| `tasks` | `GET`, `POST`, `GET/{id}`, `GET/{id}/events`, `POST/{id}/cancel`, `POST/{id}/steer` |
| `messages` | `GET`, `POST` under `/api/projects/{id}/messages` |
| `ws` | `GET /api/ws` (upgrade) |

**Middleware** (`main.py`): a same-origin check on state-changing methods
(defence-in-depth beside `SameSite=Lax`), plus `X-Content-Type-Options`,
`X-Frame-Options` and `Referrer-Policy` headers. The built SPA is mounted at `/`
*after* all API routes, so it can never shadow the API.

---

## 12. Notable implementation detail

`TaskDetailOut.model_validate(task)` raised `MissingGreenlet`, because
`model_validate` attempted to lazy-load the `files` relationship outside
async SQLAlchemy's greenlet context. The fix builds the response from
`TaskOut.model_validate(task).model_dump()` and assigns `files` from an
explicitly awaited query. Pattern: **never let a response model trigger a lazy
load.** Recorded as **D-05**.
