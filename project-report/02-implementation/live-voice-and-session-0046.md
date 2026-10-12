# Implementation — live integration, regression fix, voice session

| | |
|---|---|
| **Stage** | Live verification, workspace repair, voice session |
| **Version** | 2.5.0 |
| **Date** | 2026-10-12 |

---

## 1. The regression: a blocking call on a hot path

**Symptom.** Pi Agent, Tasks, Activity, Inspector and Milestone panels stopped
updating.

**Evidence.** The user's own server log:

```
20:49:27 httpx: GET https://api.elevenlabs.io/v2/voices?page_size=1 "HTTP/1.1 401"
20:49:27 "GET /api/voice/state HTTP/1.1" 200 OK
```

The state request triggers a third-party call. The frontend asked for that state
on **every narration line**:

```ts
useEffect(() => { if (lines.length) void load() }, [lines.length, load])
```

**Root cause.** `_state_payload` called `voice_config()`, which calls
`list_voices()` when no voice id is saved — an HTTP request to ElevenLabs with a
30-second timeout. With a key that cannot list voices (a scoped key), this failed
on every poll. The browser allows ~6 concurrent connections per origin, so
several in-flight state requests were enough to stall the WebSocket and every
other panel's requests. The backend was healthy throughout — it logged no errors —
which is why the failure looked like the frontend.

**Fix.**

1. `settings_service.voice_status()` — returns the configuration **from the store
   only**, never the network. `configured`, `audio_available`, `needs_voice`,
   model, voice id and a *cached* voice name.
2. `_state_payload` uses it and no longer calls `voice_config()` or `voice_name()`.
   Resolving the configuration now happens only where it is needed: when the
   transport actually speaks, off the critical path.
3. Failed voice lookups are cached (`_voice_cache = (now, None)`), so a key that
   cannot list voices is asked once per TTL rather than on every request.
4. The panel fetches state on mount, when the session opens or closes, and on a
   15-second interval — **not** once per narration line.

## 2. One tile can no longer break the workspace

Dockview renders every panel into one React tree, so an uncaught error in any
tile unmounts all of them: the shell stays on screen and every panel goes blank at
once. `PanelErrorBoundary` now wraps every tile via a `bounded()` helper in
`DockLayout`, naming the panel that failed and offering a retry.

## 3. The voice session

Replaces push-to-talk entirely.

| | |
|---|---|
| **Start** | One button; the session stays open |
| **Turns** | Cut on ~1 s of silence by a Web Audio level analysis |
| **Interrupt** | Just talk — Solo stops speaking |
| **End** | One button; the microphone is released |

`useVoiceSession` owns the microphone, the analyser and the segment lifecycle.
A turn is transcribed, handed to the panel, and the next segment starts
automatically, so nothing is pressed between sentences.

Two deliberate behaviours:

* **Capture pauses while Solo speaks.** The microphone would otherwise hear the
  assistant and transcribe it as a new instruction — a feedback loop.
* **Barge-in is by voice, not by button.** Input level is compared against the
  playback state; talking stops the speech.

`VoiceChannel` shows a live input meter (visible proof the microphone is open),
the orb state, a status line for listening/thinking/speaking, the transcript of
the last turn, and a clearly distinct control for ending the session.

## 4. Live integration fixes

Found only by using a real key:

* `_error` now reads the **nested** `{"detail": {...}}` envelope. It previously
  handled only a string or a list, so it discarded the message and reported a
  generic "rejected the API key" for **every** failure.
* Validation no longer uses `/v1/user`. A key can be valid for speech and scoped
  without `user_read`; reporting that as "rejected" sends the user to regenerate
  a working key. Validation now reads the model catalogue.
* A key without `voices_read` can still work: the voice id is read from settings,
  `needs_voice` is reported distinctly, and the UI explains it.
* `402 paid_plan_required` keeps the API's own explanation.

## 5. Documentation

* `elevenlabs-docs/` → **`ElevenLabs Docs/`**, matching `Pi Agent Docs` (there is
  no `Voice Agent Docs` folder in this repository).
* `02-models.md` corrected: `eleven_turbo_v2_5` **does exist**. The earlier claim
  that it did not was wrong, and it is recorded as a correction rather than
  quietly deleted.
* `07-live-verified.md` added: the permission map, plan limits, the error
  envelope, and the TTS→STT round trip, all observed against the live API.
* `docs/voice.md` updated for the session model.

## Files

**Backend** — `app/services/settings_service.py` (`voice_status`), `app/api/voice.py`.
**Frontend** — `hooks/useVoiceSession.ts` *(new)*, `components/PanelErrorBoundary.tsx`
*(new)*, `components/VoiceChannel.tsx`, `components/DockLayout.tsx`, `types.ts`,
`styles.css`. `hooks/useVoiceInput.ts` deleted — superseded by the session.
**Scripts** — `scripts/e2e-voice-live.sh` *(new)*.
**Docs** — `ElevenLabs Docs/` (renamed, corrected, extended), `docs/voice.md`.
