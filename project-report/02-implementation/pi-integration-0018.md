# 18 — Pi Agent Integration and Pyright

**Stage:** Implementation
**Date:** 2026-10-10

---

## 1. New backend modules

| Module | Lines | Responsibility |
|---|---|---|
| `adapters/pi_rpc.py` | ~300 | Transport: launch, LF-only JSONL framing, request/response correlation, event delivery, deadlines, orderly shutdown |
| `adapters/pi_events.py` | ~330 | Translate Pi records into Solo's normalised event vocabulary |
| `adapters/pi_session.py` | ~250 | One long-lived process per project; run reservation; steering; cancellation; crash detection |
| `adapters/pi_agent.py` | ~200 | The `CodingAgentAdapter` implementation (rewritten from the Phase 1 stub) |
| `services/pi_config.py` | ~430 | Providers, credentials, readiness, model discovery, catalog refresh, validation |
| `api/pi.py` | ~200 | Settings-UI endpoints |

### Changed

| Module | Change |
|---|---|
| `adapters/__init__.py` | `build_adapter` now resolves `auto` (Pi when installed, else the simulator) and injects the launch-config loader |
| `config.py` | `agent_backend` defaults to `auto`; `pi_executable`, `pi_agent_dir`, `pi_approve_project`, `pi_minimal_harness`, `pi_run_timeout_seconds` |
| `domain.py` | New event types (`check.result`, `state.updated`), `PlannedTaskStatus`, `CheckOutcome` |
| `container.py` | Wires `PiConfigService`, `ChecksService`, `OrchestratorBrain`; passes the settings-driven launch config to the adapter |
| `services/settings_service.py` | `pi_launch_config()` turns saved settings into a `PiLaunchConfig` |

---

## 2. Transport (`pi_rpc.py`)

Four decisions worth recording, each traceable to a protocol requirement:

| Requirement (from Pi's docs) | Implementation |
|---|---|
| "Split records only on LF"; `readline` also splits on `U+2028`/`U+2029` which are valid inside JSON strings | `StreamReader.readline()` — byte-oriented, LF only. A test asserts a message containing both separators survives intact |
| "Command handling is asynchronous; correlate by ID rather than order" | A pending-future map keyed by request id, resolved in the stdout dispatcher |
| "Read stdout continuously… a client that stops reading can stall the process" | A dedicated reader task; a separate task drains stderr |
| "Do not parse stderr as protocol data" | stderr is kept only as a bounded tail for error messages |

Additional robustness the docs imply but do not specify:

- **Oversized records** are skipped with a warning rather than killing the stream
  (the StreamReader limit is raised to 32 MiB for large tool results).
- **Process death** resolves all pending futures *and* an `asyncio.Event`, so a
  crashed Pi fails a task immediately instead of occupying the 30-minute run
  timeout.
- **A successful response is unwrapped to its `data` payload**, with an
  `accept_failure` opt-in that returns the raw record — this distinction was the
  subject of defect D-13.

## 3. Event translation (`pi_events.py`)

`PiEventTranslator` is stateful per run and returns a list of `AgentEvent`s per
record, plus an accumulated `TranslationState` used to build the `AgentResult`.

Two deliberate omissions:

- **Thinking blocks are discarded** and a test asserts the text never appears in
  any emitted event. Solo shows observable tool activity and user-facing
  summaries, never private chain-of-thought.
- **Streaming text is coalesced**: `text_delta` fragments are buffered and
  emitted once at `text_end`, so one assistant response does not become hundreds
  of stored rows.

Details that make the UI useful rather than noisy:

- File paths are made **project-relative** when inside the project root, and left
  absolute when outside it.
- `write` vs `edit` is reported as `written` vs `modified`.
- Commands matching a test runner pattern produce `test.result`, and the pass/fail
  summary line is extracted from the output (`3 passed, 1 failed in 0.4s`).
- Retries, compaction and queue changes become `progress.summary`, not raw logs.

## 4. Session and process lifecycle (`pi_session.py`)

- **Keyed by resolved project directory** — unique per project, so follow-ups and
  steering reach the right conversation.
- **Restarted automatically** when the launch configuration changes (a different
  provider, model or thinking level), so a Settings change takes effect on the
  next task without manual intervention.
- **Reserved by an `asyncio.Lock`**: one run per project at a time, matching the
  single-writer rule from Phase 1.
- **Cancellation** sends `abort` and waits for `agent_settled`; `CANCELLED` is
  only reported when Pi confirms it.
- **Trailing-record flush** (a short grace period) ensures the final
  `assistant.message` is not lost when `agent_settled` arrives immediately after.
- **A dead process never looks like a hang**, and never looks like success: the
  death message is recorded as the task error.

## 5. Configuration service (`pi_config.py`)

Reuses Pi's interfaces rather than re-implementing them:

| Need | Mechanism |
|---|---|
| Provider list | `get_available_models` (RPC), merged with a curated list of providers Pi supports |
| Readiness | `pi auth check --provider X --no-refresh --json` |
| Credential storage | Pi's `auth.json`, written atomically at mode `600` |
| Credential **reading** | Only key names — never values; the API returns `{configured: true}` |
| Model catalog | `get_available_models`, cached briefly, filterable |
| Catalog refresh | `pi update --models` |
| Verification | One minimal real completion, so "verified" means verified |

### The curated provider list

Pi's own registry was inspected (the installed build, not guessed) to derive
provider ids and API-key environment variables. This matters because a
credential can be stored for a provider whose model list is not discoverable —
the request explicitly asked for a manual fallback rather than assuming every
provider exposes the same capabilities. A test asserts every id in the list is
recognised by Pi (`provider_not_found` would fail it).

### Three-state honesty

```
not_configured   Pi reports no credential
configured       a credential is stored and Pi reports it ready
verified         a real request succeeded with the selected model
```

`deep=false` can never produce `verified`. The UI renders the distinction, and
two tests assert that a presence check does not set the verified badge.

## 6. Pyright (`services/checks.py`)

Solo uses Pi to *make* changes and Pyright to *verify* them.

| Property | Implementation |
|---|---|
| Structured output | `pyright --outputjson`, parsed into typed diagnostics |
| Focused | Checks the files the agent changed when they are Python; otherwise a bounded project scan |
| Bounded | File cap (300), diagnostic cap (100), wall-clock cap (configurable, default 180 s), vendor/hidden directories skipped |
| Non-blocking | Runs after the task settles; never blocks a task or a notification |
| Honest | `passed` / `failed` / `error` / `skipped` — "skipped" with a reason when Pyright is missing, disabled, or the project has no Python |
| Non-fatal | A missing tool, a timeout or unparseable output produces a result object, never an exception |

Diagnostics carry file, line, column, severity, message and rule, and render in
the Activity panel.

---

## 7. Installation

| Item | Change |
|---|---|
| `solo.sh` | `ensure_pi()` installs Pi **locally** into `.tools/pi` via `npm install --prefix`, so no sudo and no global npm mutation; an existing `pi` on PATH always wins and `PI_EXECUTABLE` is written to `.env` |
| `solo.sh` | `ensure_pyright()` reports availability; `doctor` now reports both Pi and Pyright |
| `backend/requirements.txt` | Adds `pyright==1.1.414` |
| `Dockerfile` | Adds Node 20 + the Pi CLI behind a build arg, and points `PI_CODING_AGENT_DIR` at the persistent volume. **Not verified — no Docker daemon available (D-08).** |
| `.env.example` | Documents `AGENT_BACKEND=auto`, `PI_EXECUTABLE`, `PI_APPROVE_PROJECT`, `PI_AGENT_DIR`, `PI_RUN_TIMEOUT_SECONDS`, `ORCHESTRATOR_ENABLED`, `CHECKS_ENABLED` |

Design note: `AGENT_BACKEND` now defaults to **`auto`** — Pi when the executable
is present, otherwise the simulator — so a fresh install works whether or not Pi
could be installed, and the user is never left with a broken app or a silently
simulated one. The Settings UI always shows which backend is active.
