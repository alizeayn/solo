# Voice

Solo is voice-native: the conversation is the interface and speech is its primary
output. This document describes how that is wired, what is real today, and what
is deliberately not built.

The verified ElevenLabs API notes live in [`elevenlabs-docs/`](../elevenlabs-docs/)
at the repository root.

---

## The loop

```
   microphone
       │  MediaRecorder → audio blob            (browser)
       ▼
   POST /api/voice/transcribe                   ElevenLabs Scribe → text
       │
       ▼
   POST /api/projects/{id}/messages             the EXISTING dispatch path
       │
       ▼
   Orchestrator → Pi Agent (RPC) → normalised events
       │
       ▼
   MilestoneTracker                             evidence → phase transition
       │
       ▼
   NarrationService                             ordering, coalescing, rate limit
       │
       ▼
   ElevenLabsTransport                          ElevenLabs TTS → MP3
       │
       ▼
   GET /api/voice/audio/{line_id}               played by the Voice panel
```

Two properties make this an integration rather than two features side by side:

* **Speech input feeds the existing path.** The transcript is posted to the same
  endpoint a typed message uses, so intent classification, task creation, Pi
  Agent execution, milestones and persistence are unchanged. Speech is a way to
  *produce text*, not a second way to run a task.
* **Speech output attaches at the transport seam.** `NarrationService` already
  decided what is worth saying, in what order, and when to yield. The ElevenLabs
  transport only turns a line into audio, so nothing above it changed.

---

## Why the Agents Platform is not used

ElevenLabs' Agents Platform owns the conversation loop: it holds the language
model, the turn-taking and the tools. Using it would put an ElevenLabs agent in
front of Solo's Orchestrator, and that agent would answer from its own context
instead of from the real task state.

Solo's requirement is the opposite: the voice must say what the Orchestrator
actually knows, and say when it does not know. So only two primitives are used —
text to speech and speech to text — and the orchestration stays in Solo.

The `elevenlabs_agent_id` field remains in the settings schema from earlier
scaffolding but is **not** required and is not part of the validation flow.

---

## What is spoken, and what is not

Only **milestones** are spoken. Pi Agent may perform thousands of low-level
operations in one task; narrating them would be unintelligible and expensive
(ElevenLabs bills per character).

| Spoken | Not spoken |
|---|---|
| A phase transition the tracker justified from evidence | Tool calls |
| An error | File reads |
| The final outcome | Raw RPC traffic |

The `NarrationService` additionally:

* orders by `(priority, sequence)` so a critical line overtakes progress;
* coalesces: a newer progress line replaces a queued older one, because saying
  "found the module" after "the tests pass" is nonsense;
* rate-limits delivery so speech never runs together;
* yields on barge-in — `/api/voice/interrupt` stops speech and drops
  lower-priority lines;
* never makes information audio-only: every line is published to the UI whether
  or not it was spoken.

---

## Configuration

Settings → Voice.

| Step | What happens |
|---|---|
| Save the API key | Stored encrypted; sent as `xi-api-key`; never returned by any endpoint |
| Test connection | Verifies the key, then fetches the model catalog and the voice list |
| Retrieve models and voices | `GET /v1/models` and `GET /v2/voices` for **this account** |
| Choose a model and voice | Written to the settings the runtime reads |

Models are **discovered**, not hardcoded. A static catalog would offer ids that
do not exist (`eleven_v4_conversational` and `eleven_turbo_v2_5` are both
commonly assumed and both absent) and hide account-specific ones that do.

The model list is split by capability: only models with `can_do_text_to_speech`
are offered for output, and only the rest for input.

### Defaults

| Setting | Default | Why |
|---|---|---|
| `elevenlabs_model_id` | `eleven_flash_v2_5` | ~75 ms median latency and a 40,000-character limit. Spoken progress that arrives seconds late is worse than speech that sounds slightly less rich. |
| `elevenlabs_stt_model_id` | `scribe_v2` | Highest-accuracy batch recognition. |
| Voice | first on the account | A hardcoded `voice_id` may not exist for a given account, and naming an unknown voice fails at synthesis time rather than at configuration time. |

Configuration is resolved **per line**, so saving a key or choosing a model takes
effect on the next thing Solo says rather than at the next restart.

---

## Failure behaviour

Audio is best-effort; information is not.

| Failure | Result |
|---|---|
| No key configured | The recording transport is used. Lines are shown, not spoken. `audio_available: false` |
| Synthesis fails | The line is kept and shown; only the audio is missing |
| Autoplay blocked | Playback stops quietly; the line stays visible |
| Key rejected | Reported as rejected, with the key never in the message |
| Empty recording | Reported as "no speech detected"; nothing is dispatched |

A task never fails because a voice was unavailable.

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/voice/state` | Transport, audio availability, selection, queue depth |
| `GET` | `/api/voice/history` | Recent lines, newest last |
| `POST` | `/api/voice/interrupt` | Barge-in |
| `POST` | `/api/voice/resume` | Resume after speaking |
| `GET` | `/api/voice/models` | Speech models for the account |
| `GET` | `/api/voice/voices` | Voices for the account |
| `PUT` | `/api/voice/settings` | Save model and voice selection |
| `POST` | `/api/voice/transcribe` | One recorded utterance → text |
| `GET` | `/api/voice/audio/{line_id}` | The synthesised MP3 for one line |

WebSocket channels: `narration` (each line) and `voice` (interrupt/resume).

---

## Limitations

* **Turn-taking is push-to-talk, not full duplex.** The browser records one
  utterance and posts it; there is no always-on voice activity detection. This is
  enough for "speak a task, hear progress" and avoids a socket lifecycle that
  would be premature.
* **`scribe_v2_realtime` is not used.** Batch transcription has higher latency to
  first word. It is the documented upgrade path.
* **No streaming playback.** One MP3 per line, played to completion. Barge-in
  stops it, but a line cannot resume mid-way.
* **Cost is real.** Every spoken line is billed per character — the second reason
  narration is milestone-only.
* **No browser-driven audio test.** Playback is verified by component tests and
  by hand, not by a headless browser.
