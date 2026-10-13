# Scope — voice pipeline and natural milestone narration

| | |
|---|---|
| **Stage** | 2.5.2 — ElevenLabs integration and real-time spoken milestones |
| **Date** | 2026-10-13 |

## Reported

The Pi Agent and Orchestrator now work. Voice does not: milestones are generated
as a task progresses, but nothing is spoken, and the Voice Agent does not explain
what is happening. Asked to trace the whole voice workflow and make the Voice
Agent narrate progress naturally in real time.

Also asked: the workspace must remain useful when voice fails — a typed task must
still produce a running, conversational explanation of what the agent is doing.

## Findings

Two layers, and the second is why nobody noticed the first:

1. **The account cannot synthesise.** Every request returns
   `401 This request exceeds your quota of 10000. You have 0 credits remaining.`
   That is an account state, not a Solo bug — but Solo reported voice as working.
2. **Solo hid the failure at four separate points**, so a completely dead voice
   pipeline presented as healthy.

Milestones were also never sent to the voice channel at all: `_narrate` forwarded
only `progress.summary` and `error`, and `_observe_milestone` persisted
transitions without announcing them.

## Principles applied

* **Text is the channel; audio is an enhancement.** Every narrated line exists as
  text regardless of whether it was spoken, so a typed task always produces a
  readable, conversational account of the work.
* **Never report success that did not happen.** A line with no audio is not a
  spoken line, and an account that cannot synthesise is not "voice-ready".
* **No network I/O on the polled state endpoint** (established in 2.5.1, D-42).

## Related

- [Implementation 0058](../02-implementation/voice-pipeline-0058.md)
- [Defect log 0060](../04-defects/defect-log-0060.md)
