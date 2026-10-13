# Scope — a voice-first conversation

| | |
|---|---|
| **Stage** | 2.5.5 — conversational voice: greeting, acknowledgement, steering |
| **Date** | 2026-10-13 |

## Requested workflow

1. Open the Workspace, activate Voice.
2. The agent greets and asks what to do.
3. The user explains a task by voice.
4. The agent acknowledges, confirms what it understood, creates the task, starts.
5. Spoken updates follow: what it is doing, which files it changed, what resulted.
6. The user can interrupt or add instructions by voice mid-task.
7. The agent acknowledges the addition and coordinates it into the running task.
8. Context and prior instructions are preserved across follow-ups.

## What already existed

* Voice **input** already reached the task path: the session hook transcribed a
  turn and posted it to the normal message endpoint, so speaking created tasks.
* **Steering** already existed: a message during a running task is recorded and
  forwarded to the agent.
* **Milestones** were already spoken.

## What was missing

The conversation was **one-sided**. The agent was heard only when a milestone
fired, so:

* A session opened in silence — nothing to respond to.
* A request produced **no spoken acknowledgement**; the reply existed, but
  `_narrate` forwarded only `progress.summary` and `error`.
* **File changes were inaudible**, though the user explicitly asked which files
  changed.

## Principle

A spoken conversation needs three things the milestone channel alone cannot give:
an **opening**, an **acknowledgement**, and **confirmation of what changed**.
Milestones describe the work; they do not answer the person.

## Related

- [Implementation 0076](../02-implementation/voice-first-conversation-0076.md)
- [Defect log 0078](../04-defects/defect-log-0078.md)
