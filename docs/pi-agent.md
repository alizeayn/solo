# Pi Agent integration

How Solo drives the Pi coding agent, and how to configure it without a terminal.

Full protocol reference: [`Pi Agent Docs/`](../Pi%20Agent%20Docs/) — a local copy
of Pi's own documentation for version **1.1.0**, plus
[`20-solo-integration.md`](../Pi%20Agent%20Docs/20-solo-integration.md) with the
integration design and the empirical findings behind it.

---

## 1. Where things live

| Concern | Module |
|---|---|
| **Solo's own runtime: install, locate, isolate, verify** | `backend/app/services/pi_runtime.py` |
| Transport: launch, JSONL framing, correlation, shutdown | `backend/app/adapters/pi_rpc.py` |
| Process-per-project lifecycle, run reservation, restart | `backend/app/adapters/pi_session.py` |
| Pi records → Solo's normalised events | `backend/app/adapters/pi_events.py` |
| The `CodingAgentAdapter` implementation | `backend/app/adapters/pi_agent.py` |
| Providers, credentials, model discovery, validation | `backend/app/services/pi_config.py` |
| Settings-UI endpoints | `backend/app/api/pi.py` |

Nothing outside `adapters/pi_*.py` and `services/pi_config.py` knows a Pi record
shape or a Pi command name.

---

## 2. Solo owns its Pi Agent

Solo never uses the Pi Agent installed on the host. It installs, owns and invokes
its own copy:

```
<data>/pi-runtime/          npm prefix — Solo's Pi Agent installation
│   node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js
│   runtime.json            install manifest (version, node path, timestamps)
└──
<data>/pi/agent/            PI_CODING_AGENT_DIR — Solo's Pi configuration
    auth.json               credentials entered in Solo's Settings UI
    settings.json           defaultProjectTrust=never, no telemetry
    models-store.json       Solo's own fetched model catalog
```

| Guarantee | How |
|---|---|
| The executable is **never** resolved through `PATH` | `resolve_argv()` returns an absolute interpreter plus an absolute script, or nothing |
| `~/.pi/agent` is never read or written | the agent directory always resolves inside Solo's data directory |
| Every subprocess gets Solo's configuration | `PI_CODING_AGENT_DIR` is always set to Solo's own directory |
| A bare command name is refused | `PI_EXECUTABLE=pi` is rejected and reported, because that is the silent fallback this design exists to prevent |

Subprocesses are spawned as `node <cli.js>` rather than the `node_modules/.bin/pi`
shim. The shim's shebang is `#!/usr/bin/env node`, which would need `node` on
`PATH`; passing the resolved Node binary explicitly means the only external
requirement is a Node installation, discovered once and recorded in the manifest.

**Does isolation cost anything?** No. A fresh agent directory reports no models
only because it is *unauthenticated*. With a credential stored through Solo,
the package's bundled provider catalogs resolve: a clean agent directory with
one OpenRouter credential reports 401 models. (An earlier version of Solo reused
the host's configuration on the mistaken belief that a fresh directory could
never have a catalog.)

## 3. Process model

**One long-lived `pi --mode rpc` subprocess per project**, started on demand and
reused. Pi keeps conversation context in the process, so a follow-up instruction
continues the same conversation instead of starting over, and steering is
meaningful. Sessions are keyed by the resolved project directory.

```
pi --mode rpc --no-session --no-approve --no-extensions --no-skills
   --no-prompt-templates --no-mcp [--provider P] [--model M] [--thinking L]
cwd = <project root>
```

| Flag | Why |
|---|---|
| `--mode rpc` | JSONL bidirectional control |
| `--no-session` | Solo's `.solo/` store is the durable record; Pi keeps context in-process |
| `--no-approve` (default) | Pi cannot show a trust prompt in RPC mode, so Solo decides explicitly. Configurable in Settings |
| `PI_CODING_AGENT_DIR` | Always Solo's own directory — never the host's |
| `--no-extensions` etc. | A predictable harness with no unanswerable `extension_ui_request` records |
| `--provider` / `--model` | The selection made in Solo's Settings UI |

---

## 4. Configuring Pi from the Settings UI

**Settings → Pi Agent.**

| Step | Action | What happens behind it |
|---|---|---|
| 1 | Choose a provider | The list is Pi's own catalog plus a curated list of providers Pi supports but has no models for yet, so a manual model ID is always possible |
| 2 | Paste the API key, **Save credential** | Written to Pi's `auth.json` (mode `600`) — the same file `/login` writes |
| 3 | **Check configuration** | Runs `pi auth check --provider X --json` |
| 4 | **Verify with a real request** | Sends one minimal completion through Pi, which is the only thing that proves the provider *accepts* the credential |
| 5 | **Discover models** | RPC `get_available_models`, filtered by provider |
| 6 | **Refresh catalog** | Runs `pi update --models` |
| 7 | Pick a model, **Save selection** | Persisted as `pi_provider` / `pi_model` and passed to every new Pi process |

### Why Solo writes to `auth.json`

An existing `auth.json` entry **takes precedence over a provider environment
variable** (verified against Pi 1.1.0). Injecting `OPENROUTER_API_KEY` would
therefore *not* make the credential chosen in Solo effective. Writing
`auth.json` — Solo's own file, inside Solo's agent directory — is the only way to
guarantee that what you configure is what Pi uses, and it is exactly what
`/login` does. Saving a credential also refreshes Solo's model catalog, so the
isolated installation becomes usable without any terminal step.

### Installing and repairing

`./solo.sh install` installs the runtime, and **Settings → Pi Agent** has
*Install / repair* and *Verify runtime*. A repair is a forced reinstall; a verify
starts the runtime and runs a command, which is the only thing that sets the
`verified` state.

### Three honest states

The UI never conflates these:

| State | Meaning |
|---|---|
| **not configured** | Pi reports no credential for this provider |
| **configured** | A credential is stored and Pi reports it ready — but no real request has been made |
| **verified** | A real completion succeeded with the selected model |

---

## 5. Event translation

Solo's UI never sees a Pi record. `pi_events.py` maps them onto the same small
vocabulary the simulator uses, so the activity panel, the event store and the
WebSocket are unchanged by the backend swap.

| Pi record | Solo event |
|---|---|
| `agent_start` | `run.started` |
| `tool_execution_start` (`write`/`edit`) | `file.changed` (path made project-relative) |
| `tool_execution_start` (`read`/`grep`/`bash`/…) | `tool.started` |
| `tool_execution_end` (test-looking command) | `test.result` |
| `tool_execution_end` `isError` | `error` |
| `message_end` with `stopReason: error` | `error`, with the provider's own message |
| completed assistant text | `assistant.message` (streaming deltas coalesced) |
| `agent_settled` | `run.finished` → terminal task status |
| `compaction_*`, `auto_retry_*`, `queue_update` | `progress.summary` |

**Thinking blocks are discarded.** Solo shows observable tool activity and
user-facing summaries, never private chain-of-thought. Streaming text is
coalesced so one response does not become hundreds of stored rows.

---

## 6. Failure handling

| Situation | Behaviour |
|---|---|
| `pi` not installed | Backend reports unavailable; the simulator remains available |
| No model selected | A single clear error event, no subprocess work |
| Provider 401/402/429/5xx | The provider's message is surfaced verbatim; the task fails truthfully |
| Process crash | Detected immediately (not after the run timeout); the task fails with the captured stderr tail |
| Malformed protocol record | Logged and skipped; the stream continues |
| Cancellation | `abort`, then wait for `agent_settled`; `CANCELLED` only on confirmation |
| Solo shutdown | stdin closed for an orderly Pi shutdown, then SIGTERM, then SIGKILL |

A clean process exit is never treated as success. Only `agent_settled` plus a
non-error terminal message completes a task.

---

## 7. Security notes

- Pi runs with the permissions of the Solo process, in a directory the user
  deliberately opened. Solo's path policy already constrains which directories
  those can be. Pi is **not** sandboxed; see Pi's own
  [`containerization.md`](../Pi%20Agent%20Docs/vendor/16-containerization.md).
- Solo's runtime is separate from any Pi on the machine, so configuring Solo can
  never break a desktop Pi workflow — verified by hashing `~/.pi` before and
  after a credential save: byte-for-byte unchanged.
- Credentials never reach the browser: the API returns only
  `{configured: true}` and the provider's own readiness status.
- `auth.json` is written atomically with mode `600`.
- Project-local Pi resources are **not trusted by default**, so a project cannot
  silently load executable extensions into the agent process.
- Provider error text is shown to the user but the log redactor still scrubs
  credential-shaped strings.

---

## 8. Testing

| Layer | How |
|---|---|
| **Isolation** | `backend/tests/test_pi_runtime.py` — 20 tests: PATH is never used even when a global `pi` exists, the agent directory is never `~/.pi/agent`, every subprocess gets Solo's environment, the installer writes into Solo's own prefix, and a decoy `~/.pi/agent` is proven untouched |
| Protocol, translation, adapter | `backend/tests/test_pi_integration.py` — a protocol-accurate fake (`tests/fixtures/fake_pi`) exercises real subprocesses, real pipes, real framing and correlation, deterministically and without credentials |
| Configuration service and API | `backend/tests/test_checks_and_api_pi.py` |
| Real model | `./scripts/e2e-live.sh` — submits a coding task through Chat and asserts the file really exists on disk |

The fake covers success, provider error, cancellation, crash, malformed records
and a missing model. The live script is the only test that proves a *model*
responds, and it skips itself when Pi or a credential is unavailable.
