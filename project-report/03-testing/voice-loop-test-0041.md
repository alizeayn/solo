# Testing — the voice loop

| | |
|---|---|
| **Stage** | Voice activation |
| **Version** | 2.5.0 |
| **Date** | 2026-10-11 |

---

## 1. Suites

| Suite | Result |
|---|---|
| Backend (pytest) | **456 passed** (446 → +10 net) |
| Frontend (vitest) | **132 passed** (132 → +16) |
| Frontend typecheck | clean |
| `scripts/e2e.sh` | **76 passed, 0 failed** (63 → +13) |

---

## 2. `tests/test_elevenlabs.py` — 28 tests

Only the network is faked, and the stub is **routed by URL** rather than
returning one canned response, because a stub that accepts anything cannot catch
a wrong header, path or body.

### Request shape

These would all be silent failures against the real service:

| Test | Property |
|---|---|
| `xi-api-key`, not Bearer | The documented header; a Bearer token is a silent 401 |
| Synthesis posts to `/text-to-speech/{voice_id}/stream` | Correct path and the `output_format` default |
| Transcription is multipart with `model_id` | Correct content type and field |

### Errors name the real cause

A rejected key says *rejected*; a 422 says *invalid* with the API's message; 429
says *rate limit*; a network failure says *could not reach*; and the key never
appears in any of them. An empty recording is refused **without making a
request**, asserted by checking the stub was never called.

### Discovery parsing

Speech models sort before recognition-only ones; capability fields are read;
a model with no id is skipped rather than crashing.

### Chunking

Short text is one chunk; long text splits on sentences with no word broken or
lost; a single over-long sentence is still split; whitespace produces nothing.

### The transport

Without configuration it records and reports `audio_available: false` while
still keeping the line. With configuration it synthesises real bytes and serves
them by line id. A synthesis failure keeps the line and loses only the audio. An
unexpected error from the config resolver is contained. Configuration is resolved
per line, not cached. Stop records a barge-in. Audio storage is bounded.

---

## 3. `tests/test_voice_loop.py` — 10 tests

**This is the acceptance test for the phase.** It exercises the exact sequence
the user asked for, and only the network is stubbed: everything between the HTTP
boundary and the synthesised bytes is the production path. A test that stubbed
the transport would prove nothing about the integration.

### The full loop

`test_a_spoken_task_runs_and_the_progress_is_spoken_back`:

| Step | Asserted |
|---|---|
| 1. Save the key | Saved, reported configured, key never in the response |
| 2. Validate | `ok: true`, message states what was *found* |
| 3. Retrieve models | Both models returned, parsed, capability-tagged |
| 4. Select a model and voice | `audio_available: true`, `phase: voice-active` |
| 5. Transcribe an utterance | Real text returned, and **no task created** |
| 6. Dispatch the transcript | Posted to the same endpoint a typed message uses |
| 7. Pi Agent runs | Task reaches `COMPLETED` |
| 8. Milestones derived | `understanding → implementing → completed`, all with evidence |
| 9. Narration selects | Lines produced; every kind is a milestone or outcome, never activity |
| 10. ElevenLabs synthesises | The synthesised text **equals** the spoken lines |
| 11. Audio served back | 200, `audio/*`, and the bytes match that line's text |
| 12. State consistent | `audio_available`, `spoken` count and `voice_id` all agree |

Step 10 is the one that matters most: it proves the voice speaks exactly what the
narration pipeline selected, in the same order, with nothing invented in between.

### The other nine

Discovery without a key names the key. Selecting writes the settings the runtime
reads. Transcription returns text without dispatching. An empty utterance is
refused before any ElevenLabs call. A question is classified as a question.
Audio for an unknown line is 404. Without a key the loop still records every line
and reports `narration-only` — **losing audio must never lose information.**

---

## 4. `VoiceChannel.test.tsx` — 10 tests

The hooks are mocked, so these assert the wiring: a transcript goes to the real
`sendMessage` path; an empty transcript is reported rather than dispatched; a
recording that captured nothing is reported rather than sent as silence; the
microphone is disabled when the browser cannot record; speaking stops before the
microphone opens; the speech toggle only appears when audio is available; an
honest empty state.

## 5. `useVoiceInput.test.ts` — 6 tests

A blocked microphone and a missing microphone produce **different** messages; a
blob is returned and the track released on stop; a too-short tap yields null
rather than silence; an unsupported browser reports `supported: false`; a
previous error clears on the next attempt.

---

## 6. `scripts/e2e.sh` — 13 new assertions

The script runs with **no** ElevenLabs key, so the valuable thing to assert is
not "speech works" but "the app is honest about speech not being configured" —
the failure modes that would make the UI lie:

- state reports no key, no audio, `narration-only`, recording transport;
- defaults for both models are still reported, so the UI can show what *would* be used;
- model discovery is refused with **400 naming the key** (the D-28 shape);
- voice listing likewise;
- an empty recording is refused 400;
- audio for an unknown line is 404;
- saving a selection reaches `/api/settings` — i.e. the runtime reads it.

---

## 7. What is not tested, and why

| Gap | Reason |
|---|---|
| Real ElevenLabs calls | No key is available in this environment. The request shape is asserted instead, which is what a canned response would hide. |
| Browser audio playback | No headless-browser layer exists. Covered by component tests and by hand. |
| Real microphone input | Same. The hook's decisions are unit-tested with a stubbed `MediaRecorder`. |

These are stated rather than glossed over; the first is the reason the request
shape tests exist at all.

## Related

- [Implementation 0040](../02-implementation/elevenlabs-voice-0040.md)
- [Defect log 0042](../04-defects/defect-log-0042.md)
- [Verification 0043](../05-verification/acceptance-criteria-0043.md)
