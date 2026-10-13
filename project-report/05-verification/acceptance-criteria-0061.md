# Acceptance criteria — 2.5.2

| | |
|---|---|
| **Stage** | ElevenLabs integration and spoken milestones |
| **Date** | 2026-10-13 |

---

## 1. Investigate the voice workflow

| Requirement | Status |
|---|---|
| Trace the whole pipeline | ✅ transport → narration → API → UI |
| Identify the problems | ✅ four Solo defects (D-51…D-54) plus an account-level cause |
| Explain why voice is not working | ✅ quota exhausted, and Solo hid it at four points |

## 2. Fix the ElevenLabs integration

| Requirement | Status |
|---|---|
| Failures are reported, not swallowed | ✅ transport raises; narration records and publishes |
| Status reflects reality | ✅ `phase: narration-only`, `audio_available: false`, `audio_error` populated |
| The user learns the reason | ✅ the API message reaches the UI verbatim |
| No phantom "spoken" lines | ✅ `spoken` counts only lines with audio |
| Configuration still resolvable without network I/O on the polled endpoint | ✅ (D-42 preserved) |

## 3. Milestones → real-time natural voice

| Requirement | Status |
|---|---|
| Milestone transitions are announced | ✅ `_narrate_milestone` |
| Phrasing is conversational, not log text | ✅ per-stage phrasing, rewordable by the model |
| The model may not invent progress | ✅ `describe_milestone` can only reword an evidence-backed transition |
| Works with no model configured | ✅ deterministic fallback |
| Verified end-to-end | ✅ `kind=milestone` line produced from a real transition |

## 4. Workspace usable when voice fails

| Requirement | Status |
|---|---|
| A typed task still submits | ✅ unchanged |
| Progress is still explained naturally | ✅ narration is text-first; the line survives the audio failure |
| Task, upload and voice stay in sync | ✅ one event stream; no component infers progress independently |
| The failure is explained in the UI | ✅ "Voice output is not working … still shown here as text" |

## 5. Not satisfied

| Requirement | Status |
|---|---|
| Hearing actual speech | ❌ **impossible** — 0 credits; synthesis cannot succeed |
| Browser playback of real audio | ❌ no browser layer |
| Mobile responsive UI (2.5.1 carry-over) | ❌ not done |

## Honest position

The **integration defects are fixed and verified**: Solo can no longer present a
dead voice pipeline as healthy, and milestones now generate natural spoken-form
lines. **No audio can be produced until the ElevenLabs account has quota**, which
is outside Solo's control. Every claim above about speech *working* would be
false today, so none is made.

## Related

- [Implementation 0058](../02-implementation/voice-pipeline-0058.md)
- [Defect log 0060](../04-defects/defect-log-0060.md)
- [Summary 0062](../06-summary/summary-0062.md)
