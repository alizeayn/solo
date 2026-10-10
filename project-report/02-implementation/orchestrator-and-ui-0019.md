# 19 — Orchestrator, State Foundation and UI

**Stage:** Implementation
**Date:** 2026-10-10

---

## 1. The Orchestrator

`services/orchestrator_brain.py` is the reasoning layer. Its four methods map
directly onto the responsibilities named in the request.

| Request | Method | Output |
|---|---|---|
| Intent detection | `classify` | Pydantic-validated `IntentDecision` |
| Task decomposition | `classify` + `plan_from` | `list[PlannedTask]` |
| Prioritisation | `subtasks[].priority` / `depends_on` | ordering used by `next_pending()` |
| State management | notes + queue + active task | `OrchestrationState` |
| Concise summaries | `summarise` | 1–2 sentences for the task result and the panel |
| Project questions | `answer_question` | answer grounded in the bounded snapshot |

### Structured, validated output

Classification requests JSON against an explicit schema (`INTENT_SCHEMA`) and
validates it with Pydantic: an unknown intent value, an out-of-range priority or
a malformed payload is **rejected**, and the deterministic `IntentRouter` is used
instead. Model output never names a path, runs a command or edits anything.

**Guard rails.** A decision of `CHAT_OR_EXPLAIN`, `STOP_ACTIVE_TASK` or
`NEEDS_CLARIFICATION` has its subtasks stripped before use — the model cannot
smuggle work into a question. A test asserts this.

**Dependencies are resolved by Solo.** The model returns `depends_on` as sibling
*titles*; `plan_from` maps them onto generated ids, so the model never invents
identifiers.

### Fallback is permanent, not a stopgap

`available()` is false when there is no key, no model, or the feature is
disabled; every method returns `None` on failure or invalid output. Callers
always have a deterministic path, so a missing key, a provider outage or a bad
response degrades the experience rather than blocking a task.

`MessageDispatchResult.classified_by` reports `orchestrator-model` or `rules`, so
the UI can state which path was used instead of implying the model is always in
charge.

## 2. State foundation

`services/orchestration_state.py`, persisted to
`.solo/state/orchestration.json`.

```
OrchestrationState
├── active_task_id / active_plan_id
├── queue[]      PlannedTask{ title, instruction, priority, depends_on,
│                            status, source, task_id, note }
└── notes[]      { text, kind, task_id, applied, created_at }
```

| Property | Why |
|---|---|
| Durable and project-scoped | Travels with the project, like everything else in `.solo/` |
| Bounded | Queue 100 (lowest priority dropped first), notes 200, subtasks 6 |
| Dependency-aware | `next_pending()` returns the highest-priority pending step whose dependencies are `done` |
| Revision counter | Lets the UI tell that state moved |
| Notes with `applied` | Records *what the user asked* and *what happened to it* — the foundation for Phase 3's "decide how a late instruction affects the running task" |

### Addressing the "remember my new instructions" requirement

When an instruction arrives while a task is running:

1. it is **steered into Pi** through Pi's own mechanism, and
2. it is **recorded as a note** with `applied: "steered"`.

If it could not be applied (a task is already running and cannot take it), it is
recorded with `applied: null` and shown as **pending** in the Plan panel. Nothing
the user said is lost, and the state says exactly what happened to it — which is
the contract the later reasoning model needs in order to re-plan.

## 3. Every task is tracked, even without the model

`start_coding_task` writes a queue entry for every coding task, with
`source: "user"` when it came directly from a message. So the Plan panel and the
state model are meaningful with the Orchestrator disabled, and switching the
model on adds planning on top rather than changing the model.

## 4. The automatic queue

`_after_task_settled` runs after the terminal status has been broadcast:

1. the Orchestrator writes a concise summary (when configured);
2. Pyright checks the changed files;
3. the plan step is marked `done` or `failed`;
4. **on success only**, the next ready step starts automatically.

A failed step stops the chain — Solo does not continue past an error without a
decision from the user. The whole chain is visible in the Plan panel, where a
step can be skipped, removed, or started on demand.

## 5. Ordering: why post-settle work is asynchronous

The summary is an LLM call that may take tens of seconds. Running it before the
terminal status broadcast would delay the moment the user is told the task
finished. So:

```
set status → write the task record to .solo/ → broadcast → [async] summarise, check, advance
```

A test polls for the plan status because it legitimately lands a moment later.

## 6. Cost control

| Control | Value |
|---|---|
| Summaries | **Once per settled task**, not per event. Live detail comes from the normalised event stream, which is free |
| Prompt inputs | Clipped: message 2 000 chars, context 4 000, activity 3 000, 40 activity lines |
| Decomposition | Max 6 subtasks per request |
| Timeout | Configurable (default 45 s); a failure falls back rather than retrying blindly |

Mid-run narration was deliberately **not** implemented: the per-event messages
(`Created src/app.py`, `Tests finished: 3 passed`) are already meaningful, and a
per-milestone LLM summary would add latency and cost for little gain in a
text-only UI. The summarisation interface is exactly what Phase 5's voice
narration will consume, so nothing is blocked by the decision.

---

## 7. UI improvements

Scope: what Phase 2 needed, plus the responsiveness and polish the request asked
for. No broad redesign.

### New screens

| Component | Purpose |
|---|---|
| `OrchestratorSettings.tsx` | Key, test, model discovery, model selection, enable/disable, call statistics |
| `PiAgentSettings.tsx` | Runtime status, provider picker, credential entry, two-stage validation, model discovery and selection, thinking level, project trust |
| `OrchestrationPanel.tsx` | The plan: prioritised queue with dependencies, per-step skip/remove/start, recorded instructions with their applied state |

### New layout

- **`SettingsView` is now a tabbed shell** — Orchestrator · Pi Agent · Voice ·
  Preferences — with a per-tab hint line. The previous single long form had
  become the wrong shape for two independent models each needing discovery,
  validation and selection.
- **The Inspector gained a third tab**: Task · **Plan** · Project state.

### Activity panel

- **Static checks section**: outcome pill, file/duration counts, and up to twelve
  diagnostics with `file:line:column`, message and rule.
- **A queued-steps chip** in the header, from the live orchestration channel.
- Changed files and the timeline are unchanged, so the panel still reads as a
  monitor rather than a log viewer.

### Responsiveness and polish

| Change | Reason |
|---|---|
| Tabbed settings with a scrollable body and a fixed footer | The old modal's single form overflowed on small screens |
| `.form-actions` wrap layout | Buttons no longer overflow on narrow panels |
| Model lists are bounded, filterable and capped at 80 rendered rows | OpenRouter returns 400+ models; rendering all of them blocked the UI |
| `aria-label` on state badges | Assistive technology (and tests) can address the verification state unambiguously |
| `role="alert"` on failure banners | Failures are announced, not just coloured |
| Existing responsive behaviour preserved | Below 900 px the tiled layout still becomes tabs |
| New style tokens only: `.settings-shell`, `.settings-tab`, `.model-list`, `.check-card`, `.diagnostics`, `.plan-item`, `.form-actions` | The design system's custom properties were reused; no new palette |

### UI improvements deliberately deferred

A full visual redesign, per-panel themes, drag-to-reorder in the plan, inline diff
viewing, and diagnostics jumping to a file. These belong in a dedicated UI phase
once the voice surface exists and its requirements are known.
