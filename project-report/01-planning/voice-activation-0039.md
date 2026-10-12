# Voice activation — scope

| | |
|---|---|
| **Stage** | Voice activation (Phase 3 of the product roadmap) |
| **Version** | 2.4.0 → 2.5.0 |
| **Date** | 2026-10-11 |
| **Status** | Implemented, tested, verified |

## The goal, restated plainly

Speak a task to Solo, have Pi Agent execute it, and hear useful, context-aware
spoken updates — with the existing Orchestrator, Pi Agent and milestone pipeline
preserved.

This is explicitly **not** "add speech-to-text and text-to-speech to the chat".
The requirement is a conversational foundation: speech in feeds the real task
path, and speech out speaks only what the Orchestrator actually knows.

## What was already in place

Phase 2.3 built `NarrationService` — selection, ordering, coalescing, rate
limiting and barge-in — with a `RecordingTransport` standing in for audio. That
decision is what made this phase small: the *policy* of what is worth saying
already existed and was tested, so this stage only had to attach a transport.

Phase 2.4 established milestones as the structured unit the voice channel
consumes, so the voice never reads raw agent activity.

## What this stage adds

| Area | Deliverable |
|---|---|
| Speech out | An `ElevenLabsTransport` implementing the existing `NarrationTransport` protocol |
| Speech in | Browser recording → backend transcription → the **existing** message endpoint |
| Configuration | A real Voice settings pane: key, validation, model discovery, voice discovery |
| Model selection | Live discovery from the account, split by capability |
| Documentation | Verified ElevenLabs API notes in `ElevenLabs Docs/` |

## The decision that shapes everything: no Agents Platform

ElevenLabs' Agents Platform owns the conversation loop — the language model, the
turn-taking, the tools. Using it would place an ElevenLabs agent in front of
Solo's Orchestrator, and that agent would answer from its own context rather than
from real task state.

Solo's requirement is the opposite: the voice must say what the Orchestrator
knows, and say when it does not know. So only two primitives are used:

| Need | Capability |
|---|---|
| Say something | Text to speech |
| Understand the user | Speech to text |
| Know what may be said | Models + voices (discovery) |
| Validate the key | Account |

Consequence recorded deliberately: `elevenlabs_agent_id` is no longer required,
and the old validation flow that demanded it was removed.

## Questions to answer before writing code

1. Does the ElevenLabs API use `xi-api-key` or a Bearer token?
2. Which model ids actually exist — `eleven_v4_conversational`? `eleven_turbo_v2_5`?
3. Is model discovery account-specific, or must a catalog be hardcoded?
4. How should a long milestone be spoken if it exceeds a model's character limit?
5. Where does speech output attach so nothing above it changes?
6. How does speech input avoid becoming a parallel dispatch path?

Answers are in [Implementation 0040](../02-implementation/elevenlabs-voice-0040.md)
and the verified notes in [`ElevenLabs Docs/`](../../ElevenLabs%20Docs/).

## Definition of done

1. A saved key can be validated and models retrieved.
2. The selected model and voice reach the **runtime**, not just the UI.
3. Speaking a task produces a task in the existing pipeline.
4. Milestones are spoken, tool calls are not.
5. Barge-in stops speech.
6. Losing audio never loses information.
7. The whole loop is covered by a test that fakes only the network.

## Related

- [Implementation 0040](../02-implementation/elevenlabs-voice-0040.md)
- [Defect log 0042](../04-defects/defect-log-0042.md)
- [Verification 0043](../05-verification/acceptance-criteria-0043.md)
- [`ElevenLabs Docs/`](../../ElevenLabs%20Docs/) — verified API notes
- [`docs/voice.md`](../../docs/voice.md) — the integration reference
