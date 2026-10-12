# Summary — voice activation

| | |
|---|---|
| **Stage** | Voice activation |
| **Version** | 2.4.0 → 2.5.0 |
| **Date** | 2026-10-11 |
| **Result** | Implemented, tested, documented, pushed |

---

## What was built

The first working voice loop: speak a task, Pi Agent executes it, and Solo speaks
milestones back.

```
   microphone
       │  MediaRecorder → blob
       ▼
   POST /api/voice/transcribe        ElevenLabs Scribe → text
       │
       ▼
   POST /api/projects/{id}/messages  the EXISTING dispatch path
       │
       ▼
   Orchestrator → Pi Agent (RPC) → normalised events
       │
       ▼
   MilestoneTracker                  evidence → phase transition
       │
       ▼
   NarrationService                  ordering, coalescing, rate limit, barge-in
       │
       ▼
   ElevenLabsTransport               ElevenLabs TTS → MP3
       │
       ▼
   GET /api/voice/audio/{line_id}    played by the Voice panel
```

**Why this is an integration and not two features:** speech input produces text
that is posted to the endpoint a typed message already uses, so intent
classification, task creation, Pi Agent execution and milestones are untouched.
Speech output attaches at the transport seam `NarrationService` defined in Phase
2.3, so nothing above it changed. The policy of *what is worth saying* already
existed and was tested; this stage supplied a voice.

## The decision that mattered most

**The ElevenLabs Agents Platform is not used.** It owns the conversation loop and
the language model, which would put an ElevenLabs agent in front of Solo's
Orchestrator and let it answer from its own context instead of from real task
state. Solo's requirement is the opposite — say what the Orchestrator knows, and
say when it does not know.

So only two primitives are used, and the orchestration stays in Solo. The
`elevenlabs_agent_id` field survives in the schema but is no longer required, and
the validation flow that demanded it (D-37) was removed.

## Verified API facts

Checked against the official documentation rather than assumed, and recorded in
full in [`ElevenLabs Docs/`](../../ElevenLabs%20Docs/):

- Authentication is the `xi-api-key` header, **not** a Bearer token.
- `GET /v1/models` returns what **this account** can use — so models are
  discovered, not hardcoded.
- **`eleven_v4_conversational` does not exist** (the realtime v4 model is
  `eleven_v4_turbo`).
- **`eleven_turbo_v2_5` does not exist** (the v2.5 fast model is
  `eleven_flash_v2_5`).

A static catalog would therefore have been wrong in both directions: offering ids
that do not resolve and hiding account-specific ones that do.

## The recurring bug class

Three of the five defects found here are the same mistake:

| Defect | The mistake |
|---|---|
| D-28 (previous stage) | Model listing read the completions accessor |
| D-29 (previous stage) | The enabled toggle read the static env default |
| D-38 | Audio availability read a lazy runtime flag |
| D-40 | The connection test opened a second HTTP path |

The question that finds them all: **does the value the UI shows come from the
same source as the value the runtime acts on?** It is now written into the code
as a comment at each site, because reading it once was not enough.

D-39 is the other lesson: `ElevenLabsTransport` stored audio but never set
`spoken_at`, so with the **real** transport every line claimed it had never been
spoken. A mocked transport would have hidden it. The voice-loop test uses the
real transport with only the HTTP client stubbed — which is why it was caught.

## Verification

| Suite | Result |
|---|---|
| Backend | **456 passed** |
| Frontend | **132 passed**, typecheck clean |
| `e2e.sh` | **76 passed, 0 failed** |

The acceptance test is `test_voice_loop.py`: the full sequence with only the
network faked. Its strongest assertion is that the text sent to ElevenLabs
**equals** the spoken narration lines, in order — proving the voice speaks
exactly what the pipeline selected, with nothing invented in between.

## What is honestly not done

- **No live ElevenLabs call was made.** No key exists in this environment. The
  request shape — header, path, body, content type — is asserted instead, which
  is exactly what a canned response would hide. The integration is verified
  against the documented API, not against the live service. This is the most
  important limitation in this report.
- **No browser audio verification.** Playback is covered by component tests and
  by hand.
- **Turn-taking is push-to-talk.** `scribe_v2_realtime` is the documented upgrade
  path.
- **No streaming playback.** Barge-in stops a line but cannot resume it.
- **D-08 remains open** — Docker build unverified, no daemon socket access.

## Next

1. A live ElevenLabs run with a real key, which would convert the request-shape
   assertions into end-to-end evidence.
2. Streaming recognition for natural turn-taking.
3. A browser-driven layer, which remains the weakest verification point in the
   project.

## Related

- [Scope 0039](../01-planning/voice-activation-0039.md)
- [Implementation 0040](../02-implementation/elevenlabs-voice-0040.md)
- [Testing 0041](../03-testing/voice-loop-test-0041.md)
- [Defect log 0042](../04-defects/defect-log-0042.md)
- [Verification 0043](../05-verification/acceptance-criteria-0043.md)
