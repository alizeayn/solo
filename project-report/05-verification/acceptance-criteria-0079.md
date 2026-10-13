# Acceptance criteria — 2.5.5

| | |
|---|---|
| **Stage** | Voice-first conversation |
| **Date** | 2026-10-13 |

---

## The requested workflow, step by step

| # | Step | Status |
|---|---|---|
| 1 | Open the Workspace and activate Voice | ✅ unchanged; one control |
| 2 | The agent greets and asks what to do | ✅ **new** — spoken, contextual, once per session |
| 3 | Explain the task verbally | ✅ already worked: transcribe → the normal message path |
| 4 | Acknowledge, confirm understanding, create the task, start | ✅ **new** — the reply is now spoken and echoes the request |
| 5 | Natural progress updates, files, results | ✅ milestones already spoken; **file changes now too** |
| 6 | Interrupt or add instructions by voice | ✅ already worked — barge-in and steering |
| 7 | Acknowledge the addition and coordinate it | ✅ steering existed; the acknowledgement is now audible |
| 8 | Preserve context and prior instructions | ✅ conversations are persisted per project; voice and typing share one path |

## Coordination

| Requirement | Status |
|---|---|
| Voice ↔ Orchestrator | ✅ transcription posts to the same endpoint as typed text |
| Orchestrator ↔ Pi Agent | ✅ steering forwards into the running task |
| Milestones ↔ voice | ✅ milestones, acknowledgements and file changes share one narration channel |
| Real-time delivery | ✅ one WebSocket channel for all narration |
| One synthesis path | ✅ the greeting uses `/api/voice/say`, not a second mechanism |

## Errors reported rather than swallowed

| Requirement | Status |
|---|---|
| Speech failure visible | ✅ `audio_error` in state and in the panel (2.5.2) |
| Orchestrator degradation visible in the workspace | ✅ (2.5.4) |
| Orchestrator rate limit in the logs | ✅ with the provider's own message |
| A rejected greeting | ✅ 422, not silence |

## Test totals

| Suite | Result |
|---|---|
| Backend | **468 passed** |
| Frontend | **150 passed**, typecheck clean, build succeeded |

## Not satisfied

| Requirement | Status |
|---|---|
| Hearing the greeting and acknowledgements through ElevenLabs | ❌ **the account is exhausted again** (`used 10000 / limit 10000`); synthesis returns `quota_exceeded`. Covered by the stub-transport loop test. |
| Testing voice *input* with a real microphone | ❌ no browser or microphone here |
| iOS Safari | ❌ no iOS device |

## Honest position

Every step of the requested workflow now has a code path, and the two steps that
were genuinely missing — the greeting and the spoken acknowledgement — are
implemented and covered by tests that assert the actual spoken text.

What I could not do is **hear them**, because the ElevenLabs balance is spent
again. The last thing I verified by ear was in 2.5.4, where narration played
correctly once the delivery bug was fixed.

## Related

- [Implementation 0076](../02-implementation/voice-first-conversation-0076.md)
- [Defect log 0078](../04-defects/defect-log-0078.md)
- [Summary 0080](../06-summary/summary-0080.md)
