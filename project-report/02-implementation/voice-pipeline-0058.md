# Implementation — voice pipeline and natural milestones

| | |
|---|---|
| **Stage** | 2.5.2 |
| **Date** | 2026-10-13 |

---

## 1. The account cannot speak (not a Solo defect)

```
GET/POST api.elevenlabs.io  ->  401
This request exceeds your quota of 10000. You have 0 credits remaining,
while 15 credits are required for this request.
```

Confirmed against three separate voice ids, including two previously verified as
usable on this key. The key is valid and the model `eleven_flash_v2_5` is correct;
the free-tier quota is spent. **No configuration change in Solo can fix this.**
What Solo must do is say so — which it did not.

## 2. Four places where Solo hid the truth

### a. The transport swallowed every failure

```python
except ElevenLabsError as exc:
    logger.info("elevenlabs synthesis failed: %s", exc)
    self._remember(line)
    return          # <- a failure that looks exactly like success
```

`deliver()` absorbed the error and returned normally, so narration recorded the
line as **delivered**. The intent ("keep the line, only the audio is missing") was
right; the effect was that the caller could not tell success from failure.

The transport now **raises**, and returns normally only when audio exists. The
"a task must never break" guarantee has not been dropped — it moved to narration,
which already caught every exception. The failure is now recorded, the line is
kept as text, and the reason is published.

An unconfigured account raises too, with an actionable message, because
returning normally there made text-only progress look spoken as well.

### b. `audio_available` was an OR of two disagreeing sources

```python
state["audio_available"] = bool(
    state.get("audio_available") or container.narration.state().get("audio_available")
)
```

`voice_status()` reports whether Solo is *configured*; narration reports whether
speaking *works*. OR-ing them meant a configured-but-failing account reported
`voice-active`. It now composes the two honestly:

```python
state["audio_available"] = voice_configured and audio_error is None
```

`voice_configured` is kept separate so the UI can distinguish "not set up" from
"set up but failing".

### c. The transport's own flag meant something else

`audio_available` on `ElevenLabsTransport` returns `_configured`, which is only
set *inside* `deliver`. Before the first delivery it is `False` even on a
perfectly good account, and after a *failed* delivery it was `True`. The API no
longer depends on it for availability.

### d. Failed lines were counted as spoken

`_run` published `spoken=True` unconditionally and `spoken` was
`len(self._history)` — the count of lines *attempted*. Narration now tracks
`failures`, records `last_error` (message, text, timestamp), publishes
`spoken=delivered`, and counts only lines whose `spoken_at` is set.

## 3. Milestones now speak

`_observe_milestone` persisted transitions but never announced them, and
`_narrate` accepted only `progress.summary` and `error`.

`_narrate_milestone` now speaks each transition, phrased for speech rather than
copied from a log:

| Stage | Deterministic phrasing |
|---|---|
| `understanding` | "I've read the request and I know what to build." |
| `planning` | "I've worked out the steps I'll take." |
| `implementing` | "I'm making the changes now." |
| `verifying` | "The changes are in, so I'm checking they work." |
| `completed` | "That's finished." |
| `blocked` | "I've hit something I can't get past." |

The Orchestrator model may **reword** these (`describe_milestone`, which accepts
only a transition the evidence already justified) and the deterministic phrasing
is the fallback — so a real milestone is always explained, even with no model
configured. Priority follows meaning: a blocked or failed milestone is
`CRITICAL`, completion is `IMPORTANT`, ordinary progress is `PROGRESS`.

`observe()` returns a dataclass from the tracker but a dict from the service;
`_milestone_field` reads either rather than forcing one shape on the other.

## 4. The workspace stays useful without voice

Narration was already text-first and stays that way. With audio failing, the
complete milestone narrative still reaches the UI as text through the existing
`narration` channel and the Activity panel — the only difference is a spoken
line is not attempted successfully. The UI now states this plainly:

> **Voice output is not working.** This request exceeds your quota of 10000.
> Progress is still shown here as text, and tasks are unaffected.

Task submission, file upload and the voice channel all read the same event
stream, so they cannot disagree about what a task is doing.

## Files

`backend/app/services/elevenlabs.py` (transport raises), `narration.py`
(failures, `last_error`, honest counters), `api/voice.py` (composed state),
`orchestrator.py` (`_narrate_milestone`, `_milestone_sentence`,
`_milestone_field`), `frontend/src/types.ts`, `frontend/src/components/VoiceChannel.tsx`,
tests in `test_elevenlabs.py` and `VoiceChannel.test.tsx`.
