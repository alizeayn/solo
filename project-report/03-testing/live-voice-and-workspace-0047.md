# Testing — live voice and workspace

| | |
|---|---|
| **Stage** | Live verification, regression fix, voice session |
| **Version** | 2.5.0 |
| **Date** | 2026-10-12 |

## Results

| Suite | Result |
|---|---|
| Backend (pytest) | **458 passed** |
| Frontend (vitest) | **131 passed** (17 files) |
| Frontend typecheck | clean |
| Frontend production build | succeeded |
| `scripts/e2e-voice-live.sh` (live key, through Solo) | **23 passed, 0 failed, 2 skipped** |
| `scripts/e2e.sh` (simulator) | 76 passed |

The two skips are `/v1/user` and `/v2/voices`, which this key is **not permitted**
to call. They are reported as skips, not failures — and the report explains why.

## Live verification through Solo (`e2e-voice-live.sh`)

The key was supplied at run time via `ELEVENLABS_KEY_FILE` (0600), never on a
command line, never in the repository, never printed.

| Step | Result |
|---|---|
| `GET /v1/models` | 200 — 11 models |
| `GET /v1/user` | 401 `missing_permissions` (skipped) |
| `GET /v2/voices` | 401 `missing_permissions` (skipped) |
| Synthesis | 23,868 bytes of MP3 with `eleven_flash_v2_5` |
| Round trip | transcribed back as `"Solo live voice check"` |
| Key stored in Solo | stored encrypted; **never returned** by the API |
| Solo validation | passed, with the permission note in the detail |
| Solo model retrieval | 11 models from the live account |
| Voice-listing refusal | explains the missing permission, not a bad key |
| Voice state | `configured`, `audio_available`, `phase: voice-active` |
| Task | `COMPLETED` |
| Milestones | `understanding → implementing → verifying → completed` |
| Spoken line | 1 line reached the transport |
| **Audio served by Solo** | **42,258 bytes, valid MP3 (ID3)** |
| Transcription through Solo | `"Solo live voice check"` |
| Spoken instruction | dispatched, intent `START_CODING_TASK` |
| Barge-in | narration yielded; resume worked |

The decisive rows are *audio served by Solo* and *transcription through Solo*:
those are Solo's own pipeline producing and serving real ElevenLabs audio, not a
stubbed client.

## New and changed tests

**Backend** (458, +2): `test_a_scoped_key_is_not_reported_as_rejected` (a key
valid for speech but without `user_read` must not be called rejected),
`test_a_paid_plan_error_keeps_its_explanation` (a 402 must say why).

**Frontend** (131): `VoiceChannel.test.tsx` rewritten for the session contract —
one control starts and does **not** need holding; an open session shows a single
obvious way to end it; thinking and speaking are reflected; starting is disabled
with a reason when unconfigured or unsupported; a turn is transcribed and
dispatched down the normal path; an empty turn is reported and **not** dispatched;
a transcription failure dispatches nothing; a `needs_voice` account is reported
rather than silently doing nothing; capture pauses while Solo speaks; talking
interrupts without pressing anything. `useVoiceInput.test.ts` was deleted with the
hook it covered.

## What is not verified

| Gap | Reason |
|---|---|
| Browser audio playback and the animation | No headless-browser layer; covered by component tests and by inspection |
| Real microphone capture | Same; the session hook is exercised in the browser by hand |
| Live run through the **installed** copy | Separate checkout; the updater path is used to deliver the fix |

## Related

- [Implementation 0046](../02-implementation/live-voice-and-session-0046.md)
- [Defect log 0048](../04-defects/defect-log-0048.md)
