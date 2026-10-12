# Implementation — ElevenLabs voice

| | |
|---|---|
| **Stage** | Voice activation |
| **Version** | 2.5.0 |
| **Date** | 2026-10-11 |

---

## 1. The verified API facts

Everything here was read from the official documentation on 2026-10-11 and is
recorded in full in [`ElevenLabs Docs/`](../../ElevenLabs%20Docs/).

| Question | Answer |
|---|---|
| Authentication | Header `xi-api-key: <key>` — **not** a Bearer token |
| Model discovery | `GET /v1/models` returns the models *this account* can use |
| Speech synthesis | `POST /v1/text-to-speech/{voice_id}/stream` |
| Speech recognition | `POST /v1/speech-to-text` (multipart) |
| Voice discovery | `GET /v2/voices` |
| Key validation | `GET /v1/user` |

### Model ids that do **not** exist

Checked deliberately, because the request named them as possibilities:

- **No `eleven_v4_conversational`.** The realtime v4 model is `eleven_v4_turbo`;
  the conversational variant exists only for v3 (`eleven_v3_conversational`).
- **No `eleven_turbo_v2_5`.** The v2.5 fast model is `eleven_flash_v2_5`.

A hardcoded catalog would therefore have been wrong in **both** directions:
offering ids that do not exist and hiding account-specific ones that do. This is
why discovery drives the UI.

### Defaults chosen

| Setting | Default | Why |
|---|---|---|
| `elevenlabs_model_id` | `eleven_flash_v2_5` | ~75 ms median latency, 40,000-character limit. Spoken progress arriving seconds late is worse than speech that sounds slightly less rich. |
| `elevenlabs_stt_model_id` | `scribe_v2` | Highest-accuracy batch recognition |
| Output format | `mp3_44100_128` | No paid tier required; `audio/mpeg` plays everywhere |
| Voice | first on the account | A hardcoded `voice_id` may not exist for an account, and naming an unknown voice fails at synthesis time rather than at configuration time |

---

## 2. Backend: `app/services/elevenlabs.py`

Three pieces, each with one responsibility.

### `ElevenLabsClient` — the API

A thin typed wrapper. The properties that matter are the ones a canned response
would hide:

- Sends `xi-api-key`, not `Authorization`.
- Uses `/stream` rather than the non-streaming endpoint, so first audio arrives
  sooner.
- Splits long text into sentence-bounded chunks below the smallest documented
  limit, so a caller never has to know a model's character limit.
- Distinguishes failures that need different fixes:

| Situation | Reported as |
|---|---|
| 401 / 403 | "ElevenLabs rejected the API key." |
| 422 | "rejected the request as invalid", with the API's own message |
| 429 | "rate limit reached" |
| 5xx | the status code |
| Network failure | "Could not reach ElevenLabs" + the exception type |

The key never appears in an error, and an empty recording is refused *locally*
rather than billed for as silence.

### `ElevenLabsTransport` — the seam

Implements the `NarrationTransport` protocol that already existed. This is the
whole reason the phase was small: `NarrationService` already decided what is
worth saying, in what order, and when to yield. The transport only turns a line
into audio.

Two guarantees:

- **Audio failure never loses the line.** If synthesis fails, the line is still
  recorded and still shown; only the sound is missing. A task never breaks
  because a voice was unavailable.
- **`spoken_at` is set only once audio exists.** `spoken` is what the player uses
  to decide whether there is anything to fetch, so a line whose synthesis failed
  reports `false` rather than sending the player after audio that was never made.

Configuration is resolved **per line**, not cached at startup, so saving a key or
choosing a model takes effect on the next thing Solo says.

`name` and `audio_available` report the *current* mode rather than the intended
one: with no key the transport reports `recording`, and the UI says so.

### `chunk_text` — pure and testable

Sentence-bounded splitting with a hard fallback for a single sentence longer than
the limit. Tested directly, including that no words are lost or broken.

---

## 3. Backend: configuration flow

This is the part the previous stage taught us to get right: *does the value the
UI writes actually reach the thing that acts on it?*

```
Settings → Voice
   │  PUT /api/settings        { elevenlabs_api_key }
   │  PUT /api/voice/settings  { model_id, voice_id, stt_model_id }
   ▼
settings_service
   ├─ get_secret / get_plain            (storage)
   ├─ voice_config()   ─────────────►  ElevenLabsTransport resolves this per line
   └─ voice_name()                       for display only
```

`voice_config()` returns `None` unless there is **both** a key and a usable
voice, and it falls back to the account's first voice rather than a hardcoded id.
`/api/voice/state` asks the *same* method the transport asks, so the UI cannot
report "no audio" while the transport is happily speaking, or vice versa. That
shared-source rule was written into the code as a comment, because it is the
D-28/D-29 class of bug and it happened again here (see D-38).

`test_elevenlabs()` was rewritten. It previously opened its own
`httpx.AsyncClient` and required a Conversational Agent ID. It now uses the same
client everything else uses, verifies the key, and then proves the parts the
integration actually needs are reachable — the model catalog and the voice list.

---

## 4. Backend: the voice endpoints

`app/api/voice.py` was extended from four endpoints to nine.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/voice/state` | Transport, `audio_available`, selection, queue depth, phase |
| `GET` | `/api/voice/history` | Recent lines, newest last |
| `POST` | `/api/voice/interrupt` | Barge-in |
| `POST` | `/api/voice/resume` | Resume after the user stops speaking |
| `GET` | `/api/voice/models` | Speech models the account can use |
| `GET` | `/api/voice/voices` | Voices available to the account |
| `PUT` | `/api/voice/settings` | Save `model_id`, `voice_id`, `stt_model_id` |
| `POST` | `/api/voice/transcribe` | One recorded utterance → text |
| `GET` | `/api/voice/audio/{line_id}` | The synthesised MP3 for one line |

Two design points:

- **`/models` and `/voices` return 400 naming the key** when none is saved —
  never a misleading "missing model". Discovery without a key is the exact shape
  of the bug fixed in D-28, so it is asserted in the e2e script.
- **`/transcribe` does not dispatch.** It returns the transcript and stops. The
  caller posts it to `/api/projects/{id}/messages`, which is the same endpoint a
  typed message uses. Transcription therefore adds a way to *produce text*, not a
  second way to run a task — intent classification, task creation, Pi Agent
  execution and milestones are untouched.

`/audio/{line_id}` returns 404 for an unknown id rather than an empty 200: a line
with no audio is one the transport could not (or was not configured to) speak.

---

## 5. Frontend

### `useVoiceInput` — push-to-talk

Records one utterance with `MediaRecorder`. Deliberately coarser than streaming
recognition, and it says so: no socket lifecycle, no voice-activity detection, no
partial transcripts.

Honest about its limits:

- `supported` is false when the browser cannot record, and the button is
  disabled with the reason rather than looking live.
- Permission failures are named specifically, because "blocked" and "no
  microphone" need different fixes.
- A recording under 350 ms is treated as nothing recorded, not sent as silence.
- The microphone track is always released, including on the error path.

### `useSpeechPlayback` — the output half

Fetches `/api/voice/audio/{line_id}` for each line the transport actually spoke
and plays them sequentially.

- **One at a time**, so it never undoes the backend's ordering.
- **Optional, never exclusive.** A line with no audio is still visible.
- **Barge-in wins**: `stop()` cancels immediately.
- **No autoplay fight.** Playback is opt-in, and a blocked attempt stops quietly
  rather than retrying forever.

It is not coupled to ElevenLabs: it fetches whatever the backend serves, so
swapping the transport changes nothing here.

### `VoiceChannel` — the whole loop in one panel

Press to talk → record → transcribe → `sendMessage` → the normal task path.
It stops speaking before opening the microphone, so Solo never talks over the
person.

The panel never overstates itself. Without a key it says audio is unavailable
rather than showing a dead microphone, and the speech toggle only exists when
audio is genuinely available.

### `VoiceSettings` — a real configuration pane

The old pane asked for a Conversational Agent ID and a voice ID to paste. Neither
is how this works. It was replaced with:

- key entry + save + test;
- **Retrieve models and voices**, which calls the discovery endpoints;
- a speech-model select filtered to `can_tts`;
- a recognition-model select with the complement;
- a voice select from the account, with a preview player.

Models show their capability data — character limit, cost multiplier, alpha
requirement — so the choice is informed rather than arbitrary.

---

## 6. Files

**Backend** — `app/services/elevenlabs.py` *(new, ~640 lines)*,
`app/api/voice.py`, `app/services/settings_service.py`, `app/services/narration.py`,
`app/container.py`, `app/config.py`, `app/domain.py`, `app/schemas.py`.

**Frontend** — `hooks/useVoiceInput.ts` *(new)*,
`hooks/useSpeechPlayback.ts` *(new)*, `components/VoiceChannel.tsx`,
`components/SettingsView.tsx`, `api/client.ts`, `types.ts`, `styles.css`.

**Tests** — `tests/test_elevenlabs.py` *(new, 28)*,
`tests/test_voice_loop.py` *(new, 10)*, `tests/test_services_extra.py`,
`tests/test_account_and_voice.py`,
`components/VoiceChannel.test.tsx` *(new, 10)*,
`hooks/useVoiceInput.test.ts` *(new, 6)*.

**Docs** — `ElevenLabs Docs/` *(new, 7 files)*, `docs/voice.md` *(new)*,
`docs/api.md`, `docs/architecture.md`, `README.md`, `scripts/e2e.sh`.

## Related

- [Scope 0039](../01-planning/voice-activation-0039.md)
- [Testing 0041](../03-testing/voice-loop-test-0041.md)
- [Defect log 0042](../04-defects/defect-log-0042.md)
