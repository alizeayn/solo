# Implementation — voice-first conversation

| | |
|---|---|
| **Stage** | 2.5.5 |
| **Date** | 2026-10-13 |

---

## 1. The agent now answers out loud

`_narrate` handled only `progress.summary` and `error`. Two event types were added:

| Event | Spoken as | Priority |
|---|---|---|
| `assistant.message` | the agent's own reply | `IMPORTANT` |
| `file.changed` | "I've created login.html." | `PROGRESS` |

`IMPORTANT` outranks `PROGRESS`, which matters twice: an acknowledgement is never
superseded the moment work starts, and it is never dropped just because the user
is still speaking.

The acknowledgement itself was rewritten for speech. `"Started a coding task: …"`
is log wording; the reply is now:

> Got it. I'll get started on this: create a login page.

File changes are phrased by verb (`_file_sentence`): created / updated / removed,
with an unknown verb still producing something sayable rather than a blank.

**Coalescing is deliberate.** The queue drops a superseded `PROGRESS` line, so a
burst of writes reports the latest file instead of replaying every write. The
phase-level truth still comes from milestones.

## 2. The session opens with a greeting

New endpoint:

```
POST /api/voice/say   { "text": "...", "kind": "greeting" }
```

The greeting deliberately reuses the **normal narration pipeline** rather than
introducing a second one. One synthesis path, one WebSocket stream, one player —
so the greeting cannot drift from milestone speech, and it appears in the
transcript like every other line.

It is contextual:

| State | Spoken |
|---|---|
| A task is running | "Hello again. I am still working on the current task. What would you like me to change?" |
| A project is open | "Hello. I am listening. What would you like me to do in <project>?" |
| Otherwise | "Hello. I am listening. What would you like me to work on?" |

`VoiceChannel` sends it once per session, guarded by a ref so re-renders cannot
repeat it, and resets the guard when the session closes.

## 3. Steering and context

Both already worked and needed no change, which is worth stating because it is
most of the requested workflow:

* A message sent while a task runs is recorded as a note and forwarded with
  `steer_task`, so "change the button colour" reaches the running agent.
* Conversations are persisted per project, so follow-ups carry the earlier
  instructions. Voice input posts to the same endpoint as typed input, so the two
  cannot diverge.

With acknowledgements spoken, a steer now produces an audible confirmation too.

## 4. The flow, end to end

```
tap Voice  -> greeting spoken
speak task -> /api/voice/transcribe -> /api/projects/{id}/messages
           -> Orchestrator classifies -> task created
           -> assistant.message  -> "Got it. I'll get started on this: <task>"
           -> file.changed       -> "I've created login.html."
           -> milestones         -> understanding / implementing / verifying / completed
speak again-> steered into the running task, acknowledged aloud
```

## Files

`backend/app/services/orchestrator.py` (`_narrate`, `_file_sentence`,
acknowledgement wording), `backend/app/api/voice.py` (`POST /say`),
`frontend/src/api/client.ts`, `frontend/src/components/VoiceChannel.tsx`.
