# Defect log — 2.5.2

| | |
|---|---|
| **Stage** | ElevenLabs integration and spoken milestones |
| **Date** | 2026-10-13 |
| **Defects** | D-51 … D-54 |

---

## D-51 — The voice transport swallowed every synthesis failure

**Severity** Critical · **Status** Fixed

**Symptom.** No voice, and nothing anywhere said so.

**Root cause.** `ElevenLabsTransport.deliver()` caught `ElevenLabsError`, logged it
at `INFO`, and returned normally. Narration therefore recorded a line with no
audio as **delivered**. Success and failure were indistinguishable to every
caller.

**Fix.** The transport raises; the "a task must never break" guarantee it was
protecting already lives in `narration._run`, which catches everything. The line
is still kept as text and the reason is now recorded and published.

**Class.** The same mistake as D-42 and D-47: an error handler that makes a
failure look like success.

---

## D-52 — `audio_available` was an OR of two disagreeing sources

**Severity** High · **Status** Fixed

**Root cause.** `voice_status()` reports *configured*; narration reports
*working*. `_state_payload` OR-ed them, so a configured account reported
`phase: voice-active` while every synthesis returned 401.

**Fix.** `audio_available = voice_configured and audio_error is None`, with
`voice_configured` exposed separately so the UI can tell "not set up" from
"set up but failing".

---

## D-53 — Milestones were never sent to the voice channel

**Severity** High · **Status** Fixed

**Symptom.** The user's core request: milestones are generated during a task but
never explained aloud.

**Root cause.** `_narrate` forwarded only `progress.summary` and `error`.
`_observe_milestone` detected and persisted every transition and announced none.

**Fix.** `_narrate_milestone` speaks each transition, phrased for speech, with the
Orchestrator model permitted to reword and deterministic phrasing as the fallback.

---

## D-54 — Failed deliveries were counted as spoken

**Severity** Medium · **Status** Fixed

**Root cause.** `_run` published `spoken=True` unconditionally, and `state()`
reported `spoken = len(self._history)` — lines *attempted*. The panel showed
progress as spoken while `spoken_at` was never set, so the counters contradicted
each other.

**Fix.** `failures` and `last_error` are tracked; `spoken=delivered` is published;
`spoken` counts only lines with `spoken_at`.

---

## Not a defect: the account has no quota

```
401 This request exceeds your quota of 10000. You have 0 credits remaining.
```

The key is valid and the model correct; the free-tier quota is exhausted. Solo
cannot fix this and does not pretend to. It is recorded here because it is the
reason voice is silent right now, and it must not be mistaken for a bug that a
future patch could resolve.

## Open

| ID | Issue | Status |
|---|---|---|
| — | ElevenLabs quota exhausted (account) | Needs the user to add credits or wait for reset |
| D-08 | Docker build unverified — no daemon access | Open (environment) |
| D-49 | Answers presented as completed tasks | Open (deliberate) |
| — | Mobile responsive UI | Open (deferred from 2.5.1) |
