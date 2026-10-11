# Workspace tiles, Orchestrator milestones, and configuration flow — scope

| | |
|---|---|
| **Stage** | Focused update before Phase 3 |
| **Version** | 2.3.0 → 2.4.0 |
| **Date** | 2026-10-11 |
| **Status** | Implemented, tested, verified |

## Why this update exists

Seven problems were reported against the 2.3.0 build. Two of them were
user-visible failures, one was an architectural gap that blocks voice, and the
rest were process gaps. They are addressed together because they share a
foundation: the Orchestrator's structured view of a task.

| # | Reported | Classification |
|---|---|---|
| 1 | **Retrieve Models** fails with "needs an OpenRouter API key" although the key is saved and validates | Bug — configuration flow |
| 2 | No initial tile layout when a project is created or opened | Bug — layout versioning |
| 3 | No state-management flow between Pi Agent and the Orchestrator | Gap — architecture |
| 4 | No real-time milestone updates or progressive reveal | Gap — presentation |
| 5 | End-to-end flow not demonstrated | Gap — verification |
| 6 | Commit policy not written down | Gap — process |
| 7 | Reports not updated | Gap — process |

## The reported bug, restated precisely

> I open Settings → Orchestrator. I click **Retrieve Models**. It says
> `The Orchestrator needs an OpenRouter API key added on the Orchestrator settings first.`
> The key is added and the key test works.

The decisive clue is that the *key test* works while *model retrieval* does not.
Both need the same key, so the difference must be in what each one additionally
requires. Key validation needs only a key. Model listing needs a key **and
nothing else** — you cannot choose a model before you can see the list.

## Hypotheses to check before changing anything

1. Does the model-list endpoint use an accessor that requires more than a key?
2. Do the Settings UI and the endpoint read the same settings source?
3. Does the Orchestrator enabled/disabled toggle actually reach the runtime, or
   is it read from the static environment default?
4. Is the key persisted, and does it survive a restart?
5. Do the frontend and backend disagree about field names or state?
6. Does the restored layout get validated against the panels that exist?

## Scope of the tiles

| Tile | Purpose | Must be real |
|---|---|---|
| **Main Workspace Chat** | Submit tasks, questions, files | Wired to the backend and the real agent |
| **Pi Agent Activity** | What the agent is *doing* | Real RPC events, no fabricated progress |
| **Orchestrator Milestones** | What the work *means* | Derived from evidence, no timers |
| **Voice** | Prepared for ElevenLabs | UI and state interfaces only, honestly labelled |

The last two rows carry the architectural decision for this stage: **activity and
milestones are different questions and must be different streams.** Activity is
the raw record; a milestone is a phase transition justified by evidence.
Conflating them would make the voice channel read tool calls aloud.

## What is explicitly out of scope

- ElevenLabs audio (transport, voices, interruption). Only the consuming
  interface is built.
- Speech input.
- Any milestone derived from a timer, a step count, or the passage of time.
- Redesigning the Orchestrator's planning logic.

## Definition of done

1. A saved key retrieves models without a model already chosen.
2. The enabled toggle and the selected model are honoured by the runtime.
3. Every registered panel appears for an existing user with a stored layout.
4. A real coding task produces an evidence-backed milestone chain that is
   published live, persisted, and exposed over REST.
5. One real task runs end to end through the real Pi Agent, with the result
   verified on disk.
6. A commit policy exists in exactly one place and is referenced from the others.
7. Reports, tests and a push.

## Related

- [Defect log 0036](../04-defects/defect-log-0036.md)
- [Implementation 0034](../02-implementation/orchestrator-config-and-tiles-0034.md)
- [Verification 0037](../05-verification/acceptance-criteria-0037.md)
- [Commit policy](../../docs/commit-policy.md)