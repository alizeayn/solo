# Orchestrator

The Orchestrator is Solo's decision layer. It answers three questions: *what is
the user asking for*, *what should happen next*, and *how should this be
described back to the user*. In Phase 2 it is powered by an OpenRouter model,
with deterministic rules as a permanent fallback.

Configure it in **Settings → Orchestrator**. Disable it and Solo still works.

---

## 1. Responsibilities (MVP scope)

| Responsibility | Method | Used by |
|---|---|---|
| Intent detection | `OrchestratorBrain.classify` | message routing |
| Task decomposition | `classify` (structured `subtasks`) + `plan_from` | the plan queue |
| Prioritisation and ordering | `subtasks[].priority`, `depends_on` | `OrchestrationState.next_pending` |
| State management | notes, queue, active task | `OrchestrationState` |
| Concise summaries | `OrchestratorBrain.summarise` | task result + Activity panel |
| Project questions | `OrchestratorBrain.answer_question` | Conversation panel |
| Choosing what goes to Pi, and when | `_advance_queue` | automatic sequential execution |

### What it deliberately does not do

- It never chooses a file path, runs a command, or edits anything. It emits a
  validated intent and a plan; the coding agent executes.
- It never narrates every tool call. The workspace shows detail; the model
  produces short summaries.
- It never blocks a task. Every method returns `None` on failure and the
  deterministic path takes over.

---

## 2. How a message is routed

```
message ──► brain.classify()  ──structured, Pydantic-validated──►  IntentDecision
                │ unavailable / failed / invalid
                ▼
            IntentRouter (deterministic rules)
                │
                ▼
        STOP | STEER | START | CHAT | NEEDS_CLARIFICATION
```

The router reports which path was used in `classified_by`
(`orchestrator-model` or `rules`), so the UI can show it.

**Guard rails.** A `CHAT_OR_EXPLAIN`, `STOP_ACTIVE_TASK` or
`NEEDS_CLARIFICATION` decision has any subtasks stripped before use: the model
cannot smuggle work into a question.

### Structured output

Classification asks OpenRouter for JSON conforming to an explicit schema and
validates it with Pydantic. An invalid intent value, an out-of-range priority or
a malformed payload is rejected and the deterministic rules are used instead.
Model output is never trusted to name a path, a command or a project.

---

## 3. Orchestration state

Persisted per project in `.solo/state/orchestration.json`, so it travels with
the project. Managed by `backend/app/services/orchestration_state.py`.

```json
{
  "version": 1,
  "project_id": "…",
  "revision": 7,
  "active_task_id": "…",
  "active_plan_id": "a1",
  "queue": [
    {
      "id": "a1", "title": "Create the module",
      "instruction": "Create src/pkg/mod.py with a hello() function",
      "priority": 10, "depends_on": [], "status": "running",
      "task_id": "…", "source": "orchestrator"
    },
    {
      "id": "a2", "title": "Write tests",
      "instruction": "Add pytest tests for src/pkg/mod.py",
      "priority": 20, "depends_on": ["a1"], "status": "pending",
      "source": "orchestrator"
    }
  ],
  "notes": [
    {
      "id": "n1", "text": "also update the changelog",
      "kind": "instruction", "task_id": "…",
      "applied": "steered", "created_at": "…"
    }
  ]
}
```

| Concept | Meaning |
|---|---|
| `priority` | 0 = do first, 100 = do last. `next_pending` picks the lowest number |
| `depends_on` | Ids of steps that must reach `done` first. Resolved from sibling *titles*, so the model never invents ids |
| `status` | `pending` · `running` · `done` · `failed` · `skipped` |
| `source` | `orchestrator` (planned) or `user` (a direct instruction) |
| `notes` | Instructions received while a task was running, with how each was applied |
| `revision` | Bumped on every change; the UI uses it to know the state moved |

### Why this is the foundation for Phases 3–5

The later phases add a reasoning model and a voice model. They do not need new
architecture: they read and write this same structure.

| Future requirement | Expressed as |
|---|---|
| Manage conversation and project state | the state document, extended with fields |
| Break complex requests into smaller tasks | `queue` entries |
| Prioritise by importance and dependency | `priority`, `depends_on`, `next_pending` |
| Generate concise summaries of Pi's work | `OrchestratorBrain.summarise` (already the source) |
| Real-time voice explanation of progress | narrate the same summaries |
| Retain new instructions mid-task | `notes` (already captured) |
| Decide which tasks go to Pi and in what order | `next_pending` + `_advance_queue` (already automatic) |

---

## 4. Lifecycle in practice

1. A compound request arrives. The model returns `is_compound: true` with
   ordered subtasks and dependencies.
2. The plan is written to the state store and the first ready step starts.
3. Pi runs it. Events stream to the UI as they happen.
4. On completion the model writes a concise summary, Pyright checks the changed
   files, the queue entry is marked `done`, and the **next ready step starts
   automatically**.
5. A failed step stops the chain: Solo does not continue past an error without a
   decision from the user.
6. An instruction sent mid-run is both **steered into Pi** and **recorded as a
   note** with `applied: "steered"`. An instruction that could not be applied
   (because a task was already running) is recorded with `applied: null` and
   shown as pending in the Plan panel.

Every coding task is tracked, even with the model disabled: a direct instruction
creates a single `source: "user"` queue entry. That keeps the Plan panel and the
state model meaningful without an LLM.

---

## 5. Configuration and validation

**Settings → Orchestrator.**

| Step | Endpoint | Notes |
|---|---|---|
| Save key | `PUT /api/settings` | Encrypted at rest, masked in responses, never returned |
| Test key | `POST /api/orchestrator/test?deep=false` | `GET /api/v1/key` — free |
| Verify model | `POST /api/orchestrator/test?deep=true` | One real completion — the only thing that yields `verified` |
| Retrieve models | `GET /api/orchestrator/models` | OpenRouter's catalog, filterable |
| Save model | `PUT /api/orchestrator/config` | Persisted as `openrouter_model` |
| Disable | `PUT /api/orchestrator/config` | Back to deterministic rules |

The Status panel also reports call count, failure count, last model, last
latency and the last error, so you can see whether it is actually being used.

### Failure handling

| Failure | Result |
|---|---|
| No key or model configured | `available()` is false; the router and offline answers are used |
| Timeout / network error | Logged, counted, `None` returned; fallback used |
| Invalid JSON or schema violation | Rejected; fallback used |
| Provider 401/402 | Surfaced verbatim in Settings; tasks still run |

---

## 6. Bounding and cost

- Every prompt input is clipped (`MAX_MESSAGE_CHARS`, `MAX_CONTEXT_CHARS`,
  `MAX_ACTIVITY_CHARS`) so input never grows with the project.
- Summarisation runs **once per settled task**, not per event. Live detail comes
  from the normalised event stream, which costs nothing.
- Decomposition is capped at 6 subtasks; the queue is capped at 100 entries;
  retained notes at 200.
- A request never waits on the model: Pyright, the store write and the summary
  all run *after* the task's terminal status has been broadcast.
