# 30 — Defect Log (Review Pass)

**Stage:** Defects
**Date:** 2026-10-10

Four defects. One was a real bug in new code; one was a test that had been
silently covering nothing; two were found by inspection while implementing the
requested changes rather than by a failing test.

---

## D-24 — `interrupt()` counted dropped lines but never recorded them

| | |
|---|---|
| **Severity** | Low (wrong statistics, not wrong behaviour) |
| **Status** | Fixed |
| **Found by** | `test_interrupt_drops_progress_but_keeps_errors` |
| **File** | `backend/app/services/narration.py` |

### Symptom
```python
dropped = await service.interrupt("user")
assert dropped == 1                  # passes
assert service.dropped >= 2          # fails: 1
```

### Root cause
`announce()` incremented `self.dropped` when it refused a line, but `interrupt()`
only computed a **local** `dropped` and never added it to the service total:

```python
async with self._lock:
    dropped = len([...])
    self._queue = [...]          # ← self.dropped never updated
```

So the barge-in path discarded lines without recording that it had. The counter is
what the Voice panel shows as "N dropped as stale", which would have under-reported
exactly the thing it exists to communicate.

### Fix
`self.dropped += dropped` inside the same lock as the queue mutation, so the count
and the queue can never disagree.

### Lesson
A counter is state, and it needs the same care as the thing it counts. The
behaviour was correct; only the reporting was wrong — which is the failure mode
that survives longest, because nothing appears broken.

---

## D-25 — A test asserted on the ambient `PATH`, so it silently covered nothing

| | |
|---|---|
| **Severity** | Medium (verification gap: four pyright tests were silently skipping) |
| **Status** | Fixed |
| **Found by** | A full-suite run reporting `1 failed, 371 passed, 3 skipped` |
| **File** | `backend/tests/test_checks_and_api_pi.py` |

### Symptom
```
AssertionError: assert 'No Python files' in
  'Pyright is not installed, so static checks were skipped.'
```
The test intended to prove *"checks are skipped because the project has no
Python"*. It was actually proving *"checks are skipped because the tool is
missing"*.

### Root cause
```python
PYRIGHT = shutil.which("pyright")
…
settings_factory(pyright_executable=PYRIGHT or "pyright")
```

`pyright` is installed into the **project virtualenv**, which is not on `PATH`
when running `../venv/bin/python -m pytest`. So `shutil.which("pyright")` returned
`None`, three tests guarded by `@requires_pyright` skipped, and this one fell back
to the string `"pyright"` — asserting the wrong branch of the same condition.

It had passed in earlier runs because `PATH` then happened to include a `pyright`.
A test whose branch depends on the environment is not a test.

### Fix
Resolve pyright explicitly instead of relying on `PATH`:

```python
def _find_pyright() -> str | None:
    found = shutil.which("pyright")
    if found:
        return found
    candidate = Path(__file__).resolve().parents[2] / "venv" / "bin" / "pyright"
    return str(candidate) if candidate.is_file() else None
```

and mark the affected test `@requires_pyright` so it can never assert a branch it
did not set up. Result: **4 pyright tests now run** (previously 1 ran and 3
skipped) and they exercise the real tool.

### Lesson
Two lessons in one defect. First, a fixture that depends on the environment is a
hidden skip. Second, and more importantly: **three tests were reporting "skipped"
and nobody had noticed**. A skip count that nobody reads is indistinguishable from
coverage. The fix increased real coverage by finding a green-but-empty test.

---

## D-26 — Two form fields shared the label "Current password"

| | |
|---|---|
| **Severity** | Low (usability, and an ambiguous accessible name) |
| **Status** | Fixed |
| **Found by** | `AccountSettings.test.tsx` |
| **File** | `frontend/src/components/AccountSettings.tsx` |

### Symptom
```
Found multiple elements with the text of: Current password
```

### Root cause
The account pane has two forms. The username form needs the password to confirm
the change; the password form needs the current password to authorise it. Both
fields were labelled *"Current password"*.

The test failure was the symptom; the defect is that **a screen-reader user hears
two identical field names with different purposes**, and a sighted user sees two
fields that look interchangeable.

### Fix
The username form's field is labelled **"Confirm with your password"**, which says
what it is for rather than what it is.

### Lesson
Test queries that fail on ambiguity are usually pointing at a real ambiguity. The
right response is to make the two things genuinely different, not to disambiguate
in the test.

---

## D-27 — Eight colours that would only have worked in the dark theme

| | |
|---|---|
| **Severity** | Low (visual only, but guaranteed to break) |
| **Status** | Fixed |
| **Found by** | Inspection while implementing the theme, by auditing the stylesheet for literals |
| **File** | `frontend/src/styles.css` |

### Symptom
```css
.btn--primary { color: #07101f; }              /* for a dark-on-accent label */
.auth__mark  { color: #06101f; }
.toast       { background: #1d1319; color: #ffc9c9; }
```

### Root cause
Eight literal colours outside the token block. Harmless while there was one theme,
because they happened to match it. Adding a light theme does not change them, so
they would have stayed dark-on-light and light-on-dark in the wrong places.

### Fix
All eight replaced with tokens — `var(--border-strong)`, `var(--danger-soft)`,
`var(--danger)`, and `#ffffff` where a label sits on the accent colour in both
themes. The audit was a one-line grep:

```bash
grep -cE "background: #[0-9a-fA-F]{3,6}|color: #[0-9a-fA-F]{3,6}" src/styles.css
```

### Lesson
A single-theme stylesheet hides this class of defect: the literals are *correct*
until the moment they are not. Theme work should begin with the grep, not the
screenshot — inspection found all eight in seconds, and a screenshot would have
found the two that happen to be on screen.

---

## Summary

| Id | Severity | Class | Fixed |
|---|---|---|---|
| D-24 | Low | State not recorded on one code path | ✅ |
| D-25 | Medium | Environment-dependent test; silent skips | ✅ |
| D-26 | Low | Ambiguous form labels | ✅ |
| D-27 | Low | Hard-coded colours vs. a second theme | ✅ |

**Twenty-seven defects across five milestones; twenty-six fixed with regression
coverage; one environment gap (D-08 — the Docker daemon) documented with its
confirming command.**

The pattern is consistent with earlier phases: every defect was found by *running*
or *inspecting* something that had only been reasoned about. This round adds a
variation worth recording — **D-25 was a test that was green and covering
nothing**, and it took a failure in a neighbouring case to reveal that three
others were skipping. A passing suite can be a quieter problem than a failing one.
