# 14 — Defect Log (Phase 1.5)

**Stage:** Defects
**Date:** 2026-10-10

Four defects were found while implementing the project model and the native
installer. Three were discovered by **executing** what had only been documented;
one by the end-to-end suite.

---

## D-09 — Installer aborted silently before starting the server

| | |
|---|---|
| **Severity** | Critical (the documented one-command install did nothing) |
| **Status** | Fixed |
| **Found by** | Running `./solo.sh install` on a real machine |
| **Files** | `solo.sh`, `install.sh` |

### Symptom
`./install.sh` printed *"Web UI built into frontend/dist"* and then exited with
status 0. No server was started, no password was printed, and `data/` contained
an empty directory. No error message.

### Root cause
Three bash behaviours combined:

```bash
set -euo pipefail
password="$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 24)"
```

1. `head -c 24` exits as soon as it has 24 bytes.
2. `tr` therefore blocks on a write to a closed pipe and **dies of SIGPIPE**.
3. `set -o pipefail` promotes that failure, and `set -e` aborts the script at the
   assignment — after the `mkdir` that had already run, which is why `data/`
   existed but was empty.

The exit status was masked in the shell by a following `| tail`, so the failure
looked like success.

### Fix
A `generate_password()` helper that never leaves a writer waiting:

```bash
if have python3; then
  python3 -c 'import secrets,string;a=string.ascii_letters+string.digits;print("".join(secrets.choice(a) for _ in range(24)))'
elif have openssl; then
  openssl rand -base64 48 | tr -d '\n/+=' | cut -c1-24
else
  head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n' | cut -c1-24
fi
```

`head -c … /dev/urandom` is safe because there is no writer process to kill, and
`od`/`cut` consume their entire input.

### The same trap elsewhere
`port_in_use()` had `ss … | awk … | grep -qE`: `grep -q` exits on the first
match, `awk` takes SIGPIPE, and `pipefail` then reports failure — turning a
**real** port conflict into a silent false negative. Fixed by capturing first
and grepping a herestring:

```bash
listeners="$(ss -ltn 2>/dev/null | awk '{print $4}' || true)"
grep -qE "[:.]${port}$" <<<"$listeners"
```

### Lesson
`set -o pipefail` is correct for catching real errors, but it makes every
early-exit consumer (`grep -q`, `head -c`) a landmine. Never put a
short-circuiting consumer at the end of a pipeline whose producers can block.
**Then actually run the installer.** This had been documented for a whole phase
without ever being executed.

---

## D-10 — `Secure` cookie broke sign-in over plain HTTP

| | |
|---|---|
| **Severity** | High (login appears to succeed, then every request is unauthenticated) |
| **Status** | Fixed |
| **Found by** | Code review while writing the native installer |
| **Files** | `backend/app/config.py`, `backend/app/api/auth.py` |

### Symptom
Signing in over `http://192.168.1.20:8080` returned `200` and set the session
cookie, but the next request came back `401`. The UI would bounce back to the
login screen with no explanation.

### Root cause
`secure=settings.is_production`, and `docker-compose.yml` sets `APP_ENV=production`.
Browsers **reject `Secure` cookies received over plain HTTP** (except on
`localhost`), so the cookie was never stored. Every deployment following the
documented Docker instructions on a LAN address would have hit this — the
secured-by-default instinct was actively harmful, because it protected nothing
(the traffic was already plaintext) while breaking the application.

### Fix
Auto-detect from the request scheme, with an explicit override:

```python
override = container.settings.session_cookie_secure   # SESSION_COOKIE_SECURE
if override is not None:
    return override
return request.url.scheme == "https"
```

Over HTTPS (including behind a proxy that forwards `X-Forwarded-Proto`) the flag
is set; over plain HTTP it is not. Three tests cover the default, the HTTPS
case, and the forced override.

### Lesson
`Secure` is only meaningful on an encrypted transport; tying it to a deployment
label rather than the actual scheme produced a security-*looking* setting that
actually broke the product. Fail visibly, not silently: a rejected cookie
produces no error the user can act on.

---

## D-11 — The directory browser overwrote what the user had typed

| | |
|---|---|
| **Severity** | Medium (input silently discarded; "Open Project" picked the wrong folder) |
| **Status** | Fixed |
| **Found by** | `ProjectDialog.test.tsx` (create at a chosen folder) |
| **Files** | `frontend/src/components/DirectoryBrowser.tsx`, `ProjectDialog.tsx` |

### Symptom
Typing a parent folder into the Create form and submitting created the project
somewhere else. The test asserting `create('demo', '/srv/code')` received
`create('demo', '/home/tester')`.

### Root cause
`DirectoryBrowser` loaded its initial listing on mount and then called
`onChange(result.path)` unconditionally. That is defensible for a fresh picker,
but the dialog also rendered a separate `parent` text input two-way bound to the
same state. The mount-time report raced the user's typing and overwrote it. Two
sources of truth for one value.

### Fix
Two changes:
1. `load(target, notify)` — the **mount** load passes `notify=false`: the initial
   listing is informational and does not claim a selection. Only explicit
   navigation (click, Up, Home, Go/Enter) reports.
2. Removed the duplicate text inputs from the dialog. The browser's own path
   field is the single source of truth, so the two can no longer disagree.

### Lesson
Two widgets bound to one value will fight. Either give the value one source of
truth, or give each a clearly separated responsibility. Also worth noting: the
test that caught this was written to assert the *user-visible outcome*
("which folder did we create in?"), not the internal call sequence.

---

## D-12 — End-to-end test raced a file rewrite (test defect, not a product defect)

| | |
|---|---|
| **Severity** | Low (flaky test, misleading failure) |
| **Status** | Fixed |
| **Found by** | `pytest --cov` run |
| **Files** | `tests/test_api_project_open.py` |

### Symptom
`test_completed_task_is_recorded_in_the_project_store` failed intermittently
under coverage instrumentation, reporting `'RUNNING' == 'COMPLETED'`.

### Root cause
The test polled for the *existence* of `tasks/<id>.json`. That file is written
twice: once when the task starts running, and again when it settles. The loop
exited on the first write and then asserted on a snapshot taken before the
second.

The **product** ordering was already correct (the terminal record is written
before the status is broadcast); the test was simply observing the wrong signal.

### Fix
Poll the file's **content**, not its existence:

```python
while time.monotonic() < deadline:
    if detail_path.is_file():
        detail = json.loads(detail_path.read_text())
        if detail.get("status") == "COMPLETED":
            break
    time.sleep(0.02)
```

Verified stable across three consecutive full runs with coverage enabled.

### Lesson
Polling for a file that is rewritten in place must poll for content. This is
also why the implementation orders the store write *before* the broadcast: it
removes the same ambiguity for real clients, not just for tests.

---

## Discovery (not a defect): the data directory is not a project root

The end-to-end script initially created a project at `${APP_DATA_DIR}/custom-parent`
and received `400 that location is not allowed`.

This is **correct and intentional**: the Solo data directory holds
`master.key`, and a project root is somewhere the coding agent will eventually
be able to write. The blocked set is not overrideable by configuration, so a
misconfigured `PROJECT_ROOTS` cannot expose the key. The test was moved to a
separate scratch directory.

Worth recording because it is the kind of finding that looks like a bug and is
actually the security model working.

---

## Summary

| Id | Severity | Class | Fixed |
|---|---|---|---|
| D-09 | Critical | Shell scripting (`pipefail` + SIGPIPE) | ✅ |
| D-10 | High | Cookie security vs. transport | ✅ |
| D-11 | Medium | Frontend state duplication | ✅ |
| D-12 | Low | Test observation (flaky) | ✅ |

Combined with Phase 1's eight defects: **twelve defects, eleven fixed with
regression coverage, one environment gap (D-08, the Docker daemon) documented
with its confirming command.**

The pattern repeats: defects 12, 13 and 15 were all found by *executing* or
*asserting on* something that had merely been written down. D-09 in particular
had been documented as a working one-command install for an entire phase without
ever having been run.
