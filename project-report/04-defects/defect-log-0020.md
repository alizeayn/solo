# 20 — Defect Log (Phase 2)

**Stage:** Defects
**Date:** 2026-10-10

Four defects were found during Phase 2. All were surfaced by writing tests
against a protocol-accurate fake *before* wiring the UI — which is why none of
them reached the live end-to-end run.

---

## D-13 — `call()` returned the whole response record instead of its payload

| | |
|---|---|
| **Severity** | High (every Pi task failed with a misleading error) |
| **Status** | Fixed |
| **Found by** | Running the new adapter against real Pi for the first time |
| **File** | `backend/app/adapters/pi_rpc.py` |

### Symptom
```
pi --mode rpc … --provider opencode-go --model claude-haiku-5-5
→ error: "Pi has no model selected. Choose a provider and model in Settings → Pi Agent."
```
The model *was* selected, and the same command worked from a probe script.

### Root cause
`PiRpcClient.call()` documented that it returned "its correlated `data`" but the
implementation returned the entire response record:

```python
return record          # {"type":"response","command":"get_state","success":true,"data":{…}}
```

`PiSession.state()` then did `state.get("model")`, which looked for `model` at the
top level of the envelope rather than inside `data`. It found nothing, so Solo
concluded no model was configured and refused to start the run.

Two mistakes compounded it: the docstring described behaviour the code did not
have, and the fake Pi used in tests had not yet been written, so nothing exercised
the shape of a real response.

### Fix
```python
if not record.get("success", False):
    if accept_failure:
        return record        # callers that need to inspect `error`
    raise PiRpcError(record.get("error") or "…")
return record.get("data") or {}
```

### Lesson
A docstring is not a contract. The first live run against real Pi found this in
seconds; a fake written *from the documentation* would also have caught it — but
only because the fake was written from the protocol spec rather than from the
implementation. **Write the test double from the specification, not from your
code.**

---

## D-14 — The adapter ignored the configured Pi executable

| | |
|---|---|
| **Severity** | High (tests silently ran the real binary; configuration had no effect) |
| **Status** | Fixed |
| **Found by** | `test_pi_integration.py` (4 failures) |
| **Files** | `backend/app/adapters/pi_agent.py`, `services/pi_config.py` |

### Symptom
Tests configured `pi_executable` to point at the fake server, but the failures
named a real model:

```
Pi did not become ready: Pi exited unexpectedly (code=1):
  Error: Model "fake-model" not found. Use --list-models to see available models.
```

### Root cause
`PiCodingAgentAdapter.__init__` built its session manager as
`PiSessionManager(run_timeout=…)`, using the manager's default `executable="pi"`.
The `pi_executable` setting was never passed through. `probe_pi_runtime()` was
hardcoded to `shutil.which("pi")` for the same reason.

This is the dangerous class of defect: the default happened to be correct on this
machine (real Pi *is* on PATH), so the feature would have appeared to work while
the setting did nothing. On a machine where Pi was installed locally by the
installer into `.tools/pi` — which is exactly what `solo.sh` does — the adapter
would have looked for `pi` on PATH, not found it, and reported the backend as
unavailable.

### Fix
```python
self._manager = manager or PiSessionManager(
    executable=settings.pi_executable, run_timeout=run_timeout
)
```
`probe_pi_runtime` gained an `executable` parameter, and both `PiConfigService`
and the adapter now pass it.

### Lesson
**A setting that is never read is worse than a missing setting**, because it
looks configured. Tests that point a component at a fixture are testing the
wiring as well as the behaviour — and that is what caught it.

---

## D-15 — The orchestrator brain crashed without a settings service

| | |
|---|---|
| **Severity** | Medium (test-only exposure; a latent robustness gap) |
| **Status** | Fixed |
| **Found by** | `test_orchestration_layer.py` |
| **File** | `backend/app/services/orchestrator_brain.py` |

### Symptom
`AttributeError: 'NoneType' object has no attribute 'get_secret'` from
`available()`, `configuration()` and `client()`.

### Root cause
Three methods assumed `self._settings_service` was always present. It is
optional by design (`client_factory` exists precisely so the brain can be used
with an injected client — in tests, and later for a different provider), but only
`__init__` acknowledged that.

### Fix
```python
if self._settings_service is None:
    return (self._client_factory is not None, None)
```
with `client()` guarded the same way, so an injected factory implies
availability without a saved key.

### Lesson
If a dependency is optional, every method that touches it must say so. The
constructor accepting `None` is a promise the rest of the class has to keep.

---

## D-16 — Live test harness leaked its server and asserted a wrong path

| | |
|---|---|
| **Severity** | Low (test defect, not a product defect) |
| **Status** | Fixed |
| **Found by** | Running the live acceptance script twice |
| **File** | `scripts/e2e-live.sh` |

### Symptom
Two distinct failures, both looking like product regressions:

1. The second run reported 20 failures, with every API call returning 404 —
   because the *first* run's server was still listening on the fixed port and
   serving a database that had since been deleted.
2. `no orchestration state` — even though the API endpoint returned the state
   correctly.

### Root causes
1. The server was started as `( cd … && python -m app ) &`, so `$!` was the PID of
   the subshell, not of uvicorn. Killing the subshell left uvicorn orphaned. With
   a fixed port, the next run talked to a zombie.
2. The assertion checked `<project>/.solo/orchestration.json`, but the state is
   written to `<project>/.solo/state/orchestration.json` — the `state/`
   directory holds generated state, alongside `tree.json`.

### Fix
- `exec env … python -m app` inside the subshell, so the subshell *becomes*
  uvicorn and `$!` is the right PID; the cleanup now also waits and escalates.
- A random free port per run.
- The correct path, and the harness now ships as `scripts/e2e-live.sh` with repo
  -relative paths and self-skip when Pi or a credential is unavailable.

### Lesson
A test harness that leaves state behind produces failures that look like
regressions and cost real time to diagnose. The first fix here was to **verify
the harness itself** before believing its output — `ss -ltn` showing the zombie
listener was the decisive evidence.

---

## Summary

| Id | Severity | Class | Fixed |
|---|---|---|---|
| D-13 | High | Protocol/envelope handling | ✅ |
| D-14 | High | Configuration not wired through | ✅ |
| D-15 | Medium | Optional dependency not guarded | ✅ |
| D-16 | Low | Test harness | ✅ |

Combined with earlier phases: **sixteen defects, fifteen fixed with regression
coverage, one environment gap (D-08 — the Docker daemon) documented with its
confirming command.**

The pattern is consistent across all three phases: **every defect was found by
running something that had only been reasoned about.** Phase 1's lesson was to
run the tests; Phase 1.5's was to run the installer; Phase 2's was to run the
integration against the real tool *and* to distrust the harness when it reported
a regression.
