# Defect log — live verification and the workspace regression

| | |
|---|---|
| **Stage** | Live verification, regression fix, voice session |
| **Date** | 2026-10-12 |
| **Defects** | D-42 … D-46 |

---

## D-42 — The Voice panel stalled the whole workspace

**Severity** Critical · **Status** Fixed · **Found by** the user's server log

**Symptom.** Pi Agent, Tasks, Activity, Inspector and Milestone panels stopped
updating while the app still loaded.

**Root cause.** `GET /api/voice/state` resolved the full voice configuration,
which calls ElevenLabs to discover a voice when none is saved. The Voice panel
requested that endpoint **on every narration line**, so each agent event queued a
third-party HTTP request (30 s timeout). The browser's per-origin connection limit
was exhausted and every other panel's requests stalled behind them.

**Fix.** `voice_status()` reads only the store; `_state_payload` performs no
network I/O; failed voice lookups are cached; the panel fetches on mount, on
session change and on a 15 s interval.

**Why it looked like a frontend bug.** The backend never errored — it logged
`200 OK` throughout. The failure was *latency*, not failure, which is invisible to
a status-code check and to every test in the suite.

---

## D-43 — One tile could blank the entire workspace

**Severity** High · **Status** Fixed · **Found by** reviewing the panel tree

**Root cause.** Dockview renders every panel into a single React tree and no
boundary existed, so an error in any panel unmounted all of them. This is what
makes a single-panel fault present as "everything is broken", and it removed any
clue about which tile was at fault.

**Fix.** `PanelErrorBoundary` wraps every tile, naming the panel, showing the
error, and offering a retry. Contained by construction rather than by hoping no
panel throws.

---

## D-44 — Every ElevenLabs error was misreported

**Severity** High · **Status** Fixed · **Found by** the live API

**Root cause.** ElevenLabs returns failures as a **nested object**:

```json
{"detail": {"code": "...", "message": "...", "status": "..."}}
```

`_error` handled only a string or a list, so the message was discarded and every
failure became a generic "ElevenLabs rejected the API key" — including paid-plan
errors and permission errors.

**Fix.** `_error` reads the nested form, keeps `code`, and maps
`missing_permissions`, `paid_plan_required`, 401/402/422/429/5xx to messages that
name the real cause. A stub that returned a flat string could never have caught
this; the live service did.

---

## D-45 — A valid scoped key was reported as rejected

**Severity** High · **Status** Fixed · **Found by** the live API

**Root cause.** Validation called `GET /v1/user`, which needs `user_read`. The
supplied key is valid for text-to-speech and speech-to-text but lacks `user_read`,
so Solo reported "rejected" for a working key — sending the user to regenerate a
credential that was never the problem. `voices_read` being absent then made voice
selection impossible as well.

**Fix.** Validate with `list_models()` — a capability the integration needs.
Voice discovery is a convenience, not a prerequisite: a voice id can be set
directly, `needs_voice` is reported distinctly, and the UI explains it.

**Class.** The fourth instance of the same mistake in this project (D-28, D-29,
D-38): a check that depends on something other than what the feature actually
needs.

---

## D-46 — Push-to-talk was the wrong interaction

**Severity** Medium · **Status** Replaced · **Found by** user direction

**Symptom.** Speaking required holding a button, which is a walkie-talkie
interaction and not a conversation.

**Fix.** A session: one click opens the microphone, turns are segmented on
silence, and one click ends it. Capture pauses while Solo speaks, and interrupting
is just talking.

**Note.** This is a design correction rather than a coding error, and it is
recorded here because the previous behaviour was documented as a deliberate
limitation rather than as a defect.

---

## Open

| ID | Issue | Status |
|---|---|---|
| **D-08** | Docker build unverified — no daemon socket access | Open (environment) |
| — | No headless-browser verification of playback or the animation | Accepted |
| — | Silence-based segmentation, not the realtime socket | Documented upgrade path |

## Related

- [Implementation 0046](../02-implementation/live-voice-and-session-0046.md)
- [Verification 0049](../05-verification/acceptance-criteria-0049.md)
