# Summary — 2.5.2

| | |
|---|---|
| **Stage** | ElevenLabs integration and natural milestone narration |
| **Version** | 2.5.2 |
| **Date** | 2026-10-13 |

---

## Voice was silent for one reason, and invisible for four

The account cannot synthesise — every request returns
`401 This request exceeds your quota of 10000. You have 0 credits remaining.`
That is account state, not a Solo bug, and no configuration change fixes it.

What *was* a Solo bug is that nobody could have known. The failure was hidden at
four independent points:

1. The **transport swallowed it** and returned normally, so a line with no audio
   was recorded as delivered.
2. **`audio_available` was an OR** of "configured" and "working", so a
   configured-but-failing account reported `voice-active`.
3. The transport's own flag meant "has delivered once", not "is configured".
4. **Failed lines were counted as spoken**, and the counters contradicted
   `spoken_at`.

Four places, one outcome: a completely dead integration that looked healthy from
every surface. That is the same failure mode as D-42 and D-47 — an error handler
that converts a failure into the appearance of success.

## Milestones had never been sent to the voice channel

`_narrate` accepted only `progress.summary` and `error`. `_observe_milestone`
detected each transition, persisted it and announced none. The feature the user
asked for had no code path at all.

It does now, phrased for speech rather than copied from a log:

> "The changes are in, so I'm checking they work. Checking the result."

Verified end-to-end through a real task: a milestone transition produced that
line. The Orchestrator model may reword a transition — it can never create one —
and deterministic phrasing is the fallback, so a milestone that really happened is
always explained even with no model configured.

## Text is the channel; audio is the enhancement

This is what makes the workspace usable today. With the quota exhausted, the full
milestone narrative still reaches the UI as text. The only difference is that a
spoken line is not attempted successfully. The UI says so plainly:

> **Voice output is not working.** This request exceeds your quota of 10000.
> Progress is still shown here as text, and tasks are unaffected.

Task submission, file upload and the voice channel all read the same event stream,
so they cannot disagree about what a task is doing.

## Verification

| Suite | Result |
|---|---|
| Backend | **465 passed** (+2) |
| Frontend | **133 passed** (+2), typecheck clean, build succeeded |
| Milestone → narration | verified end-to-end against the live account |
| `/api/voice/state` | reports `narration-only`, `audio_available: false`, the real error |

## What cannot be claimed

**No audio can be produced until the account has quota.** I did not hear a
milestone spoken, and I will not report the voice feature as working on the
strength of code paths alone — that is precisely the mistake this release fixes.

## To restore speech

Add ElevenLabs credits, or wait for the free-tier allowance to reset. Solo will
report `voice-active` again automatically once a synthesis succeeds, because
`audio_available` is now derived from real delivery rather than from configuration.

## Related

- [Scope 0057](../01-planning/voice-pipeline-and-natural-milestones-0057.md)
- [Implementation 0058](../02-implementation/voice-pipeline-0058.md)
- [Testing 0059](../03-testing/voice-pipeline-0059.md)
- [Defect log 0060](../04-defects/defect-log-0060.md)
- [Verification 0061](../05-verification/acceptance-criteria-0061.md)
