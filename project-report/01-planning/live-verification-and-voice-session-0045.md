# Live verification, workspace regression and the voice session

| | |
|---|---|
| **Stage** | Live ElevenLabs verification + workspace repair + voice session redesign |
| **Version** | 2.5.0 |
| **Date** | 2026-10-12 |

## What was asked

1. Review the ElevenLabs integration and test the connection with a **real key**.
2. Investigate and fix a **regression**: Pi Agent, Tasks, Activity, Inspector and
   Milestone panels stopped working.
3. Redesign the voice interaction: **no push-to-talk**. One click opens a session
   that stays open until explicitly ended, with a polished, state-aware animation.
4. Review the workspace tiles and the milestone data the voice consumes.
5. Standardise the ElevenLabs documentation folder and correct it against
   official sources.

## Why the regression and the voice work are one problem

The Voice panel, added in 2.5.0, fetches `/api/voice/state`. That endpoint
resolved the full voice configuration — including a call to ElevenLabs to
discover a voice. The panel fetched it **on every narration line**.

So a Voice panel that could not reach ElevenLabs did not merely fail to speak: it
put a blocking third-party request behind every agent event, on the same origin
as every other panel. The workspace's other tiles are not broken in themselves;
they stop updating because their requests queue behind the voice panel's.

There was a second, latent fault: no tile had an error boundary, so an error in
any one panel unmounted the whole workspace.

## Definition of done

1. The real key is verified against the live service, with results recorded.
2. `/api/voice/state` performs no network I/O.
3. No tile can take down another.
4. One click starts a voice session; one click ends it; nothing is held.
5. The animation reflects listening, thinking and speaking.
6. The ElevenLabs documentation is corrected and consistently named.

## Related

- [Implementation 0046](../02-implementation/live-voice-and-session-0046.md)
- [Defect log 0048](../04-defects/defect-log-0048.md)
- [Verification 0049](../05-verification/acceptance-criteria-0049.md)
