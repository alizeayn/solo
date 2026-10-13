# Implementation — narration delivery

| | |
|---|---|
| **Stage** | 2.5.4 |
| **Date** | 2026-10-13 |

---

## 1. The fix: merge narration by id

```
queued    ('527ab6aed961', spoken=False, "I'm making the changes now...")
delivered ('527ab6aed961', spoken=True,  "I'm making the changes now...")
```

`appendUnique` returned the list unchanged for the second message. The line was
therefore never marked spoken, and the player — which by design only plays lines
that have audio — skipped every one.

The merge is now a pure, exported function, `upsertNarration`, so the invariant is
directly testable rather than buried in a WebSocket callback:

```ts
export function upsertNarration(lines, incoming, keep = 100) {
  const index = lines.findIndex((item) => item.id === incoming.id)
  if (index === -1) return [...lines, incoming].slice(-keep)
  const next = [...lines]
  next[index] = { ...next[index], ...incoming }
  return next
}
```

This also carries the `error` field through, so a line whose synthesis failed
shows the reason and stays unspoken instead of looking successful.

**Why it survived two previous investigations.** Every other signal was healthy:
ElevenLabs returned 200, credits were spent, the panel listed the lines, the
milestones appeared. Only one boolean was wrong, and it was wrong on the client,
in a reducer, behind a WebSocket. Fixing "playback off by default" in 2.5.3 was
necessary but not sufficient — the lines it would have played were still unspoken.

## 2. Recover narration missed during a drop

The reconnect resync added in 2.5.3 refetched tasks, messages and events but not
narration. Lines spoken while the socket was down produced audio nobody was told
about. The resync now also pulls `/api/voice/state` and merges its `recent` lines.

This matters more on mobile, where the connection is less stable and the page is
more likely to be backgrounded mid-task.

## 3. Report Orchestrator degradation in the workspace

`OrchestratorBrain` already tracked `call_count`, `failure_count` and `last_error`
and exposed them on `/api/orchestrator/status`, and the Settings pane showed them.
The workspace tile did not, so a rate-limited account looked like a working one
while every model call failed.

`OrchestrationPanel` now reports it where the work happens:

> Orchestrator model unavailable, so Solo is using deterministic rules and
> snapshot answers. Tasks are unaffected.
> `Rate limit exceeded: free-models-per-day.`

The fallback itself is unchanged and still correct — degrading to rules is better
than blocking a task. What changed is that it is now visible.

## 4. Mobile notes

* **Playback does not need HTTPS.** Only the microphone does, so milestone audio
  can work on `http://<lan-ip>` even though voice *input* cannot.
* **Mobile autoplay is stricter**, and the 2.5.3 recovery already fits it: the
  retry runs directly inside a `pointerdown`/`touchstart`/`keydown` listener, and
  `play()` is reached before the first `await`, so the gesture is still live when
  the browser checks it.
* **Backgrounding** a mobile browser can suspend timers and the socket; the
  reconnect resync is what makes returning to the tab recover state.

## Files

`frontend/src/state/WorkspaceProvider.tsx` (upsert, resync),
`frontend/src/panels/OrchestrationPanel.tsx` (degradation notice),
`frontend/src/state/WorkspaceProvider.test.ts` *(new)*.
