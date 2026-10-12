# Testing — 2.5.1

| | |
|---|---|
| **Stage** | Orchestrator, Pi Agent, network and TLS |
| **Date** | 2026-10-12 |

## Suites

| Suite | Result |
|---|---|
| Backend (`pytest`) | **463 passed** (458 + 5 new) |
| Frontend (`vitest`) | 131 passed *(unchanged this round)* |
| Typecheck / build | clean *(unchanged this round)* |

## The Orchestrator, against the user's real account

The only test that mattered was the real one. Before the fix, **every** message
returned `None` and silently fell back to rules. After it:

| Message | Intent | Model's reason (real) |
|---|---|---|
| `hi` | `CHAT_OR_EXPLAIN` | "User greets with 'hi', which is a conversational opener" |
| `can you create a test module in the project?` | `START_CODING_TASK` | "User requests creating a test module…" |
| `whats yore model name?` | `CHAT_OR_EXPLAIN` | "…informational question about my model" |
| `Create a file hello.py that prints hi` | `START_CODING_TASK` | "…asks to create a new file hello.py…" |
| `stop` | `STOP_ACTIVE_TASK` | "User issued a stop command…" |

5/5 correct, with genuine per-message reasoning. This is the clearest evidence
that the Orchestrator is now doing the work rather than being bypassed.

## New regression tests

| Test | Guards |
|---|---|
| `test_complete_json_retries_without_response_format_on_400` | the fallback; asserts the retry drops `response_format` |
| `test_complete_json_does_not_retry_a_real_failure` | a 401 is surfaced, not retried into a silent pass |
| `test_fallback_prompt_describes_keys_without_echoing_the_schema` | the prompt contains no `"properties"`/`"required"` — the echo bug |
| `test_schema_instructions_list_enum_values_without_picking_one` | an enum is described, never demonstrated |
| `test_structured_output_rejected_only_matches_400` | 401/402/429/500/None are not treated as unsupported-parameter errors |

## Pi Agent readiness

Fresh isolated runtime, real task submitted, end-to-end:

```
error  Pi has no model selected. Choose a provider and model in Settings → Pi Agent.
```

Previously this same run emitted `progress.summary "Pi is running unknown from
Solo's own runtime"` and then failed with a message about an API key the user
never chose.

## Network and TLS

| Check | Result |
|---|---|
| `0.0.0.0:8080` listener | present |
| `http://127.0.0.1:8080/api/health` | 200 |
| `http://172.16.1.60:8080/api/health` (LAN) | **200** |
| `openssl` certificate SAN | `DNS:localhost, IP:127.0.0.1, DNS:<host>.local, IP:172.16.1.60` |
| `https://127.0.0.1:8090/api/health` with TLS on | **200** |
| plain `http://127.0.0.1:8090` with TLS on | correctly refused |
| Certificate presented | `subject=CN = solo` |
| `./solo.sh access` | reports bind address, LAN URL and voice readiness |

## Not verified

| Gap | Reason |
|---|---|
| A real phone or a second physical device | None available in this environment |
| Microphone capture and playback on a mobile browser | No mobile browser; no headless-browser layer |
| Mobile layout at 320/375/414 px | Responsive work is **not implemented** — see the summary |
| Live task run with a working provider quota | The account's free tier was rate-limited (429) during testing |
