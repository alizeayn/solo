# Summary — Orchestrator configuration, workspace tiles, milestones

| | |
|---|---|
| **Stage** | Focused update before Phase 3 |
| **Version** | 2.3.0 → 2.4.0 |
| **Date** | 2026-10-11 |
| **Result** | Implemented, tested, verified, pushed |

---

## What was wrong, and why

Three of the seven reported items were real defects, and all three shared one
cause: **a value the user saved was not the value the code acted on.**

1. **Model retrieval (D-28).** `client()` required a key *and* a model, and model
   *listing* used it. Listing is the step before choosing, so in the normal
   first-run state the endpoint saw `None` and blamed the key. The message named
   the wrong cause, which is why the key test passing was the decisive clue: both
   need the same key, so the difference had to be what each one additionally
   required.

2. **The enable toggle (D-29).** The runtime read
   `self._settings.orchestrator_enabled`, the static environment default, while
   the Settings UI wrote a different store. The toggle was decorative.

3. **Missing tiles (D-30).** The layout was stored under `solo.layout.v1` and the
   key was never bumped. A stored layout containing only still-registered panels
   restored *successfully*, so the code that adds new panels never ran. Nothing
   validated the restored layout against the panel set.

The rest were gaps: no milestone concept anywhere, and two process gaps.

## The architectural decision

**Activity and milestones are different questions and are now different streams.**

| | Pi Agent Activity | Orchestrator Milestones |
|---|---|---|
| Answers | what is the agent *doing* | what does the work *mean* |
| Unit | an event | a phase transition |
| Source | normalised RPC events | evidence the tracker accepted |
| Consumer | ActivityPanel | MilestonePanel **and** the voice channel |

This is what makes the voice channel possible. Reading raw activity aloud would
recite tool calls; reading milestones speaks in phases. The decision was made now,
with a recording transport, so Phase 4 attaches audio without touching the
pipeline.

## The milestone pipeline

```
_emit(...)  ──► MilestoneTracker.observe()   pure, synchronous, no clock
                    │  returns None for almost every event
                    ▼
              MilestoneService              word → publish → narrate → persist
                    ├─► WS channel "milestone"  → MilestonePanel
                    ├─► narration channel       → future ElevenLabs
                    └─► .solo/state/milestones.json
```

Two rules make it trustworthy, and both are asserted:

- **Every milestone is derived from evidence.** `observe()` returns `None` unless a
  real event justifies a transition. There are no timers. A stalled task produces
  nothing rather than a reassuring animation.
- **The model can only reword.** `describe_milestone` receives a transition the
  tracker already accepted. A test asserts it is never called for noise. With no
  credits the deterministic text is used and `worded_by` says `"evidence"`.

## Four ordering races, found and closed

The interesting work was in the *ordering* guarantees, and every one of them was
found by a test rather than by reading the code.

| Race | Fix |
|---|---|
| Endpoints awaited synchronous store I/O (D-32) | `asyncio.to_thread` |
| A trailing event reopened a completed chain (D-33) | `_closed`, checked in `observe()` |
| The row went terminal before the outcome was recorded (D-34) | close the chain, then write the row |
| One failure produced three `blocked` milestones (D-35) | repeated errors extend evidence |

The last two were only visible in a **live** run against a real provider that
failed. The deterministic simulator never produces them. That is the strongest
argument in this report for keeping the live suite: it found a defect no unit test
would have.

## Verification

| Suite | Result |
|---|---|
| Backend | **411 passed** |
| Frontend | **116 passed**, typecheck clean |
| `e2e.sh` (simulator) | **63 passed, 0 failed** |
| `e2e-live.sh` (real Pi, OpenRouter) | **42 passed, 0 failed** |

The live run is the requested scenario, executed for real: a task submitted through
chat, worked by the Pi Agent, `hello_world.py` written to disk with the requested
contents, the chain `understanding → implementing → completed`, and the final state
consistent across disk, memory and the API.

Two live attempts were made and both are reported. The first used `opencode-go`,
which returned `403 — an active OpenCode Go subscription is required`; the task
correctly failed and **found D-35 and D-36**. The second used
`openrouter/openai/gpt-4o-mini` and passed fully. Reporting only the second would
have been dishonest, and would have hidden the defects the first exposed.

## Honest limitations

- **No browser-driven verification.** There is no Playwright layer, so the tile
  layout and the reveal animation are verified by component tests and by hand, not
  by a real browser. This remains the weakest verification point.
- **No audio.** `audio_available: false`. The narration pipeline, priorities,
  coalescing and barge-in exist and are tested; only the transport is missing.
- **Milestone wording needs OpenRouter credit.** Without it the deterministic
  wording is used. The shape of the pipeline is identical either way, which is why
  this is a limitation rather than a defect.
- **Docker build still unverified (D-08).** No daemon socket access in this
  environment.

## Process

`docs/commit-policy.md` is now the canonical commit policy, referenced from
`README.md`, `docs/development.md` and `PROJECT_SPEC.md` and not duplicated. It is
operational: it prescribes grouping by functional boundary, reviewing the staged
diff, checking for secrets and generated files, running the relevant tests and
recording the verification, and never rewriting shared history.

This stage was itself committed under that policy — nine commits, split by intent
rather than by stage.

## Open items

| Item | Where |
|---|---|
| Docker image build unverified (D-08) | [36](04-defects/defect-log-0036.md) |
| No browser-driven tests | [37 §5](05-verification/acceptance-criteria-0037.md) |
| Audio transport (Phase 4) | [34 §4](02-implementation/orchestrator-config-and-tiles-0034.md) |
| Version-range compatibility gate in the updater | [26 §6](05-verification/acceptance-criteria-0026.md) |

## Related

- [Scope 0033](01-planning/workspace-tiles-and-milestones-0033.md)
- [Implementation 0034](02-implementation/orchestrator-config-and-tiles-0034.md)
- [Testing 0035](03-testing/e2e-workspace-flow-0035.md)
- [Defect log 0036](04-defects/defect-log-0036.md)
- [Verification 0037](05-verification/acceptance-criteria-0037.md)