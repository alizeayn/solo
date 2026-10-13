# Solo integration

## Where it plugs in

The Orchestrator (`app/services/orchestrator_brain.py`) asks a model to classify
intent, plan steps, summarise progress and phrase milestones. Which company serves
that model is a **setting**, not a code path.

```
orchestrator_provider = "openrouter" | "opencode_go"
```

`app/services/orchestrator_providers.py` holds one `ProviderSpec` per provider,
describing everything that differs:

| | OpenRouter | OpenCode Go |
|---|---|---|
| Base URL | `https://openrouter.ai/api/v1` | `https://opencode.ai/inference/go/v1` |
| Key setting | `openrouter_api_key` | `opencode_go_api_key` |
| Model setting | `openrouter_model` | `opencode_go_model` |
| Extra headers | none | `x-opencode-session`, `User-Agent` |
| Account endpoint | `GET /key` | none |

Both speak the OpenAI chat-completions dialect, so **one transport serves both**
(`app/services/openrouter.py`). It gained an `extra_headers` argument and nothing
else — including the `complete_json` structured-output fallback, which is exactly
what an integration like this needs, since Go's catalogue advertises no
capabilities at all.

## Adding a third provider

1. Add a `ProviderSpec` to `PROVIDERS`.
2. Add its key to `SECRET_SETTING_KEYS` and its model to `PLAIN_SETTING_KEYS` in
   `app/domain.py`.
3. Add the fields to `SettingsUpdate` and `SettingsOut`.

The UI reads the catalogue from `GET /api/orchestrator/providers`, so it needs no
change: the provider selector, key field and model list are all driven by
`key_setting` and `model_setting`.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/orchestrator/providers` | Every provider, with per-provider readiness |
| `PUT /api/orchestrator/config` | Switch provider, or set a model for it |
| `GET /api/orchestrator/models` | Models from the **active** provider |
| `GET /api/orchestrator/status` | Includes the active provider and its base URL |
| `POST /api/orchestrator/test` | Validates the active provider's key and model |

## Design decisions

* **One source of truth per provider.** Keys and models are per-provider settings.
  A single shared `openrouter_model` would apply OpenRouter's id to OpenCode Go —
  which answers `400 Model is unavailable`.
* **Unknown provider falls back, never raises.** A saved setting can name a
  provider a later release removed; raising would leave the Orchestrator
  unreachable from the UI that fixes it.
* **The account check is provider-specific.** Only OpenRouter has `GET /key`.
  Asking Go for it would report a working key as broken, so Go skips that step and
  validates with a real completion instead.
* **Keys are encrypted regardless of provider.** Which provider is active must not
  change how well a credential is protected.
* **The session id is stable for the process.** Go routes and caches on it.
