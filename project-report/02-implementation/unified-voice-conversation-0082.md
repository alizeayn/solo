# Implementation — unified conversation, realtime voice, mobile

| | |
|---|---|
| **Stage** | 2.6.0 |
| **Date** | 2026-10-13 |

---

## 1. One surface

`ConversationPanel` was rebuilt to own everything:

* the transcript, with **typed messages and spoken narration interleaved
  chronologically** — what Solo said and what you said read as one exchange;
* the **voice control**;
* the **attach** control, moved out of `WritePanel`;
* the **speech output toggle**.

`VoiceChannel` and its test were **deleted** — superseded, not orphaned. The
`voice` tile was removed from `PANEL_SPECS` and the `voice` tab from
`StackedLayout`, and the Dockview layout key moved `v3 → v4` with `v3` added to
the stale-key cleanup, because a saved layout would otherwise reference a panel
id that no longer exists.

Voice and text were already unified on the **backend** — both call `sendMessage`
into the same per-project conversation. The split was purely presentational, so
this needed no data-model change.

## 2. Real-time voice

New `useRealtimeVoice` hook: `getUserMedia` → `AudioWorklet` (down-sampled to
16 kHz PCM) → WebSocket to ElevenLabs, with a **single-use token** minted by Solo
so the API key never reaches the browser.

**The wire protocol was verified against the live service, and the documentation
alone would have been wrong.** The API reference names frames in camelCase
(`inputAudioChunk`); the real protocol uses a `message_type` field with
snake_case values. Sending `type` returns
`{"message_type":"input_error","error":"Message must be a valid protocol message"}`
and the session then does nothing while looking perfectly healthy. See
`ElevenLabs Docs/08-realtime-speech-to-text.md`.

Rules encoded in the hook:

* **dispatch only on `committed_transcript`** — partials change, and acting on one
  creates tasks from half-sentences;
* **render partials as interim text** — visible, never dispatched;
* **report every error `message_type`** (`quota_exceeded`, `auth_error`, …) with
  the service's own wording;
* **batch remains the fallback** — `POST /api/voice/stt-token` returns
  `available: false` *with a reason* rather than failing, so the UI falls back and
  says why.

`POST /api/voice/stt-token` mints the token. Minting consumes no credits; only the
streamed audio does.

## 3. Isolation

Transcription and dispatch are separate `try` blocks. A failed dispatch keeps the
turn: the text returns to the composer and the message names the dispatch failure
specifically. The microphone is never taken down by a downstream failure.

## 4. Mobile

Phone rules in `styles.css` at `≤640px`: 44px minimum targets, 16px inputs (below
that iOS Safari zooms the page), `env(safe-area-inset-*)` with
`viewport-fit=cover`, a sticky composer with `interactive-widget=resizes-content`,
a bottom tab bar (`order: 2`), and `@media (hover: none)` `:active` feedback.
Enter sends on a physical keyboard but inserts a newline on a touch keyboard.

## Files

`frontend/src/panels/ConversationPanel.tsx` (rewritten),
`frontend/src/hooks/useRealtimeVoice.ts` *(new)*,
`frontend/src/api/client.ts`, `frontend/src/components/DockLayout.tsx`,
`frontend/src/components/StackedLayout.tsx`, `frontend/src/styles.css`,
`frontend/index.html`, `backend/app/services/elevenlabs.py`,
`backend/app/api/voice.py`.
