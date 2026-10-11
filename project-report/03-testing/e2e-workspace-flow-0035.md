# Testing — Orchestrator configuration, tiles, milestones

| | |
|---|---|
| **Stage** | Focused update before Phase 3 |
| **Version** | 2.4.0 |
| **Date** | 2026-10-11 |

---

## 1. Suites

| Suite | Result |
|---|---|
| Backend (pytest) | **411 passed**, 0 failed, 0 skipped — 67 s |
| Frontend (vitest) | **116 passed** across 16 files |
| Frontend typecheck (`tsc --noEmit`) | clean |
| Frontend production build | succeeded (712 kB JS, 155 kB CSS) |
| `scripts/e2e.sh` (deterministic simulator) | **63 passed, 0 failed** |
| `scripts/e2e-live.sh` (real Pi Agent, OpenRouter) | **42 passed, 0 failed** |

Backend went 375 → 411 (+36). Frontend 103 → 116 (+13).

---

## 2. New backend coverage

### `tests/test_orchestrator_config_flow.py` — 9 tests

Written to reproduce the reported scenario before fixing it.

| Test | Property |
|---|---|
| key saved, no model → `/models` 200 | the reported bug, directly |
| the endpoint actually reached OpenRouter | not short-circuited by a stub |
| Settings UI and endpoint read one source | `openrouter_api_key.configured is True` |
| the key is never returned in JSON | secret handling |
| the key survives a restart | second `create_app` on the same data dir |
| no key → names the missing key | correct error text |
| model required for completions, not listing | `credentials()` ≠ None, `client()` = None |
| disabled Orchestrator → says "disabled" | the toggle reaches the runtime |
| the selected model is what the runtime uses | `model == "vendor/chosen"` |

HTTP is stubbed at `app.services.openrouter.httpx.AsyncClient`, and the stub
counts calls, so "returned a model list" cannot pass by returning a hard-coded
value.

### `tests/test_milestones.py` — 28 tests

**Derivation** (pure, no I/O) — acceptance → understanding; a plan is evidence of
planning; a progress summary *without* plan evidence is **not** a milestone; the
first file change closes the previous phase and opens implementation; further
changes extend evidence without new milestones; tests open verification; a static
check also counts; an error opens a failed blocked milestone; completion closes
the chain; cancellation and failure differ; **unrelated events produce nothing**;
the history is bounded; sequence numbers are monotonic.

**Service** — a milestone is published on the `milestone` channel and narrated;
an error narrates at `CRITICAL`; the model may reword but a failure falls back to
`worded_by="evidence"`; **the model is never called when the evidence justified
nothing** (the anti-fabrication test); snapshot/restore round trip; malformed
payloads are ignored; serialisation is stable.

**Integration** — a real coding task through the container produces an
evidence-backed chain starting at `understanding` and ending at `completed`, and
the snapshot is written to `.solo/state/milestones.json`.

**API layer** — `test_milestone_endpoints_serve_a_completed_task` and the 404.

**Races and defects** — trailing events do not reopen a completed chain; a
completed chain stays closed after a reload; a mid-run failure may still be
followed by recovery; repeated errors produce one `blocked` milestone.

---

## 3. New frontend coverage

### `src/panels/MilestonePanel.test.tsx` — 9 tests

Empty state explains itself; the chain renders in sequence with stages and
evidence; ordering is by `sequence`, not arrival; the current milestone is
distinguished from completed ones; a failed milestone is marked; the current
detail is revealed progressively (asserts it starts short, then grows); a
completed milestone shows in full without animating; model wording is noted; an
offline indicator appears when the stream drops.

### `src/hooks/useTypewriter.test.ts` — 4 tests

Disabled → full text; empty input; progressive reveal then completion; `null`
handling.

---

## 4. End-to-end: the requested scenario

`scripts/e2e-live.sh` was run against the **real** Pi Agent with
`PI_TEST_PROVIDER=openrouter PI_TEST_MODEL=openai/gpt-4o-mini`.

Task submitted through the chat path:

> Create a file named `hello_world.py` … define a `main()` that prints
> "Hello World from Pi", with an `if __name__ == "__main__"` guard. Use the write
> tool, then run it with python3 and report the output.

| # | Step | Result |
|---|---|---|
| 1 | Workspace accepts and submits | ✓ intent `START_CODING_TASK`, task created |
| 2 | Backend creates task state, starts real Pi | ✓ `run.started` |
| 3 | Pi Agent does real work | ✓ `tool.started`, `file.changed` |
| 4 | Activity tile shows real events | ✓ `run.started`, `file.changed`, `tool.started`, `assistant.message`, `run.finished` |
| 5 | Orchestrator uses the configured model | ✓ provider `openrouter`, model `openai/gpt-4o-mini` validated |
| 6 | Milestones identified, state updated | ✓ 3 milestones |
| 7 | Milestone tile updates incrementally | ✓ chain `understanding → implementing → completed` |
| 8 | Files created, tests executed | ✓ `hello_world.py` on disk, 83 bytes, correct contents |
| 9 | Workspace shows the actual result | ✓ summary quoted the program output |
| 10 | Final state consistent | ✓ disk = memory = API; snapshot persisted |

Actual file written by the agent:

```python
def main():
    print("Hello World from Pi")

if __name__ == "__main__":
    main()
```

Pre-existing `main.py` was left untouched.

### First live attempt — a genuine failure, reported honestly

The first attempt used `opencode-go`, which returned
`403 … An active OpenCode Go subscription is required`. The task correctly ended
`FAILED`, no file was created, and the milestone chain was
`['understanding', 'blocked', 'blocked']`.

That run **found a real defect**: one bad run produced several `error` events and
opened a `blocked` milestone for each (D-35). It is fixed and covered. The live
assertion was also corrected: a run that failed because the provider refused the
request must end `blocked`, and asserting `completed` there would reward a green
tick over the truth.

---

## 5. Test hygiene

`test_pi_runtime.py::test_the_host_pi_directory_is_never_touched` performed a real
`npm install` from the network (144.68 s). It now takes the `fake_npm` fixture,
asserts `installed.ok is True`, and documents that a unit test must not reach the
network. Suite time 407 s → 68 s.

## Related

- [Implementation 0034](../02-implementation/orchestrator-config-and-tiles-0034.md)
- [Defect log 0036](../04-defects/defect-log-0036.md)
- [Verification 0037](../05-verification/acceptance-criteria-0037.md)