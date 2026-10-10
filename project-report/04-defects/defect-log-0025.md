# 25 — Defect Log (Runtime Isolation and Updates)

**Stage:** Defects
**Date:** 2026-10-10

Seven defects. Two were in the product, five were in the *verification* — which
is worth stating plainly, because a wrong test is as costly as a wrong feature:
it either hides a bug or invents one.

---

## D-17 — The runtime "verification" omitted `--mode rpc`

| | |
|---|---|
| **Severity** | High (the installer reported a working runtime as broken) |
| **Status** | Fixed |
| **Found by** | `./solo.sh install`, first real run |
| **File** | `backend/app/services/pi_runtime.py` |

### Symptom
```
install     : ok — Pi Agent 1.1.0 installed into Solo's runtime.
verified    : no
status      : Pi did not start: Pi did not answer 'get_state' within 90s
```
The package was installed correctly; the runtime simply never answered.

### Root cause
`rpc_probe()` spawned `[node, cli.js]` **without the harness flags**:

```python
probe_argv = [*argv]                       # ← missing --mode rpc
```

Without `--mode rpc`, Pi starts its interactive terminal interface, which waits
for a user at a TTY and never reads a JSONL command from stdin. The process is
healthy and silent, so the probe waited out its full timeout.

### Fix
```python
HARNESS_FLAGS = ("--mode", "rpc", "--no-session", "--no-approve",
                 "--no-extensions", "--no-skills", "--no-prompt-templates",
                 "--no-mcp", "--no-context-files")
probe_argv = [*argv, *self.HARNESS_FLAGS]
```

The flags are now a named constant on the runtime, so the probe and the task
session cannot drift apart.

### Lesson
The long-lived session path passed these flags; only the new one-shot probe did
not. A capability added for verification must be verified itself — and the
installer's own success message ("installed") was correct, which is exactly why
`installed` and `verified` are separate states.

---

## D-18 — `/api/health` still called the old probe signature

| | |
|---|---|
| **Severity** | Medium (health reported no Pi version while Pi was working) |
| **Status** | Fixed |
| **Found by** | `scripts/e2e-live.sh` — `Pi version: None` |
| **File** | `backend/app/api/health.py` |

### Symptom
The live test reported `backend is pi` but `Pi version: None`.

### Root cause
`probe_pi_runtime()` gained a required `settings` argument when it was rerouted
through the runtime, and `health.py` was not updated. The call happened to be
inside a `try/except Exception`, so the `TypeError` was swallowed and the version
silently became `None`.

### Fix
Pass settings, and expose the new facts the health payload should carry:
`pi_isolated` and `schema_version`.

### Lesson
A broad `except Exception` around a probe is right — health must never fail — but
it also hides signature drift. The end-to-end test caught it precisely because it
asserted on a *value* rather than on the absence of an error.

---

## D-19 — Circular import between the runtime service and the adapters

| | |
|---|---|
| **Severity** | Medium (the module could not be imported on its own) |
| **Status** | Fixed |
| **Found by** | Importing `app.services.pi_runtime` directly |
| **File** | `backend/app/services/pi_runtime.py` |

### Symptom
```
ImportError: cannot import name 'PiRuntime' from partially initialized module
'app.services.pi_runtime' (most likely due to a circular import)
```

### Root cause
`services/pi_runtime.py` imported `PiRpcClient` at module level, while
`adapters/__init__.py` imports `pi_agent`, which imports `services/pi_runtime`.
The application worked because the container happened to import the adapters
first — so the cycle only appeared when the module was imported directly, which
is exactly what the installer CLI does.

### Fix
Import `PiRpcClient` lazily inside `rpc_probe()`. It is used in one method and is
not on a hot path.

### Lesson
"it works in the app" is not evidence that a module is importable. The CLI entry
point is what exposed it.

---

## D-20 — `RuntimeStatus.to_dict()` omitted a field the API required

| | |
|---|---|
| **Severity** | Medium (500 on `/api/pi/status`) |
| **Status** | Fixed |
| **Found by** | `tests/test_checks_and_api_pi.py` |
| **File** | `backend/app/services/pi_runtime.py` |

### Symptom
```
pydantic_core.ValidationError: 1 validation error for PiRuntimeOut
available — Field required
```

### Root cause
`RuntimeStatus.to_dict()` returned `installed` but not `available`, which
`PiRuntimeOut` requires (it predates the rename and is used by the health
endpoint).

### Fix
`to_dict()` includes both, documented as an alias kept for the health endpoint
and older clients.

### Lesson
Two names for one concept is a smell. It is kept deliberately here — `installed`
is the precise term for Solo's own runtime, `available` is what the health
contract already published — but the duplication is now explicit and tested
rather than accidental.

---

## D-21 — The updater recorded the new version as its own predecessor

| | |
|---|---|
| **Severity** | Medium (misleading update report) |
| **Status** | Fixed |
| **Found by** | A real update against a temporary upstream |
| **File** | `solo.sh` |

### Symptom
```
version: 2.5.0 | previous_version: 2.5.0
```

### Root cause
`update_impl` called `write_install_manifest` **twice**:

```bash
write_install_manifest
SOLO_UPDATED_BY="solo.sh update" write_install_manifest
```

`write_install_manifest` derives `previous_version` from the manifest it finds.
The first call wrote the new version, so the second read it back as the previous
one.

### Fix
One write per operation, with the version being replaced passed as an argument:

```bash
SOLO_UPDATED_BY="solo.sh update" write_install_manifest "$previous_version"
```

Passing it as an argument rather than through the environment is deliberate: a
`VAR=value function` assignment does not reliably reach a subprocess started
inside that function, and relying on it produced a second, silent failure while
diagnosing this one.

### Lesson
An idempotent-looking helper called twice is not idempotent when it reads the
state it writes. Verified afterwards: `previous_version` reads `2.2.0` for a
`2.2.0 → 2.5.0` update.

---

## D-22 — The frontend fingerprint depended on the shell's locale

| | |
|---|---|
| **Severity** | Low (needless rebuilds, not incorrect output) |
| **Status** | Fixed |
| **Found by** | Comparing the shell fingerprint to an independent computation |
| **File** | `solo.sh` |

### Symptom
An update whose only change was `VERSION` still reported
*"Changes detected: web UI"* and rebuilt the frontend.

### Root cause
`frontend_fingerprint()` hashed `find … | sort -z | xargs -0 cat`. `sort`
collates according to `LC_ALL`/`LC_COLLATE`, so the byte order of the
concatenated sources — and therefore the hash — was a function of the
environment, not only of the sources.

### Fix
`LC_ALL=C sort -z`, making the fingerprint a pure function of the file contents.

### Lesson
A fingerprint used to decide "has this changed?" must depend on *only* the thing
it is measuring. Verified: two consecutive updates against a moved upstream now
report *"No dependency or build changes detected"* with **zero** rebuild steps.

---

## D-23 — Two defects in the verification itself

| | |
|---|---|
| **Severity** | Low (test defects, but they produced two false alarms) |
| **Status** | Fixed |
| **Found by** | Running the live test and the update test |
| **Files** | `scripts/e2e-live.sh`, the ad-hoc update test |

### Symptom 1 — a product-looking failure that was not one
```
▸ Pre-flight: Pi and a usable credential
  Pi is not installed; skipping the live test.
```
Solo was working correctly. The script's own pre-flight did
`command -v "${PI_EXECUTABLE:-pi}"` — a **`PATH` check**, in the very test meant
to prove that `PATH` is irrelevant.

### Symptom 2 — a polluted `origin/main`, and patches silently lost
After an update test, `git status` reported `[behind 1]`. The test had pointed
`origin` at a temporary bare repository; `git fetch` updated the **local
`refs/remotes/origin/main`** to the test commit, and restoring the URL did not
undo that. Separately, `git reset --hard` during a test silently discarded
uncommitted `solo.sh` patches, which cost a full debugging cycle.

### Fixes
- The live test asks **the API** whether Solo's runtime is installed, and only
  notes (never requires) a global `pi`. It also installs Solo's runtime into its
  own throwaway data directory, which verifies the installer as well.
- The update test now restores the URLs **and** re-fetches to repair the tracking
  ref.
- Patches are committed before running anything that can reset the tree.

### Lesson
**Verify the harness before believing its output.** Both false alarms pointed at
the product, and both were the test's fault — one by encoding the very
assumption under test, the other by mutating shared state. The first fix is now
part of the shipped script.

---

## Summary

| Id | Severity | Class | Fixed |
|---|---|---|---|
| D-17 | High | Missing flags in a new code path | ✅ |
| D-18 | Medium | Signature drift hidden by a broad except | ✅ |
| D-19 | Medium | Circular import | ✅ |
| D-20 | Medium | Response-contract mismatch | ✅ |
| D-21 | Medium | Bookkeeping helper called twice | ✅ |
| D-22 | Low | Environment-dependent fingerprint | ✅ |
| D-23 | Low | Two test-harness defects | ✅ |

**Twenty-three defects across four phases; twenty-two fixed with regression
coverage; one environment gap (D-08 — the Docker daemon) documented with its
confirming command.**

The pattern holds and sharpened this phase: **every defect was found by running
something that had only been reasoned about**, and this time three of the seven
were in the running itself. D-17 in particular is the sharpest illustration —
the verification step added to prove the runtime works was the one thing that
did not work, and it reported the runtime as broken while the installer's
"installed" message was perfectly accurate.
