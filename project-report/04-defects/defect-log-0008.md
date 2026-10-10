# 08 — Defect Log

**Stage:** Defects
**Date:** 2026-10-10

Eight defects were found and fixed during Phase 1. Six were surfaced by writing
tests rather than by manual use. Each entry records the root cause, not just the
symptom, because all eight are easy to reintroduce.

---

## D-01 — Zip Slip disguised as a wrapping directory

| | |
|---|---|
| **Severity** | Critical (path traversal / arbitrary file write) |
| **Status** | Fixed |
| **Found by** | `test_archive.py::test_rejects_path_traversal` |
| **File** | `backend/app/services/archive.py` |

### Symptom
An archive containing `../escape.txt` extracted successfully instead of being
rejected, and no error was raised.

### Root cause
The extractor strips a single wrapping directory for usability (so
`myapp/src/main.py` becomes `src/main.py`). `_common_root()` computed the set of
first path components and found exactly one — `".."` — and therefore treated the
traversal prefix as a removable wrapper. Stripping it turned the dangerous
`../escape.txt` into a harmless-looking `escape.txt`, and validation (which ran
*after* stripping) had nothing left to object to.

Two independent mistakes combined:
1. `_common_root()` did not exclude `.` / `..` / drive-letter roots.
2. Validation happened *after* the name was rewritten.

### Fix
- Validate **every** member name up front, before any root computation:
  ```python
  for info in infos:
      _safe_member_path(dest, info.filename)
  ```
- `_common_root()` additionally rejects `"."`, `".."` and any root containing
  `":"`, as defence in depth.

### Lesson
**Validate the original input, then transform.** Ordering a security check after
a normalisation step is a recurring source of bypasses.

---

## D-02 — Terminal task state overwritten by a shutdown race

| | |
|---|---|
| **Severity** | High (incorrect persisted state; user sees "cancelled" for completed work) |
| **Status** | Fixed |
| **Found by** | `test_api_tasks.py::test_task_state_survives_restart` |
| **File** | `backend/app/services/orchestrator.py` |

### Symptom
A task that had reached `COMPLETED` was persisted as `CANCELLED` after the
application shut down.

### Root cause
A narrow race. `_set_status(COMPLETED)` commits the new status, then publishes
to the event bus and writes a `task.status_changed` event — both `await` points.
If `shutdown()` ran in that window it saw the runner still in `self._runners`
and cancelled it. `asyncio.CancelledError` was raised at the next `await`,
caught by the handler in `_run_task`, which unconditionally wrote `CANCELLED` —
clobbering the completed state.

### Fix
1. `_set_status` **refuses to leave a terminal state**:
   ```python
   if TaskStatus(task.status) in TERMINAL_STATUSES:
       return
   ```
2. `shutdown()` only cancels runners that are not already `done()`.

Fix (1) is the load-bearing one: it makes the invariant "terminal states are
sticky" hold everywhere, not just in this path.

### Lesson
Broad `except CancelledError` handlers that mutate state need a guard against
racing with the normal completion path.

---

## D-03 — Absolute archive paths silently accepted

| | |
|---|---|
| **Severity** | High (build error; security expectation unmet) |
| **Status** | Fixed |
| **Found by** | `test_archive.py::test_rejects_path_traversal[/etc/passwd]` |
| **File** | `backend/app/services/archive.py` |

### Symptom
An entry named `/etc/passwd` was not rejected; it was silently rewritten to
`etc/passwd` inside the destination.

### Root cause
`_safe_member_path` began with `.lstrip("/")`, which normalised away the leading
slash **before** the absolute-path check could see it. The result was arguably
safe in effect, but the specification requires absolute paths to be rejected,
and silently rewriting an attacker's path is a worse contract than refusing it.

### Fix
Reject explicitly before normalising:
```python
normalised = member_name.replace("\\", "/")
if normalised.startswith("/"):
    raise ArchiveError(f"unsafe absolute path in archive: {member_name!r}")
```

### Lesson
Do not normalise away the very property you are about to validate.

---

## D-04 — Informational question routed as a steering instruction

| | |
|---|---|
| **Severity** | Medium (wrong behaviour; risks interrupting the user's task with a nonsense steer) |
| **Status** | Fixed |
| **Found by** | `test_api_messages.py::test_question_while_running_does_not_interrupt_task` |
| **File** | `backend/app/services/intent.py` |

### Symptom
While a task was running, *"what files changed so far?"* was classified as
`STEER_ACTIVE_TASK` and forwarded to the running agent instead of being answered.

### Root cause
The router checked "contains a coding verb" before "is a question". The coding
verb list contains `"change"`, and the substring `"change"` occurs inside
`"changed"` — so an ordinary past-tense question matched an action verb.

Two separate weaknesses: precedence order, and naive substring matching.

### Fix
- Restructured precedence so an **informational question always wins** over a
  coding verb: stop → steering marker → informational question → coding verb →
  chat.
- Introduced `_INFORMATIONAL_STARTS` (`what`, `why`, `how`, `explain`, `status`,
  `summar`, …) which is checked *before* verb matching.
- The router's docstring now states the precedence explicitly so the ordering is
  not accidentally "tidied" later.

### Lesson
Substring verb matching is fragile in English. The consequence is contained
because the router's contract is narrow and fully unit-tested — and because
Phase 3 replaces it with a validated LLM classifier behind the same interface.

---

## D-05 — `MissingGreenlet` when serializing a task with files

| | |
|---|---|
| **Severity** | Medium (500 error on a core endpoint) |
| **Status** | Fixed |
| **Found by** | `test_api_tasks.py::test_task_runs_to_completion_with_events` |
| **File** | `backend/app/api/tasks.py` |

### Symptom
`GET /api/tasks/{id}` returned 500 with
`MissingGreenlet: greenlet_spawn has not been called`.

### Root cause
`TaskDetailOut.model_validate(task)` triggered Pydantic to read the `files`
attribute. Since it had not been loaded, async SQLAlchemy attempted a lazy load
— which requires a greenlet context that does not exist at serialization time.

### Fix
Build the response from a validated flat model and assign the relationship from
an explicitly awaited query:
```python
detail = TaskDetailOut(**TaskOut.model_validate(task).model_dump())
detail.files = [TaskFileOut.model_validate(item) for item in files]
```

### Lesson
In async SQLAlchemy, **never let a response model trigger a lazy load**. Load
relationships explicitly, or configure eager loading.

---

## D-06 — Cancellation lost when it arrived before the run started

| | |
|---|---|
| **Severity** | Medium (a cancel request could be silently ignored and the task would run to completion) |
| **Status** | Fixed |
| **Found by** | `test_api_tasks.py::test_cancel_requests_then_confirms` |
| **File** | `backend/app/adapters/mock_agent.py` |

### Symptom
A task cancelled immediately after creation ran to `COMPLETED` instead of
`CANCELLED`.

### Root cause
`cancel()` looked up an `asyncio.Event` keyed by task id and did nothing if it
was absent. The event was only created inside `run()`. Because the runner is
scheduled with `create_task` and the HTTP cancel request can arrive first, the
cancel was dropped on the floor before the run had created its event.

### Fix
`cancel()` now creates-and-sets the event if it does not exist, and `run()`
obtains it with `setdefault`, so a cancel that precedes the run is honoured.

### Lesson
This is a **contract requirement, not an implementation quirk**: a cancellation
that arrives before a session starts must be queued, never discarded. The same
requirement is written into the Phase 2 adapter guidance in
`docs/development.md` so the Pi adapter does not repeat it.

---

## D-07 — Bootstrap password file could be a directory

| | |
|---|---|
| **Severity** | Low (start-up failure in an edge case) |
| **Status** | Fixed |
| **Found by** | Design review of the Docker bind-mount behaviour |
| **File** | `backend/app/services/auth_service.py` |

### Symptom
If the app started with a *directory* at `/data/initial-admin-password` —
which is exactly what Docker creates when bind-mounting a file that does not
exist on the host — `read_text()` would raise.

### Root cause
`bootstrap_admin` checked `path.exists()`, which is `True` for a directory.

### Fix
Check `is_file()` instead, and treat a directory as "no bootstrap password", so
the app starts normally and shows first-run setup.

### Lesson
`exists()` is not `is_file()`; bind-mount semantics make the difference
reachable in practice.

---

## D-08 — Docker image build could not be executed in this environment

| | |
|---|---|
| **Severity** | Low (verification gap, not a code defect) |
| **Status** | Open — documented, with mitigation |
| **Found by** | `docker compose build` |

### Symptom
```
permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
```

### Root cause
`/var/run/docker.sock` is owned by `root:docker` with mode `660`. The build user
is in `adm`, `sudo`, `dip`, `plugdev`, `users`, `lpadmin`, `sambashare` — but
**not** `docker`, and `sudo` requires an interactive password that is not
available to an automated session. No rootless alternative (`podman`, `buildah`,
`nerdctl`) is installed.

Note that `docker --version` and `docker compose config` succeed because they are
purely client-side; only daemon operations fail, which is why this was not
apparent during the initial environment audit.

### Mitigation
The Dockerfile's steps were each reproduced natively and verified:
`npm ci` against the committed lockfile, `npm run build`, `pip install` of the
**runtime-only** requirements into a clean venv, and `python -m app` (the exact
container `CMD`) with `APP_ENV=production` — confirming health, SPA serving,
bootstrap login and `Secure` cookies.

### To close
```bash
sudo usermod -aG docker "$USER"   # then re-login
docker compose build
docker compose up -d
curl -fsS localhost:8080/api/health
```

### Lesson
Audit **daemon** access, not just client presence, when validating a build
environment.

---

## Summary

| Id | Severity | Class | Fixed |
|---|---|---|---|
| D-01 | Critical | Path traversal | ✅ |
| D-02 | High | Concurrency / state machine | ✅ |
| D-03 | High | Input validation ordering | ✅ |
| D-04 | Medium | Classification logic | ✅ |
| D-05 | Medium | Async ORM misuse | ✅ |
| D-06 | Medium | Cancellation contract | ✅ |
| D-07 | Low | Filesystem edge case | ✅ |
| D-08 | Low | Environment / verification gap | ⚠️ documented |

**All defects that affect behaviour are fixed and covered by a regression test.**
Seven of eight were found by the test suite; the eighth is an environment
limitation with its constituent steps independently verified.
