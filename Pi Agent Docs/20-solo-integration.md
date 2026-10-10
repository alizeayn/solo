# 20 — Solo ⇄ Pi Agent Integration

How Solo drives Pi, and the empirical findings that determined the design.

Every claim marked **verified** was reproduced against the installed `pi`
version `1.1.0`, not inferred from documentation.

---

## 1. Integration surface

Solo talks to Pi **only** through the documented RPC mode. There is no SDK
import, no internal file parsing, and no re-implementation of Pi's logic.

```
Solo backend                                    Pi subprocess
────────────                                    ─────────────
PiSessionManager
  └── one process per project ───────────────►  pi --mode rpc [--provider …] [--model …]
        │ stdin:  {"id":…,"type":"prompt",…}        cwd = project root
        │ stdout: {"id":…,"type":"response",…}
        │ stdout: {"type":"tool_execution_start",…}
        └── PiEventTranslator ──► normalised AgentEvent ──► TaskService ──► WebSocket
```

| Concern | Owner |
|---|---|
| Launching, framing, correlating, shutting down | `backend/app/adapters/pi_rpc.py` |
| Process-per-project lifecycle, reservations, restart | `backend/app/adapters/pi_session.py` |
| Mapping Pi records → Solo's event vocabulary | `backend/app/adapters/pi_events.py` |
| Configuring providers, credentials and models | `backend/app/services/pi_config.py` |
| Agent contract | `backend/app/adapters/base.py` (`CodingAgentAdapter`) |

The orchestrator, task lifecycle, event storage and UI are unchanged by the
backend swap: `PiCodingAgentAdapter` implements the same protocol as
`MockCodingAgentAdapter`.

---

## 2. Process model

**One long-lived Pi process per project**, started on demand and reused.

Why per project rather than per task:

- Pi's context lives in the process. A follow-up instruction ("now add tests")
  should continue the same conversation, not start from nothing.
- Steering (`steer` / `prompt` with `streamingBehavior`) is only meaningful
  against an in-flight run in the same process.
- Sessions stay naturally separated per project.

Why long-lived rather than per task: process start-up resolves the model catalog
and provider auth, which is slow and wasteful to repeat for each instruction.

The process is started with:

```
pi --mode rpc --no-approve --no-extensions --no-skills --no-prompt-templates --no-mcp
   [--provider <provider>] [--model <model>] [--thinking <level>]
cwd = <project root>
```

Flags are explained in §5. Solo reads stdout continuously on a dedicated thread;
a client that stops reading can stall Pi (documented backpressure behaviour).

---

## 3. Verified findings

These were discovered by experiment and each one changed the design.

### 3.1 `auth.json` overrides environment variables — **verified**

```
auth.json = AAAA-AUTHJSON   OPENROUTER_API_KEY = BBBB-ENVVAR
  → pi auth print-api-key --provider openrouter  →  AAAA-AUTHJSON
```

**Consequence.** Setting `OPENROUTER_API_KEY` in the subprocess environment is
**not** enough to make Solo's configured credential effective. An existing key
in the user's `auth.json` wins. Solo therefore writes the credential to
`auth.json` — the same file Pi's `/login` writes — so what the user configures in
Solo is what Pi actually uses.

### 3.2 A fresh agent directory has **zero models** — **verified**

```
PI_CODING_AGENT_DIR=<empty dir> → get_available_models → total = 0, openrouter = 0
PI_CODING_AGENT_DIR unset       → get_available_models → total = 436, openrouter = 405
```

The model catalog lives in the agent directory (`models.json` /
`models-store.json`). Overriding `PI_CODING_AGENT_DIR` to an empty directory
silently removes every model and leaves `--model` unresolved.

**Consequence.** Solo does **not** override the agent directory by default. It
reuses the user's existing Pi installation, which also preserves their providers
and catalog. An explicit `PI_AGENT_DIR` setting exists for users who want
isolation and accept running `pi update --models` to rebuild a catalog.

### 3.3 Non-interactive modes cannot answer the project-trust prompt — **documented + verified**

Pi requires a trust decision when a project contains `.pi/settings.json`,
`.pi/extensions`, `.pi/skills`, `.pi/prompts`, `.pi/SYSTEM.md` and similar.
Print, JSON and RPC modes cannot show the prompt: with `defaultProjectTrust:
"ask"` they **skip** the protected resources rather than failing.

**Consequence.** Solo passes an explicit flag on every launch so behaviour is
deterministic and never depends on a saved decision in `~/.pi/agent/trust.json`:

- default `--no-approve` (ignore project-local resources — safe, predictable);
- configurable to `--approve` for users who want their project's Pi resources.

### 3.4 Provider failures are reported in the message stream, not the process exit — **verified**

A rejected request produced `message_end` with
`stopReason: "error"` and a provider payload, then `agent_end`, then
`agent_settled`, with the child process still healthy:

```
[message_end assistant] stopReason=error
  err=402: {"message":"Insufficient credits …","code":402}
[agent_end]  [agent_settled]
```

`auto_retry_start` loops were also observed for a retryable upstream error.

**Consequence.** Solo must treat a *successful* `prompt` response as "accepted"
and derive task success from the terminal assistant message plus
`agent_settled` — never from the process exit code. Provider errors are surfaced
verbatim to the user.

### 3.5 `--api-key` is not accepted by `pi auth` — **verified**

`pi auth print-api-key --provider openrouter --api-key X` →
`Error: Auth commands only accept --provider and --model`. The flag exists on the
main CLI but not on auth subcommands. Solo does not rely on it.

### 3.6 Real file modification through RPC works — **verified**

With `--no-extensions` and a tool-capable model, a prompt asking Pi to write a
file produced:

```
tool_execution_start  write
tool_execution_end    write   isError=false
→ ping.txt on disk containing "pong"
```

### 3.7 Extension UI requests are unrenderable in Solo — **verified**

With the user's extensions loaded, the stream contained `extension_ui_request`
records (dialogs/notifications) that a non-TUI client cannot answer. With
`--no-extensions`, none appear.

**Consequence.** Solo launches Pi with `--no-extensions` by default: a predictable
harness with no unanswerable UI requests. Built-in tools (`read`, `bash`,
`edit`, `write`) are unaffected — they are not extensions.

---

## 4. Command mapping

| Solo action | Pi command |
|---|---|
| Start a coding task | `prompt` `{message}` |
| Follow-up while running | `prompt` `{message, streamingBehavior: "steer"}` |
| Follow-up after settle | `prompt` `{message, streamingBehavior: "followUp"}` |
| Cancel | `abort` |
| Inspect state | `get_state` |
| Conversation | `get_messages` |
| Token/cost stats | `get_session_stats` |
| Available models | `get_available_models` |
| Switch model | `set_model` `{provider, modelId}` |
| Thinking level | `set_thinking_level` `{level}` |
| Clear pending queue | `clear_queue` |
| New context | `new_session` |
| Shutdown | close stdin |

`abort` waits for the session to become idle before responding, so Solo sends it
and then waits for `agent_settled` before marking a task cancelled.

---

## 5. Launch flags Solo uses

| Flag | Why |
|---|---|
| `--mode rpc` | JSONL bidirectional control |
| `--no-approve` (default) / `--approve` | deterministic project-trust behaviour in a non-interactive mode |
| `--no-extensions` (default) | no unanswerable `extension_ui_request` records; a predictable harness |
| `--no-skills`, `--no-prompt-templates`, `--no-mcp` | Solo already assembles its own bounded context; disabling these keeps behaviour reproducible and avoids surprising network calls |
| `--provider`, `--model` | the selection made in Solo's Settings UI |
| `--thinking` | optional reasoning level |
| `--no-session` | Pi keeps conversation state in-process for the process lifetime; Solo records its own transcripts and task history in the project store |

`--no-session` is deliberate: Solo's `.solo/sessions/` and `.solo/tasks/` are
the durable, portable record that must survive restarts. Pi's own JSONL session
files would duplicate that, and `--session-dir` interacts with project trust
before the trust decision is made (documented). Persistent Pi sessions remain a
future option.

---

## 6. Event translation

Solo maps Pi's protocol onto its own small vocabulary so no Pi-specific record
ever reaches the database, the WebSocket, or the UI.

| Pi record | Solo event |
|---|---|
| `agent_start` | `run.started` |
| `tool_execution_start` (`write`, `edit`) | `file.changed` |
| `tool_execution_start` (other) | `tool.started` |
| `tool_execution_end` (bash/command) | `tool.finished` (+ `test.result` when it looks like a test run) |
| `tool_execution_end` `isError` | `error` |
| `message_end` with `stopReason: error` | `error` (provider message preserved) |
| completed assistant text block | `assistant.message` |
| `agent_settled` | `run.finished` → terminal task status |
| `compaction_start` / `_end` | `progress.summary` |
| `auto_retry_start` / `_end` | `progress.summary` |
| `queue_update` | `progress.summary` (steering accepted) |
| `extension_error` | `error` |

Reasoning/thinking blocks are **discarded**, never forwarded: Solo shows
observable tool activity and user-facing summaries, not private chain-of-thought.

Streaming text (`message_update` deltas) is coalesced before it is persisted, so
one assistant response does not become hundreds of database rows.

---

## 7. Failure handling

| Situation | Behaviour |
|---|---|
| `pi` binary missing | Pi backend reports unavailable; Settings explains how to install it; the mock backend remains available |
| Non-zero exit / crash | Task → `FAILED` with the captured stderr tail; the process is discarded and restarted on the next task |
| Malformed JSON line | Logged and skipped; the stream continues (framing is LF-only, deliberately not `readline`) |
| Provider error (401/402/429/5xx) | Surfaced verbatim from `message_end`, task → `FAILED`; retryable errors show the retry events |
| Cancellation | `abort`, then wait for `agent_settled`; task → `CANCELLED` only on confirmation |
| Process hangs | Per-command deadline; on expiry the process is killed and the task fails with a timeout |
| Solo shuts down | stdin closed for an orderly Pi shutdown, then SIGTERM, then SIGKILL |

Solo never reports a task as completed because a process exited cleanly. Only
`agent_settled` plus a non-error terminal message does that.

---

## 8. Security

- Pi runs with the permissions of the Solo process and the working directory of
  the project. It is **not** sandboxed; Pi's own documentation is explicit about
  this (`vendor/16-containerization.md` covers stronger isolation).
- Solo's project path policy already constrains which directories may be opened,
  so Pi's working directory is always a directory the user deliberately chose.
- Credentials never reach the browser: the API returns only
  `{configured: true, masked: "****abcd"}`. `auth.json` is written `0600`.
- Provider error text is passed through to the user but never logged with the
  request headers, and Solo's log redactor scrubs credential-shaped strings.
- `--no-approve` by default means a project cannot silently load executable
  extensions into the Pi process.

---

## 9. Version pinning

The integration targets Pi **1.1.0**, the version in `vendor/`. Pi's RPC
protocol has remained stable across the range Solo uses, but the protocol is
verified at start-up: Solo runs `pi --version` and records it, and the Settings
UI shows the detected version next to the configured provider and model.

If a future Pi release changes the protocol, the failure is contained to
`pi_rpc.py` and `pi_events.py`.
