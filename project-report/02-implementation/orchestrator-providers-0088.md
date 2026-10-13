# Implementation — provider-agnostic Orchestrator

| | |
|---|---|
| **Stage** | 2.6.1 |
| **Date** | 2026-10-13 |

---

## 1. One descriptor per provider

`app/services/orchestrator_providers.py` holds a `ProviderSpec` for each:

| | OpenRouter | OpenCode Go |
|---|---|---|
| Base URL | `https://openrouter.ai/api/v1` | `https://opencode.ai/inference/go/v1` |
| Key setting | `openrouter_api_key` | `opencode_go_api_key` |
| Model setting | `openrouter_model` | `opencode_go_model` |
| Extra headers | none | `x-opencode-session`, `User-Agent` |
| Account endpoint | `GET /key` | none |

**One transport serves both.** `OpenRouterClient` gained an `extra_headers`
argument and nothing else. That is the whole point: the structured-output fallback
added in 2.5.1 — retry once without `response_format` on a 400 — is exactly what a
second provider needs, and duplicating the client would have duplicated that too.

## 2. The session header

```python
def opencode_go_headers(session_id: str) -> dict[str, str]:
    return {"x-opencode-session": session_id, "User-Agent": "solo/2.6.1 (coding-agent)"}
```

`OrchestratorBrain` creates a `uuid4` session id once per process. Go routes and
caches on it, and rejects a request without one:

```json
400 {"type":"error","error":{"type":"MissingSessionID",
     "message":"Request is missing x-opencode-session and cannot be routed efficiently."}}
```

## 3. Per-provider settings, and why

Keys and models are separate settings rather than one shared pair. A single
`openrouter_model` would apply OpenRouter's model id to OpenCode Go, which answers
`400 Model is unavailable` — a confusing symptom for what is really a
configuration mix-up. The masked key shown in status is the **active** provider's.

## 4. Unknown providers fall back

```python
def get_provider(provider_id):
    return PROVIDERS.get((provider_id or "").strip().lower(), PROVIDERS[DEFAULT_PROVIDER])
```

A saved setting can name a provider a later release removed. Raising would leave
the Orchestrator unreachable from the UI that would fix it.

## 5. API

| Endpoint | Change |
|---|---|
| `GET /orchestrator/providers` | **New** — per-provider readiness, so the UI can say "OpenRouter is ready, Go needs a key" |
| `PUT /orchestrator/config` | Accepts `provider`; writes the model to the **active** provider's setting |
| `GET /orchestrator/models` | Uses the active provider |
| `GET /orchestrator/status` | Adds `provider`, `provider_label`, `base_url` |
| `POST /orchestrator/test` | Provider-aware; skips `GET /key` for Go |

## 6. UI

The provider selector, key field and model list are all driven by the catalogue
from `/providers` — the component reads `key_setting` and `model_setting` rather
than naming OpenRouter. Switching provider clears the model list and re-reads
status, because all three belong to whichever provider is active. **Adding a third
provider now needs no frontend change at all.**

## Also

`opencode_go_api_key` is encrypted at rest: which provider is active must not
change how well a credential is protected.

## Documentation

`OpenCode Go Docs/` — overview, the verified endpoint/auth/error reference, the
observed 39-model catalogue with guidance on which model suits an Orchestrator,
and the integration notes.
