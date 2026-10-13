# Testing — voice pipeline and milestones

| | |
|---|---|
| **Stage** | 2.5.2 |
| **Date** | 2026-10-13 |

## Suites

| Suite | Result |
|---|---|
| Backend | **465 passed** (+2) |
| Frontend | **133 passed** (+2), 17 files |
| Frontend typecheck | clean |
| Frontend build | succeeded |

## The chain, verified against the real account

Every step below ran against the user's own configuration and the live
ElevenLabs service. Real events through a real task:

```
events -> milestones -> narrated lines
  kind=progress   spoken=False  Reading project files
  kind=milestone  spoken=False  The changes are in, so I'm checking they work. Checking the result.
```

A milestone transition produced a natural spoken-form line. `spoken=False`
because the account has no quota — and the line **still reached the user as
text**, which is the property that matters.

## `/api/voice/state`, before and after

| Field | Before | After |
|---|---|---|
| `phase` | `voice-active` | `narration-only` |
| `audio_available` | `true` | `false` |
| `voice_configured` | *(absent)* | `true` |
| `spoken` | `1` (attempted) | `0` (actually spoken) |
| `failed` | *(absent)* | `1` |
| `audio_error` | *(absent)* | real quota message |

The literal error text now travels to the UI:
`This request exceeds your quota of 10000. You have 0 credits remaining, while 24
credits are required for this request.`

## New tests

**Backend**

| Test | Guards |
|---|---|
| `test_a_synthesis_failure_is_reported_rather_than_swallowed` | the transport raises; no phantom audio |
| `test_an_unconfigured_transport_reports_rather_than_faking_success` | narration-only is not "spoken" |
| `test_an_unexpected_transport_error_is_raised_for_the_caller` | a non-ElevenLabs fault cannot pass as success |
| `test_a_failed_synthesis_keeps_the_text_and_reports_the_failure` | the line survives as text, `spoken == 0`, `audio_available is False`, the reason is present |

**Frontend**

| Test | Guards |
|---|---|
| `says voice output is broken when a configured account still fails` | a configured-but-failing account is reported, with the reason and the reassurance that text still works |
| `does not cry wolf when speech is working` | no warning when speech is healthy |

## Not verified

| Gap | Reason |
|---|---|
| Audio actually played from ElevenLabs | The account has **0 credits**; no synthesis can succeed |
| Browser playback of a real MP3 | No browser layer; playback is covered by component tests |
| A spoken milestone heard aloud | Impossible until the account has quota |
