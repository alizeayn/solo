# Testing — audible narration

| | |
|---|---|
| **Stage** | 2.5.3 |
| **Date** | 2026-10-13 |

## Suites

| Suite | Result |
|---|---|
| Frontend | **139 passed** (133 + 6 new), 18 files |
| Frontend typecheck | clean |
| Frontend build | succeeded |
| Backend | unchanged this round |

## The new test file

`useSpeechPlayback` had **no test at all**, and the shipped defect was exactly the
kind a test would have caught. Six tests now cover it:

| Test | Guards |
|---|---|
| `is on by default, because that is what configuring a voice means` | the regression itself |
| `fetches and plays the audio for a spoken line` | the audio URL is actually requested |
| `never fetches audio for a line that was not spoken` | no audio, no fetch |
| `reports a blocked queue and resumes on the next interaction` | the autoplay refusal is recovered, not swallowed |
| `persists the preference so a reload keeps the choice` | `localStorage` round trip |
| `does not replay a line that already played` | no duplicate playback on re-render |

The blocked-queue test is the important one: it fails if a refused line is marked
seen, which is precisely how narration could go permanently silent after a single
autoplay refusal.

## Verification of the provider side

The usage log is the strongest evidence and it came from ElevenLabs, not from us:

```
82 requests, all HTTP 200
13 x POST /v1/text-to-speech/hpp4J3VqNfWAUOO0d1Us/stream  -> 200
```

Audio was genuinely produced. Solo's log showed `/api/voice/audio` requested
**0 times**, which located the defect on the client side of the seam.

## Reproducing the drops

32 WebSocket closes were classified against the log: 30 followed a server restart
or a page load, 2 did not. The churn was therefore mostly self-inflicted, and the
fix is not "reconnect harder" but "recover what was missed", which is now tested
by construction rather than by a unit test.

## Not verified

| Gap | Reason |
|---|---|
| Hearing a milestone spoken end-to-end | The stored key reports **0 credits remaining**, so synthesis cannot succeed. The live suite reached `phase: voice-active` and then failed every synthesis with `quota_exceeded`. |
| Browser playback of a real MP3 | No browser layer; covered by the hook tests and by inspection. |
