# Defect log — 2.5.3

| | |
|---|---|
| **Stage** | Narration playback and stream recovery |
| **Date** | 2026-10-13 |
| **Defects** | D-55 … D-58 |

---

## D-55 — Nothing was audible because playback defaulted to off

**Severity** Critical · **Status** Fixed

**Symptom.** Credits consumed, no audio heard, Voice component "not working".

**Evidence.** The provider log shows 13 successful TTS calls (HTTP 200). Solo's
log shows `/api/voice/audio` requested **zero** times. The server synthesised and
stored audio the client never asked for.

**Root cause.** `useSpeechPlayback` initialised `enabled = false`, exposed only as
a small `🔇 Voice off` toggle. The user had configured a voice and reasonably
expected to hear it.

**Fix.** On by default, persisted; the autoplay case is recovered on the first
user gesture and shown as `tap anywhere to enable sound`.

**Class.** The same shape as D-42, D-47 and D-51 — a system that reports itself
healthy while doing nothing the user asked for. Here the "report" was a default
that quietly declined the work.

---

## D-56 — The audio element was created after the code that needed it

**Severity** High (latent) · **Status** Fixed

**Root cause.** `new Audio()` was constructed in a `useEffect` declared *after*
the effect that queues and drains lines. On first render the drain saw
`audioRef.current === null` and skipped the line.

**Why it was invisible.** Playback began disabled, so the element always existed
by the time the user enabled it. Fixing D-55 exposed it immediately — the first
test run failed with `expected '' to be '/api/voice/audio/l1'`.

**Fix.** The element is created on first use.

---

## D-57 — A line refused by autoplay could never be heard

**Severity** High · **Status** Fixed

**Root cause.** The line was marked *seen* before `play()` was attempted, and the
drain loop broke on refusal. After one autoplay refusal, the lines explaining what
the agent was doing were permanently unplayable, even once the user clicked.

**Fix.** A refused line stays at the front of the queue and is retried on the next
gesture. Only genuine failures (missing audio) are dropped as seen.

---

## D-58 — Nothing was refetched after a dropped stream

**Severity** Medium · **Status** Fixed

**Symptom.** "The connection keeps dropping when switching between tiles", with
panels left stale until a reload.

**Root cause.** A WebSocket delivers only what happens while it is open. No effect
refetched on reconnect, so every drop cost the user a manual reload.

**Evidence.** Of 32 closes, **30 followed a server restart or a page load** and
only 2 were unexplained — so the drops were largely real but mostly self-inflicted.
The defect was the missing recovery, not the reconnection.

**Fix.** `WorkspaceProvider` refetches tasks, messages and the selected task's
events on reconnect (not on the first connect).

---

## Not a defect: which key is stored

The account reports `used 10000 / limit 10000 / remaining 0` for key `sk_2f98d…`,
yet 13 TTS calls succeeded the same day. One key cannot be both exhausted and
working, so the successful calls used a different key than Solo now holds.
Recorded so this is not mistaken for a code fault.

## Open

| ID | Issue | Status |
|---|---|---|
| — | Stored ElevenLabs key reports 0 credits | Needs a key with balance; see above |
| — | Mobile responsive UI | Open (deferred from 2.5.1) |
| D-49 | Answers presented as completed tasks | Open (deliberate) |
| D-08 | Docker build unverified | Open (environment) |
