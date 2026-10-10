# 22 — Phase 2 Summary

**Stage:** Summary
**Date:** 2026-10-10
**Milestone:** Phase 2 — execute coding tasks through Chat
**Status:** ✅ Complete and verified with a real model

---

## 1. What was delivered

**Solo now runs real coding work.** A request typed into Chat is classified,
planned, handed to the Pi Agent, executed inside the opened project, streamed
back into the workspace, verified by Pyright, summarised, and recorded — with the
files genuinely changed on disk.

| Deliverable | Location |
|---|---|
| Pi RPC transport, event translation, session manager, adapter | `backend/app/adapters/pi_*.py` |
| Pi configuration service (providers, credentials, models, validation) | `backend/app/services/pi_config.py` |
| OpenRouter client + Orchestrator brain | `backend/app/services/{openrouter,orchestrator_brain}.py` |
| Durable orchestration state | `backend/app/services/orchestration_state.py` |
| Pyright verification | `backend/app/services/checks.py` |
| Pi / Orchestrator / Plan / Checks APIs | `backend/app/api/{pi,orchestrator,orchestration}.py` |
| Settings UI (Orchestrator, Pi Agent, Voice, Preferences) | `frontend/src/components/*Settings*.tsx` |
| Plan panel | `frontend/src/panels/OrchestrationPanel.tsx` |
| Pi reference + integration notes | `Pi Agent Docs/` (21 documents) |
| Live acceptance test | `scripts/e2e-live.sh` |

---

## 2. Metrics

| Metric | Phase 1.5 | **Phase 2** |
|---|---|---|
| Backend tests | 194 | **288** |
| Frontend tests | 39 | **68** |
| Live end-to-end checks | – | **26** (real Pi) |
| Simulator end-to-end checks | 53 | 53 |
| Backend coverage | 91 % | **86 %** (2 400 more statements) |
| Backend modules | 45 | **56** |
| Defects found / fixed | 12 / 11 | **16 / 15** |

Total automated checks: **382**, all passing. The 26 live checks are the ones
that matter most: they prove a real model wrote a real file.

---

## 3. The four findings that shaped the design

Everything downstream followed from these, and all four were verified rather
than assumed:

1. **A fresh Pi agent directory has zero models.** So Solo reuses the user's Pi
   installation instead of isolating it — the opposite of the instinctive design.
2. **`auth.json` overrides environment variables.** So Solo writes Pi's own
   credential file, which is also what the request asked for.
3. **Non-interactive modes cannot answer the trust prompt.** So Solo decides
   explicitly (`--no-approve` by default) rather than depending on a saved state.
4. **Provider failures arrive in the message stream, not the exit code.** So task
   success is derived from `agent_settled` plus a non-error terminal message, and
   a clean exit is never treated as success.

A fifth, smaller finding was decisive for reliability: a real provider error
(`402 Insufficient credits`) surfaced during development and drove the whole
error-reporting design — the user sees the provider's own words.

---

## 4. How the state foundation is future-proof

The request listed what Phases 3–5 will need. Each maps onto something that
already exists:

| Phase 3–5 requirement | Phase 2 implementation |
|---|---|
| Manage conversation and project state | `.solo/state/orchestration.json` |
| Decompose complex requests | `queue[]` with `priority` and `depends_on` |
| Prioritise by importance and dependency | `next_pending()` |
| Concise summaries of Pi's activity | `OrchestratorBrain.summarise` |
| Voice explanation of progress | narrate the same summaries |
| Retain mid-task instructions and know their effect | `notes[]` with `applied` |
| Decide what goes to Pi, in what order | `_advance_queue`, automatic on success |

The design rule: **later phases add consumers of this state, not new
architecture.** A reasoning model reads and writes the same document; a voice
model narrates the summaries that are already generated.

---

## 5. UI work in this phase

Scoped to what Phase 2 needed, plus the responsiveness and polish requested:

- **A tabbed settings shell** (Orchestrator · Pi Agent · Voice · Preferences) with
  a scrollable body and fixed footer — the old single form was the wrong shape
  once two independent models each needed discovery and validation.
- **Two purpose-built panes** with honest three-state badges
  (`not_configured` / `configured` / `verified`), filterable model lists capped at
  80 rendered rows from catalogs of 400+, and explicit loading/notice/error states.
- **A Plan panel** showing the prioritised queue with dependencies and the
  recorded instructions, with skip / remove / start-now controls.
- **A static-checks section** in the Activity panel with outcomes and diagnostics.
- **Accessibility**: `aria-label` on state badges, `role="alert"` on failures.
- **Deferred deliberately**: a broad visual redesign, inline diffs, click-through
  diagnostics, drag-to-reorder. These belong in a dedicated UI phase once the
  voice surface defines its own requirements.

---

## 6. Definition of done

| Requirement | Status |
|---|---|
| Pi integrated and installed by Easy Installation | ✅ (local install, no sudo) |
| Pyright available and configured | ✅ |
| A coding task can be submitted through Chat | ✅ |
| Pi receives and executes it in the opened project | ✅ verified with a real model |
| Files are really created or modified | ✅ verified on disk |
| Progress is displayed in the browser workspace | ✅ |
| Project and task state managed correctly | ✅ incl. orchestration state and `.solo/` |
| Existing functionality is not broken | ✅ all 286 prior checks pass |
| Easy Installation works with the new dependencies | ✅ native path executed and verified |
| UI improvements work across screen sizes | ⚠️ by construction + component tests; **not** automated across breakpoints |
| Pi and Orchestrator configurable from Settings | ✅ with honest validation states |
| Documentation and report | ✅ |

---

## 7. Honest statement of what does not work yet

1. **The Docker image was not built** — no daemon access (D-08). The Dockerfile's
   Node + Pi step is unverified. The native install was executed instead.
2. **The live test used `opencode-go`.** The OpenRouter account available during
   development returns `402 Insufficient credits`, so the *coding* path was not
   exercised through OpenRouter. (The Orchestrator path through OpenRouter is
   implemented and unit-tested against a fake client; its live behaviour is
   bounded by that same credit limit.)
3. **No browser automation**, so responsive behaviour at specific breakpoints is
   verified by construction and manual use, not by a test.
4. **Mid-run narration is not implemented.** One summary per settled task; the
   per-event messages provide the live detail. The interface for Phase 5 is in
   place.
5. **Pi is not sandboxed.** Solo bounds *which* directories can be opened, not
   what Pi may do inside one.
6. **Voice and reasoning are untouched**, by instruction.

---

## 8. Recommended next steps

```bash
# Close the one outstanding verification gap
sudo usermod -aG docker "$USER"   # then re-login
docker compose build && docker compose up -d
curl -fsS localhost:8080/api/health
```

Then, in order:

1. **Add provider credit or an alternative provider** so the full live path can
   be exercised through OpenRouter as well as `opencode-go`.
2. **Phase 3 — deeper reasoning.** Retrieval-backed project Q&A, richer
   decomposition that re-plans when a step fails, and dependency-aware
   reordering that consumes `notes` rather than merely recording them.
3. **Phase 4 — voice.** The Conversation panel's voice control becomes real; the
   transcript and text fallback already exist.
4. **Phase 5 — spoken progress.** Narrate `summarise` output through the speech
   queue, with overlap and interruption tests, and only then claim it works.
5. **A dedicated UI phase** for the redesign deferred here.

---

## 9. Conclusion

Phase 2 is complete and — unusually for an integration of this size — verified
against the real tool rather than a simulated one. The decisive evidence is
small and concrete: a sentence typed into Chat produced `hello_world.py` on disk
with the requested contents, alongside `file.changed` events naming that exact
path, a task record in the project's own store, and a one-line summary written by
the Orchestrator.

Two things made that outcome achievable. First, **investigating before
implementing**: the four findings in §3 each inverted an assumption that would
otherwise have produced a broken or subtly wrong integration — most importantly,
isolating Pi's agent directory would have silently removed every model. Second,
**testing the transport against the documented protocol before wiring the UI**:
four defects (D-13…D-16) were caught at that stage, and three of them were the
kind that look like a working feature until the exact situation that exposes them.

The state model is the part most likely to repay its cost. It is deliberately
small — a queue, priorities, dependencies and notes — but it already answers the
questions Phase 3 will ask, and it is stored with the project rather than inside
Solo, so it survives being moved.
