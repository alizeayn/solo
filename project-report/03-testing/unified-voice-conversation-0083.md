# Testing — unified conversation, realtime voice, mobile

| | |
|---|---|
| **Stage** | 2.6.0 |
| **Date** | 2026-10-13 |

## Suites

| Suite | Result |
|---|---|
| Backend | **470 passed** (+2) |
| Frontend | **152 passed**, 20 files |
| Frontend typecheck | clean |
| Frontend build | succeeded |

`VoiceChannel.test.tsx` (17 tests) was deleted with the component it covered and
replaced by `ConversationPanel.test.tsx` (13 tests) plus
`useRealtimeVoice.test.ts` (9 tests).

## Verified against the live service

Token minting and the WebSocket handshake were exercised against the real API —
both are free, which matters because the account has no credits:

```
POST /v1/single-use-token/realtime_scribe  -> 200 {"token":"sutkn_…"}   (len 34)
POST /v1/single-use-token/scribe_realtime  -> 422 (documents the valid enum)
WSS  handshake                             -> {"message_type":"session_started", …}
send {"message_type":"input_audio_chunk","audio_base_64":"…"}  -> accepted
send {"type":"input_audio_chunk", …}       -> input_error "Message must be a valid protocol message"
```

That last line is the finding that would otherwise have produced a session which
connects, looks alive, and never transcribes anything.

## Protocol coverage (`useRealtimeVoice.test.ts`)

| Test | Guards |
|---|---|
| connects with the documented query parameters and a token, not a key | key never in a browser URL |
| shows an interim transcript without dispatching it | the classic realtime bug |
| dispatches on the committed transcript | only stable text becomes a task |
| sends `input_audio_chunk` with `audio_base_64` | the exact shape the service accepts |
| reports a service error frame | `quota_exceeded` surfaces, not silence |
| reports why realtime is unavailable and opens no socket | fallback is reachable |
| surfaces a blocked microphone, mentioning the secure-origin rule | the LAN-over-http trap |
| releases the session when stopped | no orphaned mic or socket |

## Unification and isolation (`ConversationPanel.test.tsx`)

| Test | Guards |
|---|---|
| interleaves spoken narration and typed messages into one transcript | one conversation, chronologically |
| shows a typed correction in the same thread | the exact request in the brief |
| starts a session from one control, nothing held | voice-first |
| offers an obvious way to end it | no trapped session |
| renders the interim transcript without dispatching | live feedback, no side effects |
| falls back to segmented recording when realtime is unavailable | button is never dead |
| **keeps the microphone usable when dispatch fails, and keeps the words** | the isolation requirement |
| reports a transcription failure without dispatching | separate failure sources |
| does not dispatch an empty turn | no phantom tasks |
| attaches a file from the composer | uploads in the conversation |
| speech toggle starts on / reports a blocked browser | playback honesty |

## Not verified

| Gap | Reason |
|---|---|
| Hearing realtime transcription end to end | Account balance is `used 10000 / limit 10000`; streaming returns `quota_exceeded` |
| A real microphone in a browser | No browser or microphone in this environment |
| Mobile layout at 320/375/414 px, keyboard, safe areas | No device or browser automation |
| iOS Safari autoplay and microphone policy | No iOS device |
