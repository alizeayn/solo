# Summary — 2.6.1

| | |
|---|---|
| **Stage** | Provider-agnostic Orchestrator |
| **Version** | 2.6.1 |
| **Date** | 2026-10-13 |

---

## A provider is a descriptor, not a branch

The Orchestrator was wired to OpenRouter **by name** — its key and model were read
directly in the brain, in five places in the API, and in the settings UI. Adding a
second provider by duplicating those reads would have produced two paths that drift
and a second one that rots.

Instead there is one `ProviderSpec` per provider: base URL, which settings hold the
key and the model, extra headers, and whether an account endpoint exists. One
transport serves both, because both speak the OpenAI dialect — and it gained only
an `extra_headers` argument. The structured-output fallback from 2.5.1, which
retries once without `response_format` on a 400, came along for free and turned out
to be exactly what a provider with no capability metadata needs.

**Adding a third provider now needs no frontend change at all**: the selector, key
field and model list are driven by the catalogue from `/api/orchestrator/providers`.

## The documentation's "should" is an "must"

OpenCode Go asks clients to send `x-opencode-session` for routing and prompt
caching. It does not merely prefer it — without the header **every** inference call
returns:

```json
400 {"type":"error","error":{"type":"MissingSessionID","message":"Request is
 missing x-opencode-session and cannot be routed efficiently."}}
```

A provider built from that prose would connect, fail every request, and present as
a broken API key. It was found by testing the live service rather than reading
about it, and it is recorded in `OpenCode Go Docs/02-endpoints-and-auth.md`.

## Three defects the second provider exposed

Designing against a second provider surfaced assumptions the first had been making
silently:

* **`verify_key` is OpenRouter-only** (`GET /key`). Run against Go it would report a
  **working key as broken**. The account check is now provider-specific.
* **The model was always written to `openrouter_model`**, so choosing a model for Go
  stored it under OpenRouter and then asked Go for an id it had never heard of —
  answering `400 Model is unavailable`, which points at the wrong thing entirely.
* **Status masked OpenRouter's key for every provider**, implying a key existed
  where it did not and hiding the one that did.

## Verification

| Suite | Result |
|---|---|
| Backend | **482 passed** (+12) — **OpenRouter did not regress** |
| Frontend | **152 passed**, typecheck clean, build succeeded |
| Live: model catalogue | ✅ 200, **39 models** |
| Live: without session header | ✅ 400 `MissingSessionID` |
| Live: with session header + dummy key | ✅ 401 `Invalid credential` — shape accepted |

## What is not verified

**No real completion was run, because no OpenCode Go key was available** — Pi's
credential store holds only OpenRouter. I confirmed the endpoint, the method, the
auth header, the mandatory session header and the error parsing against the live
service, and asserted the wiring end to end through the real container. But a
provider is not "working" until a model answers, and it has not.

**To close it:** enter an OpenCode Go key in Settings → Orchestrator, press
*Retrieve models*, pick one — `longcat-2.5-preview-free` is free and unlimited for
a limited time, so it costs nothing to prove — and run a task.

## Documentation

`OpenCode Go Docs/` (5 files) — overview and plans, the **verified** endpoint /
authentication / error reference, the observed 39-model catalogue with guidance on
which models suit an Orchestrator, and the Solo integration notes.

## Related

- [Scope 0087](../01-planning/orchestrator-providers-0087.md)
- [Implementation 0088](../02-implementation/orchestrator-providers-0088.md)
- [Testing 0089](../03-testing/orchestrator-providers-0089.md)
- [Defect log 0090](../04-defects/defect-log-0090.md)
- [Verification 0091](../05-verification/acceptance-criteria-0091.md)
