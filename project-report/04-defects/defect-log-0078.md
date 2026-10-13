# Defect log — 2.5.5

| | |
|---|---|
| **Stage** | Conversational voice |
| **Date** | 2026-10-13 |
| **Defects** | D-62 … D-65 |

---

## D-62 — The agent never acknowledged a request out loud

**Severity** High · **Status** Fixed

**Symptom.** The conversation was one-sided: the user spoke, and was answered only
in text. Milestones were narrated; the reply was not.

**Root cause.** `_narrate` forwarded only `progress.summary` and `error`. The
assistant's reply — the acknowledgement the workflow depends on — was never sent
to the voice channel.

**Fix.** `assistant.message` is now spoken at `IMPORTANT` priority, above progress
so it can neither be superseded nor dropped mid-utterance. The wording was also
rewritten for speech: `"Started a coding task: …"` reads well in a log and poorly
aloud.

---

## D-63 — File changes were inaudible

**Severity** Medium · **Status** Fixed

**Root cause.** `file.changed` was not narrated at all, so the files the agent
created — which the user explicitly asked to hear about — never reached the voice
channel.

**Fix.** `_file_sentence` phrases each change by verb and it is announced at
progress priority, so a burst of writes coalesces instead of replaying every one.

---

## D-64 — The greeting endpoint reported a queue depth as its own result

**Severity** Low · **Status** Fixed · **Found by** its own test

**Root cause.** `POST /api/voice/say` returned
`{"queued": line is not None, ..., **narration.state()}`. `state()` also has a
`queued` key meaning *how many lines are pending*, and spreading it last
overwrote the boolean. The endpoint reported `queued: 1` for a successful call.

**Fix.** The narration state is nested under `state` so the two meanings cannot
collide. Caught immediately because the test asserted the value rather than
truthiness — `assert payload["queued"] is True` failed on `1`.

---

## D-65 — A voice session opened in silence

**Severity** Medium · **Status** Fixed

**Root cause.** Nothing was spoken when the session started, so the user had
nothing to respond to. A voice-first interface that says nothing on activation is
indistinguishable from one that is not working.

**Fix.** `POST /api/voice/say` and a contextual greeting sent once per session.

---

## Open

| ID | Issue | Status |
|---|---|---|
| — | ElevenLabs balance exhausted again (10000/10000) | Needs a funded key |
| — | Mobile responsive UI | Open (deferred from 2.5.1) |
| D-49 | Answers presented as completed tasks | Open (deliberate) |
| D-08 | Docker build unverified | Open (environment) |
