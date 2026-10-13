# Defect log — 2.6.1

| | |
|---|---|
| **Stage** | Orchestrator providers |
| **Date** | 2026-10-13 |
| **Defects** | D-72 … D-75 |

All four were found while adding OpenCode Go — designing against a second provider
exposed assumptions that the single-provider code had been making silently.

---

## D-72 — The mandatory session header reads as optional in the documentation

**Severity** High · **Status** Avoided · **Found by** live testing

**Finding.** OpenCode Go requires `x-opencode-session` on every inference request,
but the documentation phrases it as something a client "should" do. Omitting it is
not a degraded response — it is a 400 on every call:

```json
{"type":"error","error":{"type":"MissingSessionID","message":"Request is missing
 x-opencode-session and cannot be routed efficiently."}}
```

**Why it matters.** A provider implemented from the prose would connect, fail every
request, and present as a bad API key. Solo sends a process-stable session id and
identifies itself in the User-Agent, as the documentation also asks.

---

## D-73 — `verify_key` is OpenRouter-only

**Severity** High · **Status** Fixed

**Root cause.** The key-validation step called `GET /key`, which only OpenRouter
exposes. Running it against OpenCode Go would report a **working key as broken**.

**Fix.** The account check is now provider-specific and its absence is not a fault.
OpenCode Go validates with a real completion instead, which is the stronger check
anyway — the 2025 rule that a key is only "verified" after a real request succeeds
already applied.

---

## D-74 — The model setting was written to OpenRouter's key regardless of provider

**Severity** High · **Status** Fixed · **Found by** writing the test

**Root cause.** `PUT /orchestrator/config` wrote `values["openrouter_model"]`
unconditionally. Selecting OpenCode Go and choosing a model would have stored it
under OpenRouter, then asked Go for a model id it had never heard of — which
answers `400 Model is unavailable`, a symptom that points at the wrong thing.

**Fix.** The model is written to the active provider's own `model_setting`, and the
test asserts that both providers can hold a model simultaneously and that switching
back is exact.

---

## D-75 — Status reported OpenRouter's masked key for every provider

**Severity** Medium · **Status** Fixed

**Root cause.** `_status_payload` read `openrouter_api_key` directly, so with
OpenCode Go active the UI showed OpenRouter's mask — implying a key was configured
for a provider that had none, while hiding the one it did have.

**Fix.** Status masks the **active** provider's key.

---

## Open

| ID | Issue | Status |
|---|---|---|
| — | No OpenCode Go key available, so no live completion was run | Needs a user-supplied key |
| — | ElevenLabs balance exhausted | Unrelated, unchanged |
| D-08 | Docker build unverified | Open (environment) |
