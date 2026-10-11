# How Solo integrates ElevenLabs

## The shape of the integration

```
   microphone
       │  MediaRecorder → audio blob
       ▼
   POST /api/voice/transcribe          ── ElevenLabs Scribe ──►  text
       │
       ▼
   POST /api/projects/{id}/messages    ── the EXISTING dispatch path ──►
       │
       ▼
   Orchestrator → Pi Agent (RPC) → normalised events
       │
       ▼
   MilestoneTracker  (evidence → phase transition)
       │
       ▼
   NarrationService  (ordering, coalescing, rate limit, barge-in)
       │
       ▼
   ElevenLabsTransport  ── ElevenLabs TTS ──►  MP3
       │
       ▼
   GET /api/voice/audio/{line_id}   ──►  browser plays it
```

The critical property: **speech input and speech output both connect to the
existing pipeline rather than running beside it.** Transcription produces text
that goes to the same endpoint the chat box posts to, so intent classification,
task creation, Pi Agent execution, milestones and persistence are all unchanged.
Speech output attaches at the *transport* seam that `NarrationService` already
defined, so nothing above it changes either.

## Why not the Agents Platform

The ElevenLabs Agents Platform owns the conversation loop: it holds the LLM, the
turn-taking and the tools. Using it would put an ElevenLabs agent in front of
Solo's Orchestrator, and the agent would answer from its own context instead of
from the real task state. Solo's requirement is the opposite — the voice system
must speak what the Orchestrator actually knows, and say when it does not know.

So Solo uses two primitives and keeps the orchestration:

| Need | Capability | Endpoint |
|---|---|---|
| Say something | Text to speech | `POST /v1/text-to-speech/{voice_id}/stream` |
| Understand the user | Speech to text | `POST /v1/speech-to-text` |
| Know what it may say | Models | `GET /v1/models` |
| Choose a voice | Voices | `GET /v2/voices` |
| Validate the key | User | `GET /v1/user` |

## What the transport does

`ElevenLabsTransport` implements the `NarrationTransport` protocol that already
existed:

- `deliver(line)` — synthesises the line with the configured voice and model,
  keeps the MP3 in a bounded in-memory store keyed by the line id, and marks the
  line as having audio.
- `stop()` — cancels in-flight synthesis. This is the barge-in path the
  `/api/voice/interrupt` endpoint already calls.

If synthesis fails for any reason, the line is still recorded and still shown in
the UI; only the audio is missing. Narration is never lost because audio failed.

## Grounding: what the voice may claim

The voice never invents progress, and this is enforced structurally rather than
by asking a prompt nicely:

1. It speaks **milestones**, which the tracker only produces from real events.
   Tool calls are never spoken.
2. It speaks from the milestone's `detail`, which is worded by the Orchestrator
   model only *after* the evidence justified the transition.
3. When there is no evidence, there is no milestone, and so nothing is said.
4. Every spoken line keeps its `task_id`, so a question can be answered from the
   task's actual state.

## Known limitations in this phase

- **Turn-taking is push-to-talk, not full duplex.** The browser records an
  utterance and posts it; there is no always-on voice activity detection. This is
  enough for "speak a task, hear progress" and avoids a socket lifecycle that
  would be premature.
- **`scribe_v2_realtime` is not used.** Batch transcription has higher latency to
  first word. Recorded as the upgrade path.
- **No streaming playback.** Audio is fetched as one MP3 per line and played to
  completion. Barge-in stops it, but a line cannot resume mid-way.
- **Cost is real.** Every spoken line is billed per character, which is the
  second reason narration is milestone-only.
