# Summary — 2.6.0

| | |
|---|---|
| **Stage** | Unified conversation, realtime voice, mobile |
| **Version** | 2.6.0 |
| **Date** | 2026-10-13 |

---

## Three surfaces were pretending to be one conversation

`Conversation`, `Voice` and `Write` were separate panels — and three separate tabs
on a phone. But a sentence spoken in one and a correction typed in another **are
the same conversation**, and the backend always treated them that way. The split
made the user remember which surface held the context.

`ConversationPanel` now owns the transcript, the voice control, the attach button
and the speech toggle. Typed messages and spoken narration are interleaved
chronologically, so the exchange reads as one thing. `VoiceChannel` was deleted
rather than left orphaned, and the Dockview layout key was bumped so a saved
layout cannot reference a panel that no longer exists.

## Voice was never realtime

`useVoiceSession` recorded a segment, cut it on a second of local silence, and
posted it for batch transcription. Nothing appeared while you spoke — which is
precisely why it did not feel like a conversation.

`useRealtimeVoice` streams to ElevenLabs Realtime and shows interim text as it
arrives. Only a `committed_transcript` is dispatched: partials change, and acting
on one builds tasks out of half-sentences. The batch path remains, and is still
reachable — `POST /api/voice/stt-token` returns `available: false` *with a reason*
rather than failing, so the UI falls back and explains itself.

## The documentation would have broken it silently

The API reference names frames in camelCase (`inputAudioChunk`). The live protocol
uses **`message_type`** with snake_case values, both directions. Sending `type`
returns

```json
{"message_type":"input_error","error":"Message must be a valid protocol message"}
```

and the session then does nothing at all — socket connected, microphone open, no
error to chase, and a failure indistinguishable from "voice does not work".
Implementing from the docs alone would have produced exactly the symptom being
debugged. It was caught by connecting to the real service, and it is now pinned by
a test asserting the exact frame shape and recorded in
`ElevenLabs Docs/08-realtime-speech-to-text.md`.

## The microphone survives the rest of the system

Transcription and dispatch are now separate failure paths. A failed dispatch keeps
the turn — the text returns to the composer — and says what broke. If the
Orchestrator or Pi Agent is down you can still speak, be heard, and be told why
the thing you asked for cannot proceed. That was an explicit requirement and it is
asserted by test.

## Mobile

It was the desktop layout, shrunk: one layout media query (auth only), zero phone
breakpoints, zero safe-area rules, and tab pills at roughly half the minimum
comfortable touch target. Now: 44px targets, 16px inputs (below which iOS Safari
zooms the page), safe-area insets, a sticky composer that survives the keyboard, a
bottom tab bar, and `:active` feedback where hover does not exist.

## Verification

| Suite | Result |
|---|---|
| Backend | **470 passed** (+2) |
| Frontend | **152 passed**, typecheck clean, build succeeded |
| Live: token minting | ✅ real `sutkn_…` token |
| Live: WebSocket handshake | ✅ `session_started` with resolved config |
| Live: audio frame | ✅ accepted with `message_type`; rejected with `type` |

## What I did not verify, and will not claim

**I have not heard this work.** The account is `used 10000 / limit 10000`, so
streaming returns `quota_exceeded`, and there is no browser, microphone or phone
in this environment. The protocol is verified against the live service and the
behaviour is covered by 21 new tests — but mobile layout on a real device,
iOS Safari's microphone policy, and an actual spoken round trip remain untested.

The one thing that most needs a device check is the microphone on a phone: over
`http://<lan-ip>` browsers refuse it outright, because it requires a secure
origin. `./solo.sh cert` provides one.

## Related

- [Scope 0081](../01-planning/unified-voice-conversation-0081.md)
- [Implementation 0082](../02-implementation/unified-voice-conversation-0082.md)
- [Testing 0083](../03-testing/unified-voice-conversation-0083.md)
- [Defect log 0084](../04-defects/defect-log-0084.md)
- [Verification 0085](../05-verification/acceptance-criteria-0085.md)
