# Scope — OpenCode Go as a second Orchestrator provider

| | |
|---|---|
| **Stage** | 2.6.1 — provider-agnostic Orchestrator |
| **Date** | 2026-10-13 |

## Requested

Add **OpenCode Go** alongside OpenRouter so a key can be entered, models retrieved
the same way, and the Orchestrator's model chosen — without removing or breaking
OpenRouter.

## What existed

The Orchestrator was wired to OpenRouter by name. `openrouter_api_key` and
`openrouter_model` were read directly in `orchestrator_brain`, in `api/orchestrator.py`
in five places, and in the settings UI. OpenCode Go appeared only as a **Pi Agent**
provider (`pi_config.py`), never as an Orchestrator one.

Adding a second provider by duplicating those reads would have produced two code
paths that drift, and the second one would rot.

## What was learned from the vendor

OpenCode Go is **OpenAI-compatible**, so it needed a provider *descriptor* rather
than a second transport. Two findings shaped the work:

1. **`x-opencode-session` is mandatory**, though the documentation phrases it as a
   request ("your client *should* send"). Without it every call is a 400. A
   provider wired from the prose alone would look like a broken key.
2. **There is no account endpoint.** OpenRouter has `GET /key`; Go does not, so a
   shared "validate the key" step would have to become provider-specific or it
   would report a working Go key as broken.

Both are recorded in [`OpenCode Go Docs/`](../../OpenCode%20Go%20Docs/README.md).

## Principle

A provider is a **descriptor**, not a branch. Everything that differs between them
— base URL, which settings hold the key and the model, extra headers, whether an
account endpoint exists — belongs in one table.

## Related

- [Implementation 0088](../02-implementation/orchestrator-providers-0088.md)
- [Defect log 0090](../04-defects/defect-log-0090.md)
