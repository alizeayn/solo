# Acceptance criteria — 2.6.0

| | |
|---|---|
| **Stage** | Unified conversation, realtime voice, mobile |
| **Date** | 2026-10-13 |

---

## 1. One unified Conversational interface

| Requirement | Status |
|---|---|
| Text input, file upload and Voice Mode in one interface | ✅ `ConversationPanel` owns all three |
| Share conversation history and context | ✅ one backend conversation; one `sendMessage` path |
| Not separate systems | ✅ `VoiceChannel` deleted, `voice` tile and tab removed |
| A spoken turn and a typed correction in the same thread | ✅ asserted by test |
| Narrated updates read as part of the same exchange | ✅ interleaved chronologically |

## 2. Real-time voice interaction

| Requirement | Status |
|---|---|
| Agent speaks and listens in one session | ✅ narration output unchanged; realtime input added |
| Interim feedback while speaking | ✅ partial transcripts shown |
| Ongoing conversation, not one-shot | ✅ VAD commits + steering |
| Not built on guesses | ✅ protocol verified against the live service |

## 3. Correct microphone integration

| Requirement | Status |
|---|---|
| Follow the official documentation | ✅ token auth, handshake parameters, commit strategies |
| Microphone access | ✅ `getUserMedia` with echo cancellation and noise suppression |
| Audio capture and processing | ✅ AudioWorklet → 16 kHz PCM |
| Speech recognition | ✅ Realtime `scribe_v2_realtime` |
| Voice responses | ✅ existing TTS path, unchanged |
| Documentation recorded | ✅ `ElevenLabs Docs/08-realtime-speech-to-text.md` |

## 4. Independent voice input and error handling

| Requirement | Status |
|---|---|
| Voice works even if the Orchestrator or Pi fails | ✅ separate try blocks; mic unaffected |
| Still acknowledges what was said | ✅ narration of the reply; failure text preserved |
| Explains errors clearly | ✅ service error frames, dispatch errors, mic errors, all with reasons |
| A failed turn is not lost | ✅ the text returns to the composer |

## 5. Reduced coupling

| Requirement | Status |
|---|---|
| One component failing does not stop Voice Mode | ✅ asserted by test |
| Failures isolated and reported | ✅ per-tile error boundaries plus per-source messages |
| Realtime unavailable → still usable | ✅ batch fallback, stated in the UI |

## 6. Orchestrator integration

| Requirement | Status |
|---|---|
| Voice and text both processed | ✅ identical endpoints |
| Task context maintained | ✅ per-project conversations; steering notes |
| Decides what reaches Pi Agent | ✅ unchanged and still authoritative |

## 7. Mobile-friendly UX

| Requirement | Status |
|---|---|
| App-like on a phone | ✅ bottom navigation, sticky composer, thumb-sized controls |
| Microphone controls | ✅ 48px voice button with live state |
| Voice-session states | ✅ listening / hearing you / speaking |
| Text input | ✅ 16px to prevent iOS zoom; Enter behaviour per input type |
| File uploads | ✅ in the composer |
| Real-time conversation | ✅ interim text in the transcript |
| Verified on a device | ❌ **not done** — no device or browser automation available |

## Test totals

| Suite | Result |
|---|---|
| Backend | **470 passed** |
| Frontend | **152 passed**, typecheck clean, build succeeded |

## Live verification performed

| Check | Result |
|---|---|
| Single-use token minting | ✅ HTTP 200, real token |
| Realtime WebSocket handshake | ✅ `session_started` with resolved config |
| `input_audio_chunk` frame accepted | ✅ |
| Wrong frame field rejected | ✅ (proves the correct shape was needed) |
| Streaming actual audio | ❌ `quota_exceeded` — account balance is 0 |

## Not satisfied

| Requirement | Status |
|---|---|
| Hearing a realtime transcription end to end | ❌ needs credits |
| Real microphone in a browser | ❌ no browser here |
| Mobile layout on a device | ❌ no device here |

## Honest position

Every step of the requested workflow is implemented and covered by tests,
including the eight behaviours that specifically encode the requirements —
unified transcript, interim text not dispatched, mic surviving a dispatch
failure, and the batch fallback.

What is **not** verified is anything requiring a browser with a microphone or a
funded account. I have confirmed the protocol against the live service, including
the frame naming that would otherwise have failed silently, but I have not heard
this work.
