# Acceptance criteria — Orchestrator configuration, tiles, milestones

| | |
|---|---|
| **Stage** | Focused update before Phase 3 |
| **Version** | 2.4.0 |
| **Date** | 2026-10-11 |
| **Result** | All criteria met except the two carried open items |

---

## 1. The seven reported areas

### 1. OpenRouter model retrieval — **met**

| Criterion | Evidence |
|---|---|
| Configure and validate the key | `/api/orchestrator/test` returns `verified` after a real completion |
| Retrieve models with a key saved and no model chosen | `scripts/e2e.sh`: **458 models retrieved** |
| Select a model and have it reach the runtime | `/api/orchestrator/status` reports the selected model; `is_enabled()` honours the toggle |
| Both read one configuration source | Settings and the endpoint read `settings_service`; asserted in `test_orchestrator_config_flow.py` |
| Key survives a restart | Second `create_app` on the same data dir sees `has_key` |
| Key never returned | The raw key appears in no response; asserted in unit and e2e tests |
| The fix is not a bypass | The endpoint really calls OpenRouter; the stub counts calls |

**Honest limitation.** Completions require credit on the OpenRouter account. The
e2e used `openrouter`/`openai/gpt-4o-mini`, which completed successfully. Model
*listing* is free and was verified against the live service.

### 2. Workspace tiling layout — **met**

Every registered panel is present after load, whether the layout was restored or
built from defaults (D-30). Four tiles: Main Workspace Chat (real dispatch),
Pi Agent Activity (real RPC events), Orchestrator Milestones (evidence-derived),
Voice (UI and state interfaces only, labelled as such).

**Correction.** The library is **Dockview** (`dockview-react`), not "DarkView".
Themes `themeAbyss` / `themeLight`.

### 3. State-management foundation — **met**

One gate (`_emit`) → derive → word → publish → narrate → persist. Activity and
milestones are separate channels. No orchestration logic in the frontend: it
renders structured objects and never infers progress from text. Task identity,
ordering, terminal transitions and errors are covered by D-32…D-35 regressions.

### 4. Real-time updates and typing animations — **met**

Milestones are published per transition. `useTypewriter` reveals only the current
milestone, is disabled under reduced motion, and never delays a result — stage,
status and evidence update immediately. The structured state is untouched by the
animation, so voice consumes the same data.

### 5. End-to-end functional test — **met**

Real Pi Agent, real OpenRouter model, real file on disk: **42 passed, 0 failed**.
The 10-step sequence is tabulated in [Testing 0035 §4](../03-testing/e2e-workspace-flow-0035.md).
The chain was `understanding → implementing → completed` and the file written by
the agent was read back from disk and quoted.

### 6. Commit policy — **met**

`docs/commit-policy.md` is canonical; `README.md`, `docs/development.md` and
`PROJECT_SPEC.md` link to it and do not restate it.

### 7. Documentation and delivery — **met**

Reports 0033–0038; commits per the new policy; push to `main`.

---

## 2. Anti-fabrication criteria

These are the criteria that keep the milestone tile honest, so they are stated
explicitly.

| Criterion | How it is guaranteed |
|---|---|
| No milestone from a timer | `MilestoneTracker` has no clock; `observe()` only reacts to events |
| No fabricated milestones | Unrelated events return `None`; asserted for five event types |
| The model cannot invent progress | `describe_milestone` is only reachable after a transition the tracker justified; a test asserts it is never called for noise |
| Every milestone explains itself | `evidence` is non-empty for every milestone; asserted in unit, e2e and live tests |
| The UI does not infer progress | The frontend renders `stage`/`status`/`evidence`; there is no parsing of message text |
| A stalled task produces nothing | Silence is the default; the empty state says so |

---

## 3. Test totals

| Suite | Count | Result |
|---|---|---|
| Backend | 411 | pass |
| Frontend | 116 | pass |
| `e2e.sh` | 63 | pass |
| `e2e-live.sh` | 42 | pass |
| **Total** | **632** | **0 failed, 0 skipped** |

---

## 4. Verification commands

```bash
cd backend && ../venv/bin/python -m pytest          # 411 passed
cd frontend && npx vitest run && npx tsc --noEmit   # 116 passed, clean
./scripts/e2e.sh                                     # 63 passed
PI_TEST_PROVIDER=openrouter PI_TEST_MODEL=openai/gpt-4o-mini \
  ./scripts/e2e-live.sh                              # 42 passed
```

---

## 5. Carried open items

| Item | Reason |
|---|---|
| Docker image build (D-08) | No daemon socket access; user not in `docker` group |
| No browser-driven visual tests | No Playwright layer yet — the acknowledged weakest verification point |
| No audio transport | Deliberately Phase 4; only the consuming interface is built |
| Milestone wording falls back to evidence without credit | Environment, not code; the pipeline is identical in shape either way |

## Related

- [Scope 0033](../01-planning/workspace-tiles-and-milestones-0033.md)
- [Defect log 0036](../04-defects/defect-log-0036.md)
- [Summary 0038](../06-summary/summary-0038.md)