# Summary — 2.5.4

| | |
|---|---|
| **Stage** | Narration delivery, mobile playback, visible degradation |
| **Version** | 2.5.4 |
| **Date** | 2026-10-13 |

---

## One boolean, on the client, behind a WebSocket

The mobile log gave the answer: **24 successful ElevenLabs calls, and zero
requests for `/api/voice/audio`.** Audio was generated and paid for; the browser
never asked for it.

The cause was an id collision. A narration line is published **twice under one
id** — queued with `spoken: false`, then delivered with `spoken: true` — and the
provider merged narration with `appendUnique`, which **returns the list unchanged
when the id is already present**. The delivered message was discarded. Every line
stayed unspoken, and the player, which by design only plays lines that have audio,
fetched nothing. Ever.

The milestone channel in the *same handler* used an upsert, with a comment noting
that a milestone "may arrive more than once (queued, then updated)". The identical
situation was handled correctly for milestones and incorrectly for narration.

Proven on the wire with a real `NarrationService`:

```
('527ab6aed961', False, "I'm making the changes now...")
('527ab6aed961', True,  "I'm making the changes now...")
```

By 2.5.3 the audio was reachable and playback was enabled — but the lines the
player would have played were still unspoken. Fixing the default was necessary and
not sufficient.

## Why two earlier investigations missed it

Every available signal was healthy and all of it was server-side: HTTP 200s,
credits consumed, milestones rendering, lines listed in the panel. The one wrong
value lived in a client-side reducer behind a WebSocket, where no server log, no
status code and no provider report could reach it. It was found by reading what
the frontend *does with* a narration envelope rather than what it *receives*.

The lesson generalises: an append-only merge is wrong for any message that updates
an earlier one. That is now a named, exported, tested function.

## Also fixed

* **Narration missed during a disconnect is recovered.** The resync pulled tasks,
  messages and events but not narration, so lines spoken while the socket was down
  produced audio nobody was told about. It now merges `/api/voice/state`'s recent
  lines — which matters most on mobile, where backgrounding suspends the socket.
* **A rate-limited Orchestrator is visible in the workspace.** The brain already
  tracked `failure_count` and `last_error`; only Settings showed them. The tile now
  reports the degradation and the provider's own message. The fallback to
  deterministic rules is unchanged — degrading beats blocking — but it is no
  longer silent.

## Mobile

Playback does **not** require HTTPS, so milestone audio can work over
`http://<lan-ip>` even though voice *input* cannot. The autoplay retry already
runs directly inside a `pointerdown`/`touchstart` listener with `play()` reached
before the first `await`, so the gesture is still live when the browser checks it.

## Verification

| Suite | Result |
|---|---|
| Frontend | **147 passed** (139 + 8), 19 files |
| Typecheck / build | clean |
| Wire contract | same id twice, second `spoken: true` — verified |

## What I still cannot claim

**I have not heard narration.** That needs a browser and a funded key, and the
account's balance is consumed by testing. The chain from milestone → synthesis →
client fetch → playback is correct in code and covered by a test that fails on the
old behaviour; the remaining unknown is only the browser's own audio output.

## Related

- [Scope 0069](../01-planning/narration-delivery-0069.md)
- [Implementation 0070](../02-implementation/narration-delivery-0070.md)
- [Testing 0071](../03-testing/narration-delivery-0071.md)
- [Defect log 0072](../04-defects/defect-log-0072.md)
- [Verification 0073](../05-verification/acceptance-criteria-0073.md)
