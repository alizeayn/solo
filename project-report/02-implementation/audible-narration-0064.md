# Implementation — audible narration

| | |
|---|---|
| **Stage** | 2.5.3 |
| **Date** | 2026-10-13 |

---

## The defect

`useSpeechPlayback` defaulted to **off**:

```ts
const [enabled, setEnabled] = useState(false)
```

and the panel only rendered a small toggle (`🔇 Voice off`) when
`audio_available` was true. The result, measured rather than assumed:

| Observation | Value |
|---|---|
| Successful ElevenLabs TTS calls | **13** (all HTTP 200) |
| Requests for `/api/voice/audio/{id}` | **0** |

Solo synthesised, paid, stored — and the client never fetched a byte.

## Playback is now on, and a refusal is recoverable

* **Default on**, persisted to `localStorage` (`solo.voice.playback`) so a reload
  keeps the choice.
* **A blocked line is never lost.** On an autoplay refusal the line goes back to
  the front of the queue and a one-shot `pointerdown` / `keydown` / `touchstart`
  listener resumes it. Previously the line was marked *seen* before playback was
  attempted, so the very lines explaining a task could never be heard — even
  after the user clicked. That is a bug independent of the default.
* **The refusal is visible.** The panel shows
  `tap anywhere to enable sound`, so a silent panel becomes a one-tap fix instead
  of a mystery.
* **Only real failures drop a line** from the queue; an autoplay refusal does not.

## A latent ordering bug the fix exposed

The audio element was created in a `useEffect` declared **after** the effect that
queues lines and drains them. On first render the drain therefore found
`audioRef.current === null` and skipped the line. This was invisible while
playback started disabled — the element already existed by the time the user
toggled it on — and became fatal the moment playback defaulted to on.

The element is now created on first use (`ensureAudio()`), so ordering cannot
matter.

## Stream recovery

A WebSocket delivers only what happens while it is open; reconnecting does not
replay the gap. Nothing refetched on reopen, so a task that advanced during a drop
left every panel stale until a manual reload — which is why a brief interruption
presented as a broken workspace.

`WorkspaceProvider` now tracks the previous connection state and, on a
**re**connect (not the first connect, which the initial loads already cover),
refetches the task list, the messages and the selected task's events.

## What the log actually showed about the drops

32 closes, 32 opens. **30 of the 32 closes are explained by server restarts (15)
and page loads (19)** — including my own `solo.sh update` runs. Only 2 were
unexplained. The drop was largely real but mostly self-inflicted; the missing
resync is what made each one cost the user a reload.

## Files

`frontend/src/hooks/useSpeechPlayback.ts`, `frontend/src/components/VoiceChannel.tsx`,
`frontend/src/state/WorkspaceProvider.tsx`,
`frontend/src/hooks/useSpeechPlayback.test.ts` *(new)*.

## Note on the key

The stored key is still `sk_2f98d…`, and the account reports
`used 10000 / limit 10000 / remaining 0`. Yet 13 TTS calls succeeded earlier the
same day. Those two facts cannot both describe one key, so the calls that worked
were made with a different key than the one Solo now holds. Worth confirming which
key is saved in Settings → Voice.
