# Scope — why the audio was generated and never fetched

| | |
|---|---|
| **Stage** | 2.5.4 — narration delivery, mobile playback, visible degradation |
| **Date** | 2026-10-13 |

## Reported

A new ElevenLabs key, credits being consumed, still no audio in the Workspace, and
the same on a phone running Solo under Termux. Milestones appear, so the voice
pipeline *should* be able to narrate. Also: when the Orchestrator is rate-limited
or otherwise fails, that must be reported rather than silently swallowed.

## What the mobile log proved

| Observation | Value |
|---|---|
| Successful ElevenLabs TTS calls | **24**, all HTTP 200 |
| Requests for `/api/voice/audio/{id}` | **0** |

Audio was being generated and paid for, on the phone as well as the desktop.
The client never asked for it.

## The cause

A narration line is published **twice under one id**: queued (`spoken: false`) and
then delivered (`spoken: true`). The provider merged narration with `appendUnique`,
which **discards any id it has already seen**, so the delivered version never
replaced the queued one. Every line stayed `spoken: false`, and
`useSpeechPlayback` only plays lines that have audio — so it fetched nothing, ever.

The milestone channel in the same handler used an **upsert**, with a comment
noting that a milestone "may arrive more than once (queued, then updated)". The
identical situation was handled correctly for milestones and incorrectly for
narration.

## Principle

A message that updates an earlier message must be merged by id. Appending is only
correct for genuinely new events.

## Related

- [Implementation 0070](../02-implementation/narration-delivery-0070.md)
- [Defect log 0072](../04-defects/defect-log-0072.md)
