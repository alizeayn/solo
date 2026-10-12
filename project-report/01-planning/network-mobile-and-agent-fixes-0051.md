# Scope — network access, mobile, and the agent fixes

| | |
|---|---|
| **Stage** | 2.5.1 — remote access, mobile responsiveness, Orchestrator/Pi defects |
| **Date** | 2026-10-12 |

## Requested

1. Reach Solo from phones and other devices on the network, and remotely where
   properly configured, without exposing it indiscriminately.
2. Make the Workspace UI genuinely usable on a phone, not merely shrunk.
3. Make voice work on a touchscreen: tap to start, session stays open.
4. **Reported defect:** submitting a task shows `Completed` but nothing happens;
   the Orchestrator and Pi Agent — especially Pi Agent Activity — are not working.

## Ordering decision

The reported agent defect was investigated first. A workspace that cannot run a
task is a more serious fault than a layout that is awkward on a phone, and the two
turned out to be connected: both are failures of *state that the UI reports
confidently but that does not reflect what happened*.

## Workstreams

| # | Workstream | Outcome |
|---|---|---|
| A | Orchestrator model call | **Fixed** — structured output was rejected by the configured model |
| B | Pi Agent readiness | **Fixed** — an unusable model is now reported, not run |
| C | Task/answer semantics | **Identified** — questions are recorded as completed tasks |
| D | Network accessibility | **Verified working**; TLS support added so phones can use voice |
| E | Mobile responsive UI | **Outstanding** — see limitations |

## Related

- [Implementation 0052](../02-implementation/network-mobile-and-agent-0052.md)
- [Defect log 0054](../04-defects/defect-log-0054.md)
