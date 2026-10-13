# Acceptance criteria — 2.5.4

| | |
|---|---|
| **Stage** | Narration delivery, mobile playback, visible degradation |
| **Date** | 2026-10-13 |

---

## 1. Diagnose the whole voice workflow

| Requirement | Status |
|---|---|
| Milestone events | ✅ reach the UI (milestone channel upserts correctly) |
| ElevenLabs generation | ✅ 24 successful TTS calls, HTTP 200, on desktop and phone |
| Audio delivery to the client | ❌ **was the failure** — 0 fetches for 24 generated files |
| Playback | ✅ fixed in 2.5.3; blocked in practice by the delivery failure |
| Mobile compatibility | ✅ playback needs no HTTPS; autoplay retry already runs inside the gesture |

## 2. Fix it

| Requirement | Status |
|---|---|
| The delivered line replaces the queued one | ✅ `upsertNarration` |
| The failure cannot recur silently | ✅ 6 tests, including the exact regression |
| Narration missed during a drop is recovered | ✅ resync merges `/api/voice/state` |
| Mobile autoplay refusal is recoverable | ✅ retried inside the gesture listener |

## 3. Report failures clearly instead of failing silently

| Requirement | Status |
|---|---|
| Synthesis failure is visible | ✅ carried on the line and in `/api/voice/state` (2.5.2) |
| Orchestrator rate limit is visible in the workspace | ✅ `OrchestrationPanel` notice with the real message |
| Orchestrator rate limit is in the logs | ✅ already, with the provider's own text |
| Voice input may remain unsupported | ✅ accepted; narration output is the goal |

## 4. Not satisfied

| Requirement | Status |
|---|---|
| Hearing narration in a browser end-to-end | ❌ no browser layer in this environment; the account balance is also consumed by testing |
| iOS Safari specifically | ❌ no iOS device available |

## Honest position

The blocker is **found, fixed and covered by a test that fails on the old code**:
narration was published twice under one id and the second, authoritative message
was discarded, so the player never had a line with audio. This was verified
directly on the wire, not inferred.

What I still cannot do is **hear it**, because that requires a browser and a
funded ElevenLabs key. The delivery chain from milestone → synthesis → client
fetch → playback is now correct end to end in code and test; the remaining
unknown is only the browser's own audio output.

## Related

- [Implementation 0070](../02-implementation/narration-delivery-0070.md)
- [Defect log 0072](../04-defects/defect-log-0072.md)
- [Summary 0074](../06-summary/summary-0074.md)
