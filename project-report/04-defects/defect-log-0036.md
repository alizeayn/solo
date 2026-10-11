# Defect log — Orchestrator configuration, tiles, milestones

| | |
|---|---|
| **Stage** | Focused update before Phase 3 |
| **Version** | 2.4.0 |
| **Date** | 2026-10-11 |
| **Defects** | D-28 … D-36 (9) |

---

## D-28 — **Retrieve Models** reported a missing key when the key was saved

**Severity** High · **Status** Fixed · **Found by** user report

**Symptom.** Settings → Orchestrator → **Retrieve Models** returned
`The Orchestrator needs an OpenRouter API key added on the Orchestrator settings first.`
The key was saved and the key test passed.

**Root cause.** `OrchestratorBrain.client()` required **both** a key and a chosen
model:

```python
if not key or not model:
    return None
```

`/api/orchestrator/models` used that accessor. Listing models is the step that
comes *before* choosing one, so in the normal first-run state — key saved, no model
yet — the endpoint saw `None` and reported a missing key. The message named the
wrong cause.

**Fix.** Split the accessor by question: `credentials()` needs only a key (used for
listing), `client()` needs a key and a model (used for completions),
`is_enabled()` for routing. The router's `_require_client` became
`_require_credentials` + `_has_key`, with distinct messages for a disabled
Orchestrator with no key, a missing key, and everything else.

**Regression.** `tests/test_orchestrator_config_flow.py` — 9 tests, including the
reported scenario verbatim.

---

## D-29 — The Orchestrator enabled/disabled toggle did not reach the runtime

**Severity** High · **Status** Fixed · **Found by** a failing new test

**Symptom.** Disabling the Orchestrator in Settings changed nothing: completions,
status and routing behaved as if it were enabled.

**Root cause.** `available()`, `client()` and `configuration()` read
`self._settings.orchestrator_enabled` — the **static environment/config default** —
instead of the saved setting the UI writes. The toggle was decorative.

**Fix.** New `is_enabled()` reads `orchestrator_enabled` through
`settings_service.get_bool(...)` with the static value as a *default*, and only
falls back to the static value if the store raises. All three call sites use it;
`configuration()` reports `"enabled": await self.is_enabled()`.

**Why it matters beyond this bug.** It is the same class of error as D-28: a
runtime reading a static default while the user's saved configuration lives
elsewhere. Both were found by asking "does the value the UI writes actually reach
the thing that acts on it?"

---

## D-30 — Existing users never received the new workspace tiles

**Severity** High · **Status** Fixed · **Found by** reading `DockLayout`

**Symptom.** New panels did not appear for anyone who had used an earlier build.

**Root cause.** The layout was stored under `solo.layout.v1` and the key was never
bumped when panels were added. A stored v1 layout contains `conversation`,
`activity`, `inspector` — all still registered — so `api.fromJSON(stored)`
**succeeded**, `restored` became true, and `addDefaultLayout` (which registers
Write and Voice) never ran. Nothing validated the restored layout against the
panel set.

**Fix.** Key bumped to `solo.layout.v3` (with stale v1/v2 entries cleared); the
default layout became data (`PANEL_SPECS`); and **`ensureAllPanels(api)`** adds any
registered panel missing from a restored layout, anchored to one that exists. The
guarantee is now *every registered panel is present after load*, not *the default
layout is present when nothing was stored*.

---

## D-31 — A unit test performed a real `npm install` from the network

**Severity** Medium · **Status** Fixed · **Found by** suite timing (83 s → 407 s)

**Symptom.** The backend suite became slow and flaky and failed without network.

**Root cause.** `test_the_host_pi_directory_is_never_touched` called the real
installer, which shelled out to `npm install` (144.68 s of the run).

**Fix.** The test takes the `fake_npm` fixture, asserts `installed.ok is True`, and
documents that a unit test must not reach the network. The property under test —
the host Pi directory is never touched — is unchanged; only the mechanism is
faked. Suite time 407 s → 68 s.

---

## D-32 — Every milestone endpoint returned 500

**Severity** High · **Status** Fixed · **Found by** `scripts/e2e.sh`

**Symptom.** `GET /api/milestones/task/{id}` returned 500 while the WebSocket
stream and the tracker were both working.

**Root cause.** `_hydrate` did `payload = await container.store.read_milestones(project)`,
but `read_milestones` is **synchronous** plain file I/O:
`TypeError: object dict can't be used in 'await' expression`.

**Fix.** `await asyncio.to_thread(container.store.read_milestones, project)`.

**Why the tests missed it.** The service-level tests exercised the tracker and the
bus, never the REST layer. The regression test goes through HTTP deliberately.

---

## D-33 — A trailing event reopened a completed milestone chain

**Severity** High · **Status** Fixed · **Found by** the new API test

**Symptom.** A completed task's chain ended on `verifying` instead of `completed`.

**Root cause.** The terminal transition and the last verification event are not
ordered relative to each other. A `test.result` arriving after `finish()` opened a
fresh `verifying` milestone, so the chain no longer ended on the outcome and the
panel showed work still in progress for a finished task.

**Fix.** The tracker keeps a `_closed` set. `finish()` closes the chain *before*
recording the terminal milestone, and `observe()` returns `None` for a closed task.
On reload only `completed`/`cancelled` are treated as authoritative — a `blocked`
milestone can come from a mid-run error the agent recovered from.

**Note.** `_closed` is kept separately from the milestone list because "is this
task over" is a different question from "what milestones does it have".

---

## D-34 — The task row became terminal before the outcome was recorded

**Severity** Medium · **Status** Fixed · **Found by** the same test

**Symptom.** A client polling task status could observe `COMPLETED` and then read a
milestone still marked `active`.

**Root cause.** `_set_status` wrote the terminal row first and closed the milestone
chain afterwards, inside the same request.

**Fix.** `_set_status` now reads in one session, closes the milestone chain in its
own context, then opens a second session to write the row (re-checking the terminal
guard, since a concurrent settlement may have won). The chain is therefore final
before the terminal status is visible anywhere. This also keeps the store write and
the optional model call out of a database transaction.

---

## D-35 — One failure produced three `blocked` milestones

**Severity** Medium · **Status** Fixed · **Found by** the live e2e run

**Symptom.** A task that failed because the provider refused the request showed
`['understanding', 'blocked', 'blocked']` — the same obstacle twice.

**Root cause.** A single bad run emits several `error` events (the provider's
error, the agent giving up, the task settling), and each opened a new `blocked`
milestone.

**Fix.** A repeated error extends the existing `blocked` milestone's evidence and
detail instead of opening a new one. A *different* later failure is still recorded
as its own evidence.

**How it was found.** Only a real provider failure produced it. The deterministic
simulator never fails this way, which is the argument for keeping the live suite.

---

## D-36 — The live suite asserted `completed` for a run that had failed

**Severity** Low (test honesty) · **Status** Fixed · **Found by** the same run

**Symptom.** With `opencode-go` returning 403, the milestone assertion failed with
`AssertionError: ['understanding', 'blocked', 'blocked']` — the *test* was wrong,
not the product.

**Root cause.** The assertion hard-coded a successful outcome.

**Fix.** The live script reads the final task status and asserts the chain that
matches it: a `COMPLETED` run must reach `completed` via `implementing`; a failed
run must end `blocked` or `cancelled`. It also asserts at most one `blocked`
milestone (D-35). Asserting success unconditionally would reward a green tick over
the truth.

---

## Open

| ID | Issue | Status |
|---|---|---|
| **D-08** | Docker image build not executed — no daemon socket access | Open (environment) |
| — | No automated visual/browser verification | Accepted limitation |
| — | No audio transport; `audio_available: false` | By design (Phase 4) |
| — | OpenRouter completions need credit; milestone wording falls back to evidence | Environment |

## Related

- [Implementation 0034](../02-implementation/orchestrator-config-and-tiles-0034.md)
- [Testing 0035](../03-testing/e2e-workspace-flow-0035.md)
- [Verification 0037](../05-verification/acceptance-criteria-0037.md)