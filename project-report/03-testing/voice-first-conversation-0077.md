# Testing — voice-first conversation

| | |
|---|---|
| **Stage** | 2.5.5 |
| **Date** | 2026-10-13 |

## Suites

| Suite | Result |
|---|---|
| Backend | **468 passed** (+3) |
| Frontend | **150 passed** (+3), 19 files |
| Frontend typecheck | clean |
| Frontend build | succeeded |

## Backend coverage

| Test | Guards |
|---|---|
| `test_a_spoken_task_runs_and_the_progress_is_spoken_back` (extended) | a `reply` line exists, it echoes the request, and its priority outranks progress |
| `test_narration_speaks_acknowledgements_and_file_changes` | created / updated / removed phrasing, and a sayable default for an unknown verb |
| `test_the_greeting_endpoint_speaks_through_the_normal_pipeline` | the greeting is queued **and lands in the transcript** |
| `test_an_empty_greeting_is_rejected` | a blank greeting is a 422, not silence |

The extended loop test is the important one: it asserts that the agent actually
acknowledged the request aloud and that the acknowledgement contains the
instruction the user gave, which is the requirement "confirms that it understands".

## Frontend coverage

| Test | Guards |
|---|---|
| greets the user when the session opens, and names the project | the conversation has an opening |
| greets once per session, not on every re-render | no repeated greeting |
| offers to change the current task when one is still running | the greeting is contextual |

## Verified behaviour from the loop test

```
reply   : "Got it. I'll get started on this: Write a simple Python calculator."
kind    : reply      priority: 1 (IMPORTANT — above progress)
```

## Not verified

| Gap | Reason |
|---|---|
| A live spoken greeting through ElevenLabs | The account reports **used 10000 / limit 10000 / remaining 0**, so synthesis returns `quota_exceeded`. The chain is covered by the stub-transport loop test instead. |
| Speech *input* end-to-end with a real microphone | No browser or microphone in this environment; the hook is covered by component tests. |
| iOS Safari specifically | No iOS device available. |
