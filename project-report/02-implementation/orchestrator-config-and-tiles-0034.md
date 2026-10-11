# Implementation — Orchestrator configuration, workspace tiles, milestones

| | |
|---|---|
| **Stage** | Focused update before Phase 3 |
| **Version** | 2.4.0 |
| **Date** | 2026-10-11 |

---

## 1. Orchestrator configuration flow

### The defect

`OrchestratorBrain` had one accessor and used it for two different questions:

```python
async def client(self):
    key = await self._settings_service.get_secret("openrouter_api_key")
    model = await self._settings_service.get_plain("openrouter_model")
    if not key or not model:
        return None          # ← model listing treated as "no key"
```

Model *listing* is the step that comes **before** a model is chosen. In the normal
first-run state — key saved, no model yet — `client()` returned `None`, and
`/api/orchestrator/models` reported a missing key. The message was not merely
unhelpful, it was wrong about the cause.

### The fix — three accessors for three questions

| Accessor | Requires | Used by |
|---|---|---|
| `is_enabled()` | nothing | status, routing decisions |
| `credentials()` | a key | model listing, key checks |
| `client()` | a key **and** a model | completions |

`is_enabled()` reads `orchestrator_enabled` through `settings_service.get_bool`
with the static `Settings` value as a *default*, falling back to the static value
only if the store raises. The environment value is a starting point, not an
override — the toggle in the UI must win, or the toggle is decorative.

`_require_client` in the router was replaced by `_require_credentials` plus a
`_has_key` helper, with **three distinct messages** for the three genuine causes:

1. disabled *and* no key → names both;
2. no key saved → names the key;
3. otherwise → proceeds, and a remote failure surfaces as 502 from OpenRouter.

A missing *model* is never reported as a missing *key*.

### Milestone wording hook

`describe_milestone(stage, title, evidence, instruction)` was added to the brain.
It calls the model with `MILESTONE_SYSTEM` and a strict schema
(`{"detail": str}`, required, no additional properties) and returns `None` on
`OpenRouterError`, `ValidationError`, or an empty result.

**It can only reword.** It receives a transition the tracker already justified
and returns prose for it. It cannot create a milestone, and with no key, no
credits, or a failing model the deterministic text is used unchanged.

---

## 2. Workspace tiles

### Why existing users saw no new tiles

`DockLayout` stored its layout under `solo.layout.v1` and never bumped the key
when panels were added. A stored v1 layout contains `conversation`, `activity`,
`inspector` — all still registered — so `api.fromJSON(stored)` **succeeded**,
`restored` became true, and `addDefaultLayout` (which registers Write and Voice)
never ran. There was no validation of the restored layout against the panel set.

### The fix

- Storage key bumped to `solo.layout.v3`; `clearLayout()` also removes the stale
  v1/v2 entries.
- `PANEL_SPECS` declares each panel's order and anchor, so the default layout is
  data rather than a sequence of imperative calls.
- **`ensureAllPanels(api)`** adds any *registered* panel missing from the
  restored layout, anchored to one that exists, and returns the ids it added.
  `onReady` restores, then calls `ensureAllPanels`, then falls back to
  `addDefaultLayout` if nothing was restored.

The guarantee is now: **every registered panel is present after load**, whether
the layout came from storage or from the defaults.

### The panels

| Panel | Backed by |
|---|---|
| `ConversationPanel` | `/api/projects/{id}/messages`, `/api/tasks` — the real dispatch path |
| `ActivityPanel` | `event` WebSocket channel, normalised runtime events |
| `MilestonePanel` | `milestone` WebSocket channel + `/api/milestones/task/{id}` |
| `VoiceChannel` | `/api/voice/state`, `narration` channel — UI and interfaces only |
| `WritePanel`, `InspectorPanel` | project file API |

`StackedLayout` (narrow screens) gained a Milestones tab so the same component is
reachable without the tiling grid.

---

## 3. The milestone pipeline

### Where it sits

```
workspace submit
   → Orchestrator.start_coding_task            task row created
   → _emit(TASK_CREATED)                       ─┐
   → Pi Agent RPC (real runtime)                │ every event passes through
   → normalised events → _emit(...)            ─┤ one gate: persist, publish,
   → _set_status(terminal)                     ─┘ narrate, observe milestone
                                                   │
             ┌─────────────────────────────────────┴───────────────┐
             ▼                                                     ▼
   MilestoneTracker (pure, sync)                     event bus → WS "event"
   derive → word → publish → narrate                        → ActivityPanel
             │
             ├─→ WS "milestone" → MilestonePanel
             ├─→ narration channel → future ElevenLabs
             └─→ <project>/.solo/state/milestones.json
```

Two consumers, one source. The frontend never infers progress from text, and the
voice channel never reads raw activity.

### Evidence rules — what opens a milestone

| Event | Milestone | Notes |
|---|---|---|
| `task.created` | **understanding** | detail = the instruction |
| `progress.summary` with `source=orchestrator` or `plan_id` | **planning** | a real plan exists |
| `file.changed` (first) | **implementing** | detail = the path |
| `file.changed` (later) | — | extends the active milestone's evidence |
| `test.result`, `check.result` (first) | **verifying** | |
| `test.result`, `check.result` (later) | — | updates the active detail |
| `error` (first) | **blocked / failed** | |
| `error` (repeated) | — | extends evidence, does not duplicate |
| terminal status | **completed / cancelled / blocked** | closes the chain |

Everything else returns `None`. That is the common case by design: a stalled task
produces nothing rather than a reassuring animation.

### The milestone object

```json
{
  "id": "…", "task_id": "…", "project_id": "…",
  "stage": "implementing",
  "title": "Making the changes",
  "status": "active",
  "detail": "First change: calculator.py",
  "evidence": ["file changed: calculator.py"],
  "sequence": 2,
  "created_at": "…", "updated_at": "…",
  "worded_by": "evidence"
}
```

`evidence` is why this structure is safe to speak aloud: every milestone can
explain itself. `worded_by` records whether the prose came from
`orchestrator-model` or from `evidence`, so a claim can always be traced.

`sequence` is globally monotonic, so the UI orders reliably and never re-sorts
unstable input. One active milestone per task; `_open` closes the previous one.

### Ordering guarantees

Three races were found and closed (D-32, D-33, D-34):

1. **The chain closes before the row goes terminal.** `_set_status` reads in one
   session, closes the milestones in another context, then writes the row. A
   client that observes a finished task can never then read a milestone still
   marked "in progress".
2. **A closed chain accepts nothing.** `_closed` is tracked separately from the
   milestone list, because "is this task over" is a different question from
   "what milestones does it have". Trailing events — a final check result, a
   late error — are dropped.
3. **`blocked` is not terminal on reload.** Only `completed`/`cancelled` are
   treated as authoritative when rehydrating, so a mid-run failure the agent
   recovered from does not lock the chain.

### Persistence

`<project>/.solo/state/milestones.json`, written after every transition, read
back by `_hydrate` on the first milestone request for a project. The store is
synchronous file I/O and is called through `asyncio.to_thread`.

### REST

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/milestones` | every milestone held |
| `GET` | `/api/milestones/task/{task_id}` | one task's chain, oldest first (404 if unknown) |
| `GET` | `/api/milestones/state` | the persisted snapshot (`{"version": 1, "milestones": […]}`) |

WebSocket channel: `milestone`. Upserted by id on the frontend, because a
milestone may arrive more than once (created, then updated).

---

## 4. Progressive reveal

`useTypewriter(text, {enabled})` reveals text in 3-character chunks at ~24 ms.

It is **presentation only**, and it is deliberately constrained:

- Only the *current* milestone animates. Anything else is shown in full at once.
- Stage, status and evidence update immediately — nothing waits on the reveal.
- `prefers-reduced-motion: reduce` disables it entirely.
- A changed detail restarts the reveal; a re-render does not.

The structured object in `WorkspaceProvider` is untouched by the animation, so
the voice channel consumes the same data the panel renders.

---

## 5. Files

**Backend** — `app/services/orchestrator_brain.py`, `app/api/orchestrator.py`,
`app/services/milestones.py` *(new)*, `app/api/milestones.py` *(new)*,
`app/services/orchestrator.py`, `app/services/project_store.py`,
`app/container.py`, `app/main.py`.

**Frontend** — `src/panels/MilestonePanel.tsx` *(new)*,
`src/hooks/useTypewriter.ts` *(new)*, `src/components/DockLayout.tsx`,
`src/components/StackedLayout.tsx`, `src/state/WorkspaceProvider.tsx`,
`src/types.ts`, `src/api/client.ts`, `src/styles.css`.

**Tests** — `tests/test_orchestrator_config_flow.py` *(new, 9)*,
`tests/test_milestones.py` *(new, 28)*, `tests/test_pi_runtime.py`,
`src/panels/MilestonePanel.test.tsx` *(new, 9)*,
`src/hooks/useTypewriter.test.ts` *(new, 4)*.

**Scripts** — `scripts/e2e.sh`, `scripts/e2e-live.sh`.

**Docs** — `docs/commit-policy.md` *(new)*, `docs/development.md`, `README.md`,
`PROJECT_SPEC.md`.

## Related

- [Scope 0033](../01-planning/workspace-tiles-and-milestones-0033.md)
- [Defect log 0036](../04-defects/defect-log-0036.md)
- [Testing 0035](../03-testing/e2e-workspace-flow-0035.md)