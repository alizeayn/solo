# Defect log — 2.6.0

| | |
|---|---|
| **Stage** | Unified conversation, realtime voice, mobile |
| **Date** | 2026-10-13 |
| **Defects** | D-66 … D-71 |

---

## D-66 — One conversation was split across three surfaces

**Severity** High · **Status** Fixed

**Symptom.** A spoken turn and a typed correction lived in different panels
(`Conversation`, `Voice`) and file upload in a third (`Write`) — three tabs on
mobile. The user had to remember which surface held the context.

**Root cause.** The split was purely presentational; the backend conversation was
always one. So the fix was structural, not a synchronisation problem.

**Fix.** `ConversationPanel` owns transcript, voice, attachments and speech
output. The `voice` tile and tab were removed, `VoiceChannel` deleted, and the
Dockview layout key bumped `v3 → v4` so saved layouts cannot reference a removed
panel.

---

## D-67 — Voice was batch, so it never felt live

**Severity** High · **Status** Fixed

**Root cause.** `useVoiceSession` recorded a segment, cut it on ~1 s of local
silence, and posted it for batch transcription. Nothing was shown while speaking.

**Fix.** `useRealtimeVoice` streams to ElevenLabs Realtime and renders interim
text as it arrives. Batch remains the fallback.

---

## D-68 — Interim speech was invisible in an empty conversation

**Severity** Medium · **Status** Fixed · **Found by** its own test

**Root cause.** The interim bubble was rendered only inside the non-empty
transcript branch, so the very first thing spoken into a new conversation showed
nothing until it was committed — exactly when reassurance matters most.

**Fix.** The transcript renders when there is either an entry or interim text.

---

## D-69 — Starting a session could hang forever

**Severity** Medium · **Status** Fixed · **Found by** its own test

**Root cause.** `start()` awaited the socket's `open`, `error` or `close` with no
timeout. A connection that did none of those left the panel stuck on
"connecting" with no way back — and the test timed out after 5 s, which is how it
surfaced.

**Fix.** A 10 s connect timeout resolving to a clear error.

---

## D-70 — Mobile was the desktop layout, shrunk

**Severity** High · **Status** Fixed

**Evidence.** One layout media query (auth only); **zero** phone breakpoints,
safe-area rules, `touch-action` or ≥44px targets; `StackedLayout` tabs at
`padding: 6px 12px`, roughly half the minimum comfortable target.

**Fix.** Phone rules at ≤640px: 44px targets, 16px inputs (below which iOS Safari
zooms the page), safe-area insets with `viewport-fit=cover`, sticky composer with
`interactive-widget=resizes-content`, bottom tab bar, and `:active` feedback where
hover does not exist.

---

## D-71 — The documented frame name would have broken the session silently

**Severity** High · **Status** Avoided · **Found by** live testing

**Finding.** The API reference names frames in camelCase (`inputAudioChunk`). The
live protocol uses a `message_type` field with snake_case values in both
directions. Sending `type` yields
`{"message_type":"input_error","error":"Message must be a valid protocol message"}`.

**Why it matters.** The socket stays connected, the microphone is open, and no
transcript ever arrives — a failure that looks exactly like "voice does not work",
with no error to chase. Implementing from the documentation alone would have
produced it.

**Recorded in** `ElevenLabs Docs/08-realtime-speech-to-text.md`, and pinned by a
test asserting the exact frame shape.

---

## Open

| ID | Issue | Status |
|---|---|---|
| — | ElevenLabs balance exhausted; realtime audio unverified by ear | Needs a funded key |
| — | No browser/device verification of mobile layout or microphone | No device available |
| D-49 | Answers presented as completed tasks | Open (deliberate) |
| D-08 | Docker build unverified | Open (environment) |
