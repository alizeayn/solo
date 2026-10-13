# Acceptance criteria — 2.5.3

| | |
|---|---|
| **Stage** | Narration playback and stream recovery |
| **Date** | 2026-10-13 |

---

## 1. Why no narration was heard

| Requirement | Status |
|---|---|
| Investigate the whole path | ✅ provider log + Solo log + code |
| Identify the cause | ✅ **playback defaulted to off**; audio was generated and never fetched |
| Evidence that audio was produced | ✅ 13 TTS calls, all HTTP 200 |
| Evidence the client never asked for it | ✅ `/api/voice/audio` requested **0** times |

## 2. Fix the playback

| Requirement | Status |
|---|---|
| Narration is audible without hunting for a setting | ✅ on by default, persisted |
| An autoplay refusal is recoverable | ✅ resumes on the next gesture |
| An autoplay refusal is visible | ✅ `tap anywhere to enable sound` |
| Refused lines are not lost | ✅ requeued, never marked seen |
| No duplicate playback | ✅ covered by test |
| Regression coverage | ✅ 6 new tests on an untested hook |

## 3. Fix the perceived connection drops

| Requirement | Status |
|---|---|
| Drops characterised | ✅ 30 of 32 explained by restarts/page loads; 2 unexplained |
| Missed events recovered | ✅ resync on reconnect |
| Panels no longer go stale after a drop | ✅ tasks, messages and events refetched |

## 4. Not satisfied

| Requirement | Status |
|---|---|
| Hearing a milestone spoken end-to-end | ❌ **the stored key reports 0 credits remaining**, so synthesis cannot succeed. The live suite reached `phase: voice-active` and then failed every call with `quota_exceeded`. |
| Browser playback of real audio | ❌ no browser layer |

## Honest position

The defect that explains the report is **found, fixed and covered by tests**: Solo
generated audio thirteen times and the client refused to fetch it, because playback
defaulted to off. That is now on by default, refusals are recovered and visible,
and refused lines are no longer discarded.

I have **not** heard a milestone spoken, because the key Solo holds currently has
no credits. The provider log proves the audio path works; the remaining blocker is
the key, not the code.

## Related

- [Implementation 0064](../02-implementation/audible-narration-0064.md)
- [Defect log 0066](../04-defects/defect-log-0066.md)
- [Summary 0068](../06-summary/summary-0068.md)
