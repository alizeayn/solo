# Summary — 2.5.5

| | |
|---|---|
| **Stage** | Voice-first conversation |
| **Version** | 2.5.5 |
| **Date** | 2026-10-13 |

---

## The conversation was one-sided

Voice input already worked — speaking created tasks, and steering already reached
a running agent. What was missing was that **the agent only spoke when a milestone
fired**. So a session opened in silence, a request produced no spoken
acknowledgement, and the files being written were inaudible.

Those are the three things a conversation needs that a milestone channel cannot
provide. Milestones describe the work; they do not answer the person.

## What was added

**The agent now answers out loud.** `assistant.message` and `file.changed` reach
the voice channel, with the acknowledgement at `IMPORTANT` priority so it cannot be
superseded the moment work starts nor dropped while the user is still speaking.

The acknowledgement was rewritten for speech. `"Started a coding task: …"` is log
wording; it is now:

> Got it. I'll get started on this: create a login page.

And file changes are phrased by verb — "I've created login.html", "I've updated
styles.css", "I've removed old.css" — coalescing under load so a burst of writes
reports the latest rather than replaying every one.

**The session opens with a greeting**, contextual to what is happening:

| State | Spoken |
|---|---|
| A task is running | "Hello again. I am still working on the current task. What would you like me to change?" |
| A project is open | "Hello. I am listening. What would you like me to do in <project>?" |

It goes through `POST /api/voice/say` — the **same narration pipeline** as
milestone speech. One synthesis path, one stream, one player, so the greeting
cannot drift from the rest and it lands in the transcript like any other line.

## What needed no change

Worth stating, because it is most of the requested workflow: steering and
conversation context already worked. A message during a running task is recorded
and forwarded to the agent, and conversations are persisted per project, so
follow-ups carry earlier instructions. Voice input posts to the same endpoint as
typed input, so the two cannot diverge — they now simply have an audible
acknowledgement attached.

## A small bug caught by its own test

`POST /api/voice/say` spread the narration state over its result, and `state()`
also has a `queued` key meaning *how many lines are pending*. It overwrote the
boolean, so a successful call reported `queued: 1`. The test asserted the value
rather than truthiness, which is the only reason it failed loudly instead of
passing.

## Verification

| Suite | Result |
|---|---|
| Backend | **468 passed** (+3) |
| Frontend | **150 passed** (+3), typecheck clean, build succeeded |
| Acknowledgement | asserted to echo the user's instruction, at priority 1 |

## What I could not verify

**The ElevenLabs account is exhausted again** — `used 10000 / limit 10000` — so
every synthesis returns `quota_exceeded` and I could not hear the greeting or the
acknowledgements. The chain is covered by the loop test with a stub transport,
which asserts the actual spoken text and its priority.

To test by ear, the key in Settings → Voice needs balance. Nothing else has to
change: the greeting and acknowledgements use the same path that played correctly
in 2.5.4.

## Remaining limitations

| Limitation | Note |
|---|---|
| ElevenLabs balance | Consumed by testing; needs a funded key |
| Voice input verification | No browser or microphone in this environment |
| Mobile responsive UI | Still deferred from 2.5.1 |
| D-49 | Answer rows still render as completed tasks |

## Related

- [Scope 0075](../01-planning/voice-first-conversation-0075.md)
- [Implementation 0076](../02-implementation/voice-first-conversation-0076.md)
- [Testing 0077](../03-testing/voice-first-conversation-0077.md)
- [Defect log 0078](../04-defects/defect-log-0078.md)
- [Verification 0079](../05-verification/acceptance-criteria-0079.md)
