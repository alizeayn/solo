# 17 — Phase 2 Scope: Pi Agent, Orchestrator and the State Foundation

**Stage:** Planning
**Date:** 2026-10-10
**Milestone:** Phase 2 — execute coding tasks through Chat

---

## 1. Objectives

| # | Objective | Source |
|---|---|---|
| 1 | Integrate the **Pi Agent** so coding tasks submitted through Chat actually run inside the opened project and modify real files | request |
| 2 | Integrate **Pyright** so the harness can verify what Pi changed | request |
| 3 | Configure **Pi Agent entirely from the Workspace Settings UI** — provider, credentials, validation, model discovery and selection | request |
| 4 | Configure **OpenRouter entirely from the Settings UI** and have the Orchestrator **actually use** that model for intent detection, task management, prioritisation and MVP state management | request |
| 5 | Establish a **state-management foundation** that Phases 3–5 (reasoning + voice) can extend without rebuilding | request |
| 6 | Improve the UI — responsive, polished, modern — for the Phase 2 feature set only | request |
| 7 | Fold Pi and Pyright into **Easy Installation** | request |
| 8 | Document, test, report, push | standing |

Out of scope: the voice model, the reasoning/Operator model, and a broad UI
redesign.

---

## 2. Investigation before implementation

The specification required verifying the intended tool rather than assuming it.
Findings are recorded in full in `Pi Agent Docs/20-solo-integration.md`; the four
that changed the design:

### 2.1 A fresh agent directory has **zero models** (verified)

```
PI_CODING_AGENT_DIR=<empty dir> → get_available_models → 0 models
PI_CODING_AGENT_DIR unset       → get_available_models → 436 models
```

The catalog lives in the agent directory. **Consequence:** Solo must not
override `PI_CODING_AGENT_DIR`; it reuses the user's existing Pi installation.
This single finding determined the configuration architecture.

### 2.2 `auth.json` overrides environment variables (verified)

```
auth.json = AAAA   OPENROUTER_API_KEY = BBBB
  → pi auth print-api-key --provider openrouter → AAAA
```

**Consequence:** injecting an API key as an environment variable would *not*
make Solo's configured credential effective. Solo writes Pi's `auth.json` — the
same file `/login` writes — which is also what the request asked for
("equivalent to the `/login` workflow").

### 2.3 Non-interactive modes cannot answer the project-trust prompt (documented)

Print/JSON/RPC silently skip protected project resources when the decision is
unset. **Consequence:** Solo passes an explicit `--no-approve` (configurable), so
behaviour never depends on a saved decision in `~/.pi/agent/trust.json`, and a
project cannot silently load executable extensions.

### 2.4 Provider failures arrive in the message stream, not the exit code (verified)

A rejected request produced `message_end` with `stopReason: "error"` carrying
`402: Insufficient credits`, then `agent_settled`, with the process healthy.
**Consequence:** a successful `prompt` response means *accepted*, not *finished*;
task success is derived from `agent_settled` plus a non-error terminal message.
A clean exit is never success.

### 2.5 Pyright

`pyright` 1.1.414 is installable via pip and emits `--outputjson` diagnostics
with file, range, severity, message and rule — enough for a structured UI.

---

## 3. Architectural decisions

| Decision | Choice | Rationale |
|---|---|---|
| Integration surface | **RPC mode only** (`pi --mode rpc`) | Solo is Python; the SDK is in-process TypeScript. RPC is the documented language-independent interface and isolates a Pi crash from the web app |
| Process model | **One long-lived process per project** | Pi holds context in-process, so follow-ups continue the same conversation and steering is meaningful; start-up resolves auth and the catalog, too slow per task |
| Session durability | `--no-session` | Solo's `.solo/` store is the durable, portable record. Pi's own JSONL would duplicate it |
| Harness flags | `--no-extensions`, `--no-skills`, `--no-prompt-templates`, `--no-mcp` | Reproducible; the user's extensions emitted `extension_ui_request` records a non-TUI client cannot answer |
| Credentials | Written to Pi's `auth.json` | §2.2 — the only correct option; also the `/login` equivalent |
| Agent directory | Reused, not overridden | §2.1 |
| Orchestrator fallback | Deterministic rules always present | A missing key, an outage or an invalid response must never block a task |
| Model output | Pydantic-validated structured JSON | The model classifies and plans; it never names a path or runs a command |
| Post-settle work | Asynchronous, after the terminal broadcast | A slow model must not delay telling the user a task finished |
| State location | `.solo/state/orchestration.json` | Consistent with the project model; travels with the project |

### The state foundation (objective 5)

The request listed future capabilities — conversation/project state management,
decomposition, prioritisation by dependency, summaries, voice narration, context
retention for mid-task instructions, and deciding what goes to Pi in what order.
Rather than build a pipeline that would need replacing, each was mapped onto one
durable structure:

| Future requirement | Expressed as | Implemented in Phase 2? |
|---|---|---|
| Manage conversation/project state | the state document | ✅ (extended in later phases) |
| Decompose complex requests | `queue[]` | ✅ |
| Prioritise by importance and dependency | `priority`, `depends_on`, `next_pending()` | ✅ |
| Concise summaries of Pi's work | `OrchestratorBrain.summarise` | ✅ |
| Voice explanation of progress | narrate the same summaries | interface ready |
| Retain new instructions mid-task | `notes[]` with `applied` | ✅ |
| Decide what goes to Pi, in what order | `next_pending` + `_advance_queue` | ✅ automatic |

The design rule that follows: **later phases add consumers of this state, not new
architecture.**

---

## 4. Success criteria

1. A coding task typed into Chat creates or modifies a **real file** in the
   opened project, and the file exists on disk afterwards.
2. The execution process is visible in the workspace: meaningful events, changed
   files, test results and progress summaries — not raw logs.
3. Pi's provider, credentials, model list and model selection are configurable
   entirely from Settings, with honest validation states.
4. OpenRouter is configurable from Settings, and the selected model is
   demonstrably used by the Orchestrator.
5. A prioritised, dependency-aware queue executes sequentially and retains
   instructions given mid-task.
6. Pyright reports on the changed files.
7. Pi and Pyright are installed by the existing one-command installer.
8. **No Phase 1 or 1.5 behaviour regresses**: all 286 existing checks still pass.
9. Every claim in this report is backed by a test that was actually run, with
   verified / unverified clearly separated.
