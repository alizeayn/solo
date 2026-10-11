# Acceptance criteria — voice activation

| | |
|---|---|
| **Stage** | Voice activation |
| **Version** | 2.5.0 |
| **Date** | 2026-10-11 |
| **Result** | All met except the two environment-limited items, which are stated |

---

## 1. The requested outcome

> Speak a task, have Pi Agent execute it, and hear useful, context-aware spoken
> updates.

| Requirement | Status | Evidence |
|---|---|---|
| Speech input activates the pipeline | Met | Transcript posted to the existing message endpoint; task reaches `COMPLETED` in `test_voice_loop.py` |
| Pi Agent executes the task | Met | The deterministic agent in the test; the real agent in `e2e-live.sh` |
| Orchestrator identifies milestones | Met | `understanding → implementing → completed`, every one with evidence |
| The voice speaks relevant updates | Met | Synthesised text **equals** the spoken lines, in order |
| Interruption supported | Met | Barge-in clears progress, stops in-flight synthesis, and is called before the microphone opens |
| Questions answered from task state | Met | A question is classified `CHAT_OR_EXPLAIN` and answered, not dispatched as work |

## 2. Configuration

| Requirement | Status |
|---|---|
| Enter and save an ElevenLabs key | Met |
| Validate it against the API | Met — `GET /v1/user`, then the catalog and voice list |
| See whether it is configured and operational | Met — `configured`, `audio_available`, `phase` |
| Clear errors on failure | Met — five distinct messages, none containing the key |
| Key never exposed | Met — asserted in unit and e2e tests |
| Live model discovery | Met — `GET /v1/models`, account-specific |
| Useful per-model information | Met — character limit, cost multiplier, languages, alpha flag |
| Selecting changes the **runtime** | Met — `voice_config()` is resolved per line from saved settings |
| Roles made clear | Met — the model select is filtered by `can_do_text_to_speech`; input uses the complement |

## 3. Model accuracy

| Claim | Verified |
|---|---|
| `eleven_v4`, `eleven_v4_turbo`, `eleven_v3`, `eleven_v3_conversational` exist | Yes, per the model catalog |
| `eleven_v4_conversational` does **not** exist | Yes — the realtime v4 model is `_turbo` |
| `eleven_turbo_v2_5` does **not** exist | Yes — the v2.5 fast model is `eleven_flash_v2_5` |
| `scribe_v2`, `scribe_v2_realtime`, `scribe_v2_medical` exist | Yes |

Recorded because a hardcoded list would have shipped two ids that do not resolve.

## 4. The architecture requirements

| Requirement | How it is guaranteed |
|---|---|
| Selective updates | Only milestones are narrated; tool calls never are. Asserted on the `kind` of every line. |
| Real-time updates | A milestone is published per transition, not batched at the end. |
| Context-aware responses | Speech input feeds the same dispatch path, so the answer comes from real task state. |
| Consistent state | The voice panel and the milestone tile read the same structured objects. |
| Not coupled to the frontend | `ElevenLabsTransport` implements a backend protocol; the frontend fetches audio by line id. |
| No invented progress | The voice speaks milestones the tracker derived from evidence; the model may only reword what was already justified. |
| Uncertainty communicated | With no evidence there is no milestone, so nothing is said. With no key, the UI says audio is unavailable. |

## 5. Anti-fabrication

| Criterion | Asserted |
|---|---|
| No timer-based milestone | `MilestoneTracker` has no clock |
| No fabricated progress | Unrelated events return `None` |
| The model cannot invent a milestone | It is only reachable after a transition the tracker accepted |
| Every spoken line is traceable | Every line carries `task_id` and its milestone's evidence |
| Information is never audio-only | Every line is published to the UI whether or not it was spoken |

## 6. Test totals

| Suite | Count | Result |
|---|---|---|
| Backend | 456 | pass |
| Frontend | 132 | pass |
| `e2e.sh` | 76 | pass |
| **Total** | **664** | **0 failed** |

## 7. Verification commands

```bash
cd backend && ../venv/bin/python -m pytest          # 456 passed
cd frontend && npx vitest run && npx tsc --noEmit   # 132 passed, clean
./scripts/e2e.sh                                     # 76 passed
```

## 8. Honest limitations

| Item | Reason |
|---|---|
| **No live ElevenLabs call was made** | No key is available in this environment. The request shape — header, path, body, content type — is asserted instead, which is what a canned response hides. This is the single most important limitation to state: the integration is verified against the *documented* API, not against the live service. |
| No browser audio verification | No headless-browser layer. Playback is covered by component tests and by hand. |
| Turn-taking is push-to-talk | Documented as the upgrade path (`scribe_v2_realtime`). |
| No streaming playback | One MP3 per line; barge-in stops it but cannot resume mid-line. |
| Cost is real | Billed per character — the second reason narration is milestone-only. |

## Related

- [Scope 0039](../01-planning/voice-activation-0039.md)
- [Defect log 0042](../04-defects/defect-log-0042.md)
- [Summary 0044](../06-summary/summary-0044.md)
