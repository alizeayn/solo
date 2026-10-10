# 10 — Summary

**Stage:** Summary
**Date:** 2026-10-10
**Phase:** 1 of 6 — Deployable shell
**Status:** ✅ Complete and verified

---

## 1. What was delivered

A secure, deployable, single-origin application whose entire critical path works
end to end:

> **sign in → create or import a project → ask a question → start a coding task
> → watch normalized events stream in → steer the running task → reach a
> terminal status → state survives a restart**

| Deliverable | Location |
|---|---|
| FastAPI backend (33 modules, 1 965 statements) | `backend/app/` |
| React + TypeScript + Dockview frontend (20 modules) | `frontend/src/` |
| 123 backend tests, 89 % coverage | `backend/tests/` |
| 22 frontend tests | `frontend/src/**/*.test.ts(x)` |
| 26-check end-to-end smoke test | `scripts/e2e.sh` |
| Dockerfile, Compose, installer, backup/restore, dev workflow | root + `scripts/` |
| README and four technical documents | root + `docs/` |
| This report | `project-report/` |

---

## 2. Metrics

| Metric | Value |
|---|---|
| Backend modules / statements | 33 / 1 965 |
| Frontend modules | 20 |
| Backend tests | 123 passed, 0 failed, 89 % coverage |
| Frontend tests | 22 passed, 0 failed |
| End-to-end checks | 26 passed, 0 failed |
| TypeScript errors | 0 (`strict: true`) |
| Runtime dependencies | Backend 9 (pinned), frontend 4 |
| Defects found / fixed | 8 / 7 (1 environment gap, documented) |
| Acceptance criteria verified | 9 fully, 3 partially, 2 deferred |
| Backend suite runtime | ~31 s |
| Frontend bundle | 644 kB JS (167 kB gzip), 139 kB CSS |

---

## 3. Key engineering decisions

1. **Domain vocabulary first.** Statuses, event types and intents were frozen
   before any service was written, so every module switches on the same enums
   and no provider string ever reaches the database.
2. **Repositories as the only database consumer.** Business logic cannot write
   SQL, which makes a PostgreSQL migration an engine-URL change.
3. **Adapter contract before the real provider.** Building the simulator against
   the same protocol the Pi adapter will implement meant the entire product path
   could be validated safely in Phase 1 — and made `build_adapter` a
   one-line switch for Phase 2.
4. **Persist before broadcast.** Every event is committed to SQLite before the
   WebSocket frame is sent, so a dropped socket can never lose state.
5. **Terminal states are sticky.** A single guard in `_set_status` closes an
   entire class of races (D-02) rather than patching one path.
6. **Deterministic routing where determinism is possible.** The LLM classifier
   is deferred to Phase 3, and only where the rules are genuinely ambiguous.
7. **Honesty in the UI.** Voice and attachment controls are rendered *disabled*
   with phase labels. A control that appears to work but does not is worse than
   no control, and the specification explicitly forbids claiming untested
   capability.
8. **Validate the original input, then transform.** The D-01/D-03 pair shows why
   ordering matters more than the individual check.

---

## 4. Defects and what they taught

| Class | Defects | Lesson |
|---|---|---|
| Path traversal | D-01, D-03 | Validate *before* normalising or rewriting a name. |
| Concurrency | D-02, D-06 | Guard terminal states; a cancellation that arrives before a session starts must be queued, not dropped. |
| Classification | D-04 | Precedence order and substring verb matching are both fragile in natural language. |
| Async ORM | D-05 | Never let a response model trigger a lazy load. |
| Filesystem edge case | D-07 | `exists()` is not `is_file()`; bind-mounts make this reachable. |
| Environment | D-08 | Audit *daemon* access, not just client presence. |

**Seven of eight were found by writing tests.** The suite earned its keep on the
first pass: it produced a critical traversal bypass, a state-corruption race, a
silently-ignored cancellation and a wrong routing decision — none of which a
casual click-through would have revealed. Each now has a dedicated regression
test, and the four most instructive are written up in `docs/development.md` so
they are not reintroduced.

---

## 5. Verification summary

| Layer | Method | Result |
|---|---|---|
| Unit | 123 pytest + 22 Vitest | ✅ |
| Types | `tsc --noEmit`, `strict` | ✅ 0 errors |
| Integration | TestClient with lifespan | ✅ |
| System | Real uvicorn + real SPA + real SQLite (`scripts/e2e.sh`) | ✅ 26/26 |
| Runtime dependency set | Fresh venv, `python -m app` (the container `CMD`) | ✅ |
| Frontend build | `npm ci` against the committed lockfile + `vite build` | ✅ |
| Shell scripts | `bash -n` × 4 | ✅ |
| Compose configuration | `docker compose config --quiet` | ✅ |
| Container image | `docker compose build` | ⚠️ blocked (D-08) |

---

## 6. Honest limitations

Recorded so they cannot be mistaken for completed work:

1. **The coding agent is a simulator.** It emits a realistic, ordered event
   stream and modifies **no files**. This is stated in the README's status
   table, in `docs/api.md`, in the Settings UI ("active backend: simulated agent
   — no files are modified") and in the acceptance criteria.
2. **No LLM inference is performed.** Intent routing is deterministic and
   unit-tested. Provider credentials can be stored and *tested*, but no model is
   called.
3. **No audio.** No voice or TTS code path exists. The controls are disabled and
   labelled. Criterion 11's "only after overlap/interruption testing" condition
   is therefore honoured by construction rather than by testing.
4. **The Docker image was never built.** The daemon is unreachable from this
   session. Nine of ten verification layers pass; all steps the image performs
   were reproduced natively and served the app correctly, but this remains
   strictly weaker than building the image.
5. **No browser-driven UI test.** Component tests plus a real-server API-level
   end-to-end run cover the path; the UI itself is verified by typecheck, manual
   inspection and component tests, not by an automation harness.
6. **`orchestrator.py` is 77 % covered.** The remaining lines are defensive
   shutdown and corruption branches; every state transition is tested.

---

## 7. Recommended next steps

### Immediate (closes the Phase 1 verification gap)

```bash
sudo usermod -aG docker "$USER"   # re-login afterwards
docker compose build
docker compose up -d
curl -fsS localhost:8080/api/health
```

### Phase 2 — Pi RPC integration (highest value)

1. Read the authoritative local documentation before writing code:
   `…/pi-coding-agent/docs/rpc.md`, `rpc-commands.md`, `cli-integration.md`.
2. Implement `PiCodingAgentAdapter` against the contract in `adapters/base.py`:
   launch a managed long-lived subprocess in RPC mode, consume stdout as JSONL,
   keep stderr separate, correlate responses by request id, and distinguish
   "prompt accepted" from "task settled".
3. Carry over the D-06 requirement: a cancellation arriving before the session
   starts must be queued, never dropped.
4. Translate protocol records into the existing `domain.EventType` values — no
   protocol parsing outside the adapter.
5. Verify version compatibility and document any limitation found.
6. Tests with a fake transport; never call a real provider in the suite.

### Phase 3 — OpenRouter context layer

Implement `classify` behind the existing `IntentRouter` contract with
Pydantic-validated output, plus bounded summaries and project Q&A. Reuse
`ContextSnapshot` and `build_snapshot`; keep the hard caps.

### Phase 4–5 — Voice and spoken progress

Signed-URL session from the backend (the API key must stay server-side), then
the speech arbiter/queue with explicit overlap and interruption tests. Only
claim proactive speech once that behaviour has been demonstrated.

### Phase 6 — Hardening

A real-server smoke test on the target host, installer idempotency re-check after
schema changes, and the reverse-proxy configuration exercised end to end.

---

## 8. Conclusion

Phase 1 met its objective: the smallest useful, polished, deployable version of
the product exists, is secure by default, is documented, and is covered by 171
passing checks across four verification layers.

The most valuable outcome is arguably structural rather than functional. The
contracts that later phases depend on — the task/event vocabulary, the adapter
protocol, the intent-router interface, the bounded context snapshot, the
repository boundary and the encrypted settings store — are all in place and
tested. Phase 2 replaces exactly one class (`PiCodingAgentAdapter`); Phase 3
replaces exactly one method (`IntentRouter.classify`); Phases 4 and 5 fill in
UI that is already reserved and labelled. Nothing in the core needs rewriting to
accommodate them, which is the property the specification asked for.

The discipline that produced that outcome was mostly about *ordering*: freeze
the vocabulary before the services, validate input before transforming it,
persist before broadcasting, confirm before marking cancelled, and label what is
not yet built instead of letting it look finished.
