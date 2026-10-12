# Acceptance criteria — live voice and the workspace

| | |
|---|---|
| **Stage** | Live verification, regression fix, voice session |
| **Date** | 2026-10-12 |

---

## 1. Test the connection with the supplied key

| Requirement | Result |
|---|---|
| Key verified against the live service | ✅ `GET /v1/models` 200; TTS 200; STT 200 |
| Integration works correctly | ✅ solo validation passed; 11 models retrieved; real audio produced and served |
| Findings recorded | ✅ [`ElevenLabs Docs/07-live-verified.md`](../../ElevenLabs%20Docs/07-live-verified.md) |

**Honest note.** The key is **scoped**: it may read models and perform speech, but
it is **not permitted** `user_read` or `voices_read`. Both facts are reported as
skips with an explanation, not hidden. Speech output therefore uses a voice id set
directly (`EXAVITQu4vr4xnSDxMaL`, verified usable on this plan) because the account
cannot list voices, and library voices return `402` on a free plan.

## 2. The workspace regression

| Requirement | Status |
|---|---|
| Root cause identified | ✅ blocking third-party call on a hot path (D-42) |
| Pi Agent, Tasks, Activity, Inspector, Milestones restored | ✅ `/api/voice/state` performs no network I/O; the panel no longer polls per event |
| Integration between components intact | ✅ one WebSocket, one provider; the voice panel consumes the same streams as the rest |
| A single panel cannot break the others | ✅ `PanelErrorBoundary` on every tile (D-43) |
| No regression in existing behaviour | ✅ 458 backend, 131 frontend, `e2e.sh` 76 |

## 3. The voice interaction

| Requirement | Status |
|---|---|
| No push-to-talk / hold | ✅ session model; nothing is held |
| A button activates the interface | ✅ **Start voice session** |
| Animation displays while active | ✅ orbital animation, live input meter, session-open indicator |
| Session stays active until ended | ✅ turns are cut on silence and listening resumes automatically |
| Obvious way to end | ✅ **End voice session**, styled distinctly |
| Reflects listening / processing / speaking | ✅ status line and orb state |
| Clear active vs inactive feedback | ✅ live meter, panel highlight, session pill |

## 4. Milestone data for context-aware conversation

| Requirement | Status |
|---|---|
| Structured, not raw activity | ✅ the voice speaks milestones with `stage`, `status`, `detail`, `evidence`, `task_id` |
| Not every low-level operation | ✅ tool calls are never narrated |
| Consistent with the tile | ✅ both read the same milestone objects |
| No invented progress | ✅ milestones exist only where evidence justified them |

## 5. Documentation

| Requirement | Status |
|---|---|
| Folder named consistently | ✅ `ElevenLabs Docs/` (matching `Pi Agent Docs`) |
| Accurate and organised Markdown | ✅ 7 files + index; one earlier error corrected |
| Based on official sources | ✅ documentation plus **live-verified** results |

## 6. Test totals

| Suite | Count | Result |
|---|---|---|
| Backend | 458 | pass |
| Frontend | 131 | pass |
| `e2e-voice-live.sh` | 23 | pass (2 skipped: not permitted for this key) |
| `e2e.sh` | 76 | pass |

## 7. Limitations

| Item | Reason |
|---|---|
| No headless-browser check of playback or animation | No browser layer in this project; the weakest verification point |
| Segmentation is silence-based, not the realtime socket | Documented upgrade path |
| The installed copy needs an update to receive the fix | Separate checkout; delivered via the updater |
| D-08 open | Docker build unverified |

## Related

- [Implementation 0046](../02-implementation/live-voice-and-session-0046.md)
- [Summary 0050](../06-summary/summary-0050.md)
