# Testing — narration delivery

| | |
|---|---|
| **Stage** | 2.5.4 |
| **Date** | 2026-10-13 |

## Suites

| Suite | Result |
|---|---|
| Frontend | **147 passed** (139 + 8 new), 19 files |
| Frontend typecheck | clean |
| Frontend build | succeeded |
| Backend | unchanged this round |

## The contract, verified on the wire

Proven against a real `NarrationService` with a succeeding transport — no network,
no credits spent:

```
narration publishes:
   ('527ab6aed961', False, "I'm making the changes now. Build the lo")
   ('527ab6aed961', True,  "I'm making the changes now. Build the lo")

same id published twice?  True
second publish spoken=true? True
=> appendUnique keeps only False  (client never fetches audio)
=> upsertNarration keeps True     (client fetches and plays)
```

That is the whole defect and the whole fix in five lines.

## New tests

`WorkspaceProvider.test.ts` — six cases on `upsertNarration`:

| Test | Guards |
|---|---|
| appends a line it has not seen | the insert path still works |
| **replaces a queued line when the same id is delivered** | **the regression** |
| keeps the original text when the update carries none | a merge must not blank fields |
| carries a synthesis failure through to the line | failures stay visible and unspoken |
| leaves other lines untouched and preserves order | no accidental reordering |
| bounds the list so a long task cannot grow it without limit | memory bound kept |

`OrchestrationPanel.test.tsx` — two more:

| Test | Guards |
|---|---|
| reports a failing Orchestrator instead of silently falling back | the degradation is visible, with the real reason |
| stays quiet when the Orchestrator is healthy | no false alarm |

## Why this was missed twice

The evidence available in 2.5.2 and 2.5.3 was all server-side and all healthy.
The one wrong value lived in a client-side reducer behind a WebSocket, so no
server log, no HTTP status and no provider report could show it. It was found by
reading what the frontend does with a narration envelope rather than what it
receives.

## Not verified

| Gap | Reason |
|---|---|
| Hearing narration end-to-end in a browser | No browser layer; and the account's balance is consumed during testing |
| iOS Safari playback specifically | No iOS device available in this environment |
