# Summary — live voice, workspace regression, voice session

| | |
|---|---|
| **Stage** | Live verification, regression fix, voice session redesign |
| **Version** | 2.5.0 |
| **Date** | 2026-10-12 |

---

## The regression, and why it was invisible

The workspace panels were not broken. They were **starved**.

`GET /api/voice/state` resolved the full voice configuration, including a call to
ElevenLabs to discover a voice. The Voice panel requested it on **every narration
line**. Each agent event therefore queued a third-party request with a 30-second
timeout, on the same origin as every other panel. The browser's connection limit
was reached and the other tiles stopped updating.

The backend logged `200 OK` throughout. The failure was latency, not error, which
is why nothing in the test suite caught it and why it looked like a frontend
problem. It was found in the user's own server log, by noticing a third-party
request sitting immediately before a state request.

The fix is structural: **the state endpoint performs no network I/O.** Resolving a
voice is only needed when Solo actually speaks, which is off the critical path.

## Two things that should not have been possible

* **A single panel could blank the workspace.** Dockview renders every tile into
  one React tree; with no boundary, one error unmounted all of them. Every tile is
  now wrapped, and names itself when it fails.
* **Every ElevenLabs error was misreported.** The API returns
  `{"detail": {...}}`; the client read only strings and lists, so it discarded the
  message and said "rejected the API key" for permission problems, plan limits and
  everything else. A stub that returned a flat string could never have exposed it.

## The live verification

**23 passed, 0 failed, 2 skipped** against the real service, through Solo.

The two most important results are not the probes:

* Solo served **42,258 bytes of real MP3** for a milestone it decided to speak.
* Solo transcribed a real utterance and dispatched it as `START_CODING_TASK`.

That is the whole loop — evidence → milestone → narration → ElevenLabs → audio →
delivery — running on Solo's own pipeline.

**The key is scoped**, and this is stated plainly rather than glossed:
`user_read` and `voices_read` are **not permitted**. Speech works; listing voices
does not; the validation had to stop depending on `user_read` for a key like this
to be usable at all. Free-plan library voices return `402`.

## A documentation error, corrected

`02-models.md` claimed `eleven_turbo_v2_5` does not exist. **The live API returns
it** — a full TTS model with a 40,000-character limit. The claim is corrected in
place and the correction is kept visible, because it is the clearest possible
argument for the design decision it describes: discover models from the account
rather than trusting a list. A hardcoded catalogue would have hidden a real model
and offered one that does not resolve.

## The voice interaction

Push-to-talk is gone. One click opens a session; turns are cut on silence;
listening resumes on its own; one click ends it. The panel shows a live input
meter, an animation that follows listening / thinking / speaking, the transcript of
the last turn, and a distinctly styled control for ending the session.

Two behaviours that make it feel like a conversation rather than a recording:
**interrupting is just talking**, and **capture pauses while Solo speaks**, so the
microphone never transcribes the assistant's own voice back as a new instruction.

## Verification

| Suite | Result |
|---|---|
| Backend | **458 passed** |
| Frontend | **131 passed**, typecheck clean, build succeeded |
| `e2e-voice-live.sh` | **23 passed, 0 failed, 2 skipped** |
| `e2e.sh` | 76 passed |

## Open

| Item | Note |
|---|---|
| No headless-browser verification | Playback and the animation are covered by component tests and by inspection. Still the weakest point in the project. |
| Silence-based segmentation | A lightweight VAD, not `scribe_v2_realtime`. Documented upgrade path. |
| Installed copy | Delivered via `./solo --update`, which also exercises the updater. |
| D-08 | Docker build unverified — no daemon socket access. |

## Related

- [Scope 0045](../01-planning/live-verification-and-voice-session-0045.md)
- [Implementation 0046](../02-implementation/live-voice-and-session-0046.md)
- [Testing 0047](../03-testing/live-voice-and-workspace-0047.md)
- [Defect log 0048](../04-defects/defect-log-0048.md)
- [Verification 0049](../05-verification/acceptance-criteria-0049.md)
