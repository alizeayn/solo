# Defect log — voice activation

| | |
|---|---|
| **Stage** | Voice activation |
| **Version** | 2.5.0 |
| **Date** | 2026-10-11 |
| **Defects** | D-37 … D-41 (5) |

---

## D-37 — The Voice settings pane asked for credentials that are not used

**Severity** Medium · **Status** Fixed · **Found by** implementing the integration

**Symptom.** The pane required a **Conversational Agent ID** and a pasted
**voice ID** before it would report success.

**Root cause.** The pane was written during Phase 2.3 scaffolding, when the plan
was to use the ElevenLabs Agents Platform. That decision was reversed — the
Agents Platform owns the conversation loop and the language model, which would
put an ElevenLabs agent in front of Solo's Orchestrator and let it answer from
its own context instead of from real task state.

**Fix.** The pane now saves a key, validates it, and discovers models and voices
from the account. `elevenlabs_agent_id` remains in the schema but is no longer
required or validated.

**Why it mattered.** Left alone, the UI would have demanded a credential the
integration never reads — and a user who supplied one would have had no way to
tell that nothing used it.

---

## D-38 — `audio_available` came from a lazy flag, so the UI could report "no audio" while speaking

**Severity** High · **Status** Fixed · **Found by** the end-to-end voice-loop test

**Symptom.** With a key and voice configured,
`/api/voice/state` reported `audio_available: false` until something had been
spoken.

**Root cause.** The state endpoint read the transport's `_configured` flag, which
is only set *during delivery*. Before the first line it was still `False` even
though a key and voice existed.

**Fix.** The endpoint now calls `settings_service.voice_config()` — the **same**
method the transport calls before it speaks — and reports `audio_available` from
that. A comment records why, because this is the third instance of the same bug
class in this project:

| Defect | Same shape |
|---|---|
| D-28 | Model listing read the completions accessor |
| D-29 | The enabled toggle read the static env default |
| D-38 | Audio availability read a lazy runtime flag |

The recurring question is: *does the value the UI displays come from the same
source as the value the runtime acts on?*

---

## D-39 — A spoken line was recorded but never marked as spoken

**Severity** High · **Status** Fixed · **Found by** the end-to-end voice-loop test

**Symptom.** With a real transport, every line in `/api/voice/history` had
`spoken: false`, and the frontend player had nothing to play.

**Root cause.** `ElevenLabsTransport.deliver` stored the audio but never set
`line.spoken_at`. The recording transport sets it; the real one did not. So the
one code path that matters most — the real one — was the one that lost the flag.

**Fix.** `spoken_at` is set immediately after the audio is stored, and only then.
A line whose synthesis failed correctly reports `false`, which is what stops the
player fetching audio that was never produced.

**Note.** This is precisely the class of bug that a mocked-transport test hides.
The voice-loop test uses the real transport with only the HTTP client stubbed,
which is why it caught it.

---

## D-40 — The connection test used a second HTTP path

**Severity** Medium · **Status** Fixed · **Found by** the end-to-end test

**Symptom.** The stubbed HTTP client was bypassed, so the test failed with
`'StubElevenLabs' object does not support the asynchronous context manager
protocol`.

**Root cause.** `test_elevenlabs` opened its own `httpx.AsyncClient` for the
account check and then constructed an `ElevenLabsClient` for the rest — two
independent HTTP paths inside one method.

**Fix.** One client, the same one the transport uses. **The failure was a
symptom; the design was the defect.** Two paths in one method is how a check
passes while the runtime fails, which is D-28 again.

---

## D-41 — A voice-loop assertion raced the narration worker

**Severity** Low (test correctness) · **Status** Fixed · **Found by** the test failing

**Symptom.** The assertion that synthesised text equals the spoken lines failed
intermittently with `no line reached the transport`.

**Root cause.** The test polled until *one* line had `spoken: true`, then
compared the full list against the synthesis log. The narration worker was still
draining its queue, so the two snapshots were taken at different moments.

**Fix.** The test waits for `queued == 0 and spoken >= 1` before comparing, so it
observes a settled state rather than a moving one.

**Note.** The product was correct; the test was wrong. It is recorded because
"the test was flaky" is a real defect in the evidence, and an intermittent
assertion that is silenced rather than fixed is worse than no assertion.

---

## Open

| ID | Issue | Status |
|---|---|---|
| **D-08** | Docker image build not executed — no daemon socket access | Open (environment) |
| — | No ElevenLabs key in this environment, so no live API call was made | Accepted; the request shape is asserted instead |
| — | No browser-driven audio verification | Accepted limitation |
| — | Turn-taking is push-to-talk, not full duplex | By design; documented |

## Related

- [Implementation 0040](../02-implementation/elevenlabs-voice-0040.md)
- [Testing 0041](../03-testing/voice-loop-test-0041.md)
- [Verification 0043](../05-verification/acceptance-criteria-0043.md)
