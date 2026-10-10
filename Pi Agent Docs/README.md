# Pi Agent Documentation

Local reference for integrating **Pi Agent** (`@earendil-works/pi-coding-agent`,
CLI name `pi`) into Solo.

Why this folder exists: Pi's protocol details are load-bearing and easy to get
wrong from memory. Keeping an authoritative copy here means the integration can
be maintained without re-fetching documentation, and it pins the exact version
the integration was written against.

| | |
|---|---|
| **Pi version documented** | `1.1.0` |
| **Package** | `@earendil-works/pi-coding-agent` |
| **CLI binary** | `pi` |
| **Local docs source** | `…/lib/node_modules/@earendil-works/pi-coding-agent/docs/` |
| **Upstream** | <https://pi.dev/docs/latest/> |

---

## Read this first

| Document | Why it matters for Solo |
|---|---|
| **[20-solo-integration.md](20-solo-integration.md)** | **Start here.** Solo's integration design plus the empirical findings that shaped it (credential precedence, agent-dir isolation, project trust). |
| [vendor/02-rpc-protocol.md](vendor/02-rpc-protocol.md) | The wire protocol: JSONL framing, correlation, lifecycle, shutdown |
| [vendor/03-rpc-commands.md](vendor/03-rpc-commands.md) | Every stdin command and its response |
| [vendor/04-json-event-stream.md](vendor/04-json-event-stream.md) | The stdout event stream Solo translates into UI progress |
| [vendor/08-providers-and-auth.md](vendor/08-providers-and-auth.md) | Provider IDs and API-key environment variables |
| [vendor/09-models.md](vendor/09-models.md) | Model catalog, custom endpoints, `models.json` |
| [vendor/12-security-and-trust.md](vendor/12-security-and-trust.md) | Project trust, and why it needs explicit handling in non-interactive modes |

---

## Orientation

**What Pi is.** A coding agent CLI with `read`, `bash`, `edit` and `write`
tools, session management, and four interfaces that share one agent core:
interactive TUI, print, JSON, and RPC.

**Why Solo uses RPC.** Solo is Python. Pi's SDK is TypeScript and in-process; the
RPC mode is the language-independent, process-isolated interface designed for
exactly this case. Solo keeps Pi at arm's length behind a subprocess boundary so
a Pi crash or hang cannot take the web application with it.

**The two halves of the protocol.**

```
Solo ──stdin──►  command   (prompt, steer, abort, get_state, bash, …)
Solo ◄─stdout──  response  (correlated by "id")
Solo ◄─stdout──  event     (agent/turn/message/tool/queue/compaction/retry)
```

Diagnostics go to **stderr**; stdout is protocol only. A successful `prompt`
response means *accepted*, not *finished* — `agent_settled` is what means "Pi
will not continue automatically".

**What Solo reads from Pi.**

| Need | Mechanism |
|---|---|
| Which providers exist | `get_available_models` (RPC) / `pi --list-models` |
| Is a provider authenticated | `pi auth check --provider X --json` |
| Available models for a provider | `get_available_models`, filtered by `provider` |
| Progress of a coding task | session events on stdout |
| Real file changes | `tool_execution_*` events for `write`/`edit` |

**What Solo writes to Pi.**

| Need | Mechanism |
|---|---|
| Provider credential | `<agent-dir>/auth.json`, mode `600` — the same file `/login` writes |
| Provider/model selection | `--provider` / `--model` process arguments |

---

## Document map

```
Pi Agent Docs/
├── README.md                     this index
├── 20-solo-integration.md        Solo's design + empirical findings
└── vendor/                       verbatim upstream reference (v1.1.0)
    ├── 01-how-pi-works.md            agent loop, context, sessions
    ├── 02-rpc-protocol.md            RPC wire protocol
    ├── 03-rpc-commands.md            command + response reference
    ├── 04-json-event-stream.md       event stream reference
    ├── 05-message-types.md           AgentMessage / content blocks
    ├── 06-session-format.md          session JSONL format
    ├── 07-sessions.md                session management
    ├── 08-providers-and-auth.md      providers, env vars, auth.json
    ├── 09-models.md                  model catalog and custom endpoints
    ├── 10-configuration.md           agent dir and project .pi dir
    ├── 11-settings.md                settings.json reference
    ├── 12-security-and-trust.md      trust model and isolation
    ├── 13-environment-variables.md   PI_* variables
    ├── 14-cli-reference.md           every CLI flag
    ├── 15-sdk.md                     in-process TypeScript SDK
    ├── 16-containerization.md        running Pi isolated
    ├── 17-extensions.md              extensions
    ├── 18-skills.md                  skills
    └── 19-codemode.md                codemode tool
```

## Refreshing this folder

When Pi is upgraded, re-copy `vendor/` from the installed package and update the
version note above:

```bash
DOCS=$(dirname "$(readlink -f "$(command -v pi)")")/../docs   # adjust to the install layout
cp "$DOCS"/*.md "Pi Agent Docs/vendor/"
```
