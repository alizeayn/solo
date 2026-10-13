# Defect log — 2.5.4

| | |
|---|---|
| **Stage** | Narration delivery, mobile playback, visible degradation |
| **Date** | 2026-10-13 |
| **Defects** | D-59 … D-61 |

---

## D-59 — The delivered narration was thrown away by an id collision

**Severity** Critical · **Status** Fixed

**Symptom.** Credits consumed, audio generated (24 successful TTS calls on the
phone), nothing ever heard. Milestones appeared normally.

**Root cause.** A narration line is published twice under one id — queued
(`spoken: false`), then delivered (`spoken: true`). The provider merged narration
with `appendUnique`, which **returns the list unchanged when the id already
exists**, so the delivered update was discarded. Every line stayed
`spoken: false`, and the player only plays lines that have audio, so it never
requested a single MP3.

**Evidence.** `/api/voice/audio` requested **0** times against **24** successful
synthesis calls in the same window.

**Fix.** `upsertNarration` merges by id, keeping the latest fields. Extracted as a
pure function so the invariant is testable.

**Class.** The same shape as D-42, D-47, D-51 and D-55: the system reports itself
healthy while doing none of the work. Here a single boolean, on the client, behind
a WebSocket, was wrong.

---

## D-60 — Narration spoken during a disconnect was never recovered

**Severity** Medium · **Status** Fixed

**Root cause.** The 2.5.3 resync refetched tasks, messages and events but not
narration, so lines spoken while the socket was down had audio that no client was
ever told about.

**Fix.** The resync also merges `/api/voice/state`'s `recent` lines.

**Why it matters more on mobile.** Backgrounding a phone browser suspends timers
and the socket; returning to the tab is precisely when the gap has to be filled.

---

## D-61 — A rate-limited Orchestrator was invisible in the workspace

**Severity** Medium · **Status** Fixed

**Symptom.** The user saw an Orchestrator that silently did nothing.

**Root cause.** The brain tracked `failure_count` and `last_error` and exposed them
on `/api/orchestrator/status`; only the Settings pane rendered them. The
workspace tile showed nothing, so a fully rate-limited account looked healthy.

**Fix.** `OrchestrationPanel` reports the degradation and the reason. The fallback
to deterministic rules is unchanged — degrading beats blocking — but it is no
longer silent.

---

## Open

| ID | Issue | Status |
|---|---|---|
| — | ElevenLabs account balance is consumed during testing | Needs a key with headroom |
| — | Mobile responsive UI | Open (deferred from 2.5.1) |
| D-49 | Answers presented as completed tasks | Open (deliberate) |
| D-08 | Docker build unverified | Open (environment) |
