# Testing — Orchestrator providers

| | |
|---|---|
| **Stage** | 2.6.1 |
| **Date** | 2026-10-13 |

## Suites

| Suite | Result |
|---|---|
| Backend | **482 passed** (470 + 12 new) |
| Frontend | **152 passed**, 20 files |
| Frontend typecheck | clean |
| Frontend build | succeeded |

The 470 pre-existing tests are the important number: **OpenRouter did not
regress.** The provider layer was added underneath it and every existing
assertion still holds.

## New tests (`tests/test_orchestrator_providers.py`)

| Test | Guards |
|---|---|
| both providers are registered | the catalogue is what it claims |
| **an unknown provider falls back rather than raising** | a stale setting cannot brick the Orchestrator |
| each provider points at its own settings | a shared key/model would cross-configure them |
| the catalogue describes each provider for the UI | the selector is data-driven |
| **OpenCode Go sends the session header its API requires** | the mandatory header |
| OpenRouter needs no extra headers | the abstraction does not leak into the default |
| the client actually sends the provider headers | the registry is useless if the transport drops them |
| OpenRouter keeps its attribution headers | `HTTP-Referer` / `X-Title` survive |
| the error type is shared between providers | callers never branch on provider |
| **the brain uses OpenCode Go when it is selected** | end-to-end through the real container: base URL, session header, reported provider |
| **switching provider does not disturb the other** | both keys and models coexist; switching back is exact |
| the OpenCode Go key is encrypted at rest | protection does not depend on the provider |

## Verified live against OpenCode Go

No key was available, so these are the checks that need none — and they cover the
two things most likely to be wrong:

| Check | Result |
|---|---|
| `GET /inference/go/v1/models` with no credential | **200, 39 models** |
| Inference without `x-opencode-session` | **400** `Request is missing x-opencode-session…` |
| Inference with the session header and a dummy key | **401** `Upstream request failed: Invalid credential` |
| Inference with the session header and an unknown model | **400** `Upstream request failed: Model is unavailable.` |
| `https://opencode.ai/zen/go/v1/models` | 200, identical list |

The third row is the useful one: it proves the endpoint, method, auth header and
parsing are all accepted, so **a real key is the only missing piece**.

## Not verified

| Gap | Reason |
|---|---|
| A real completion through OpenCode Go | **No OpenCode Go key was available.** Pi's credential store holds only OpenRouter. |
| Model listing through Solo's client | `/models` rejects an *invalid* key (401) while allowing *no* key, so the client — which always sends one — needs a valid key to list |
| A full task run on OpenCode Go | Same |
