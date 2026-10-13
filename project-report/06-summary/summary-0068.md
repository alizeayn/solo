# Summary — 2.5.3

| | |
|---|---|
| **Stage** | Narration playback and stream recovery |
| **Version** | 2.5.3 |
| **Date** | 2026-10-13 |

---

## The audio was real; the client never asked for it

The provider usage log answered the question outright: **82 requests, every one
HTTP 200, thirteen of them successful text-to-speech calls.** ElevenLabs was
generating audio and credits were being spent exactly as expected.

Solo's own log then supplied the missing half: **`/api/voice/audio` had been
requested zero times.**

The cause was a single default:

```ts
const [enabled, setEnabled] = useState(false)
```

Playback was off. The panel offered a quiet `🔇 Voice off` toggle, and the client
silently declined audio the server had already paid for. **Full cost, no audio** —
the worst of both outcomes, defended in a comment as avoiding an autoplay fight.

It is now on by default and persisted. A browser refusal is no longer obeyed
silently: the line stays queued, the panel says `tap anywhere to enable sound`, and
the next interaction resumes it.

## Two further bugs, one of them hidden by the first

* **A refused line could never be heard.** It was marked *seen* before playback was
  attempted, so after a single autoplay refusal the lines explaining the task were
  permanently unplayable — even once the user clicked. A bug in its own right.
* **The audio element was created after the code that needed it.** `new Audio()`
  lived in an effect declared after the queueing effect, so the first drain found
  `null` and skipped the line. That was invisible while playback started disabled,
  and became immediately fatal once it did not. Fixing the default exposed it in
  the first test run.

## The connection

32 closes, 32 opens. Classified against the log: **30 followed a server restart
(15) or a page load (19)** — including my own updates — and only **2 were
unexplained**. So the drops were mostly real but largely self-inflicted.

The genuine defect was that **nothing refetched after a drop**. A WebSocket
delivers only what happens while it is open, so a task that advanced during an
interruption left every panel stale until a manual reload. That is what turned a
brief hiccup into "the workspace is broken". `WorkspaceProvider` now resyncs on
reconnect.

## Test coverage

`useSpeechPlayback` had **no test**, and the defect it shipped was exactly what a
test would have caught. Six now cover it: the default, the fetch, the refusal and
its recovery, persistence, and no duplicate playback.

## Verification

| Suite | Result |
|---|---|
| Frontend | **139 passed** (133 + 6) |
| Typecheck / build | clean |
| Provider audio path | 13 successful TTS calls, all HTTP 200 |

## What I could not verify

**I have not heard a milestone spoken.** The key Solo holds reports
`used 10000 / limit 10000 / remaining 0`, and every synthesis returns
`quota_exceeded`. The live suite reached `phase: voice-active` and then failed
every call.

There is also a puzzle worth your attention: **key `sk_2f98d…` cannot have made
those thirteen successful calls while simultaneously reporting zero credits.** The
calls that worked were made with a different key than the one now saved. Check
which key is in Settings → Voice.

## Related

- [Scope 0063](../01-planning/audible-narration-0063.md)
- [Implementation 0064](../02-implementation/audible-narration-0064.md)
- [Testing 0065](../03-testing/audible-narration-0065.md)
- [Defect log 0066](../04-defects/defect-log-0066.md)
- [Verification 0067](../05-verification/acceptance-criteria-0067.md)
