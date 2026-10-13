# Scope — one conversation, real-time voice, mobile

| | |
|---|---|
| **Stage** | 2.6.0 — unified conversation surface, realtime voice, mobile |
| **Date** | 2026-10-13 |

## Requested

1. **One unified Conversational interface.** Text, file upload and Voice Mode in
   the same place, sharing history and context — not two systems.
2. **Real-time voice.** Speak and be spoken to naturally, like a conversation.
3. **Correct microphone integration**, following the official ElevenLabs docs.
4. **Independent voice input.** The mic keeps working when the Orchestrator or Pi
   Agent fails, and the failure is explained rather than swallowed.
5. **Reduced coupling.** One component failing must not take Voice Mode down.
6. **Orchestrator integration** for both voice and text.
7. **Mobile-friendly UX**, app-like on a phone.

## What was actually wrong

| Finding | Evidence |
|---|---|
| Three surfaces, one conversation | `Conversation`, `Voice` and `Write` were separate panels **and** separate mobile tabs; uploads lived in `Write` |
| Voice was not realtime | `useVoiceSession` = MediaRecorder + local RMS silence cut → batch `/transcribe`; no interim text at all |
| Errors were coupled | one `try` wrapped transcribe **and** dispatch, so an agent failure surfaced on the voice path |
| Mobile was unbuilt | **1** layout media query (auth only), **0** phone breakpoints, **0** safe-area rules, **0** touch targets ≥44px |

## The principle

A sentence spoken in one panel and a correction typed in another **are the same
conversation**. Presenting them as separate places forces the user to remember
which one holds the context. The fix is structural, not cosmetic.

## Related

- [Implementation 0082](../02-implementation/unified-voice-conversation-0082.md)
- [Defect log 0084](../04-defects/defect-log-0084.md)
