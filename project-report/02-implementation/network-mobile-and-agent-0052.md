# Implementation — 2.5.1

| | |
|---|---|
| **Stage** | Remote access, TLS, Orchestrator and Pi Agent fixes |
| **Date** | 2026-10-12 |

---

## A. The Orchestrator was silently dead

**Symptom.** The Orchestrator never influenced a single routing decision.

**Investigation.** The brain logged only:

```
WARNING orchestrator classification failed: Provider returned error
```

Reproducing the exact call against the user's own account isolated it:

| Call | Result |
|---|---|
| `complete_json` **with** `response_format` | **400 `Provider returned error`** |
| `complete_json` **without** it | **200, valid JSON** |

`OrchestratorBrain.classify()` returned `None` for **every** message, so routing
always fell back to the deterministic rules router. The panel and the settings all
said the Orchestrator was configured and enabled — and it was. Only the transport
was failing, and the failure was reported as a generic sentence.

The configured model, `apodex/apodex-1.1-mini:free`, **advertises**
`supports_structured_output: true` in OpenRouter's catalogue but rejects the
parameter at request time. So the catalogue flag could not be trusted either.

**Fix.** `complete_json` retries **once** without `response_format` on a 400 and
describes the required keys in the prompt instead.

```
INFO model apodex/apodex-1.1-mini:free rejected response_format (HTTP 400); retrying without it
```

Two details that matter:

* **Only 400.** A 401, 402, 429 or 5xx is surfaced unchanged, because retrying an
  auth or quota failure would hide the real cause.
* **Never the raw schema.** Embedding the JSON Schema made the model return *the
  schema document* instead of an instance of it. `_schema_instructions()` lists
  each required key and its allowed values in prose. Enum values are listed, never
  demonstrated, because an example object silently biases the field to its first
  value.

Validation is unchanged: the reply must still parse into a JSON object.

## B. Pi ran with a phantom model

Pi reports the literal string `"unknown"` when its agent directory has no model
selected. The guard tested only for a *missing* id, so `"unknown"` passed as a
real model. The run started, then failed deep inside the provider with
`No API key found for the selected model`, while the Activity panel said:

```
Pi is running unknown from Solo's own runtime
```

**Fix.** Treat `unknown` / `none` / `null` as "no model" and emit the existing
actionable event before starting:

```
Pi has no model selected. Choose a provider and model in Settings → Pi Agent.
```

Verified with a fresh runtime: the event now reaches the Activity stream.

## C. Questions are recorded as completed tasks

`_answer_question` creates a `QUESTION` task and sets it to `COMPLETED`
immediately, storing the answer as its summary. That is intentional — the row is a
container for the reply — but the UI presents it exactly like a coding task.

So typing "hi" or "whats yore model name?" produces a task row reading
**Completed** with no agent run, which reads as *"my task finished and nothing
happened"*. The user's own database shows this clearly: 9 `QUESTION`/`COMPLETED`
rows including `"hi"` and `"are you ready for start project?"`, plus 2 `CODING`
rows that genuinely failed on provider limits.

**Status: identified, not fixed.** Changing task semantics is a product decision
and the fix belongs with the Activity/milestone presentation work.

## D. Network access and TLS

**The LAN already worked.** `app_host` defaults to `0.0.0.0` and the API is
same-origin, so a phone reaches it with no change. Verified:

```
LISTEN  0  2048  0.0.0.0:8080
http://127.0.0.1:8080   -> 200
http://172.16.1.60:8080 -> 200
```

What did **not** work was voice from a phone, and the reason is not obvious:
browsers expose the microphone only in a **secure context**. Over
`http://<lan-ip>` it is refused, so the session cannot start at all.

**Added:**

* `APP_HOST` documents the local-only (`127.0.0.1`) versus LAN (`0.0.0.0`) choice.
* `SOLO_ALLOWED_HOSTS` — opt-in Host allow-list (`TrustedHostMiddleware`). Empty by
  default, because the address a phone uses is not known in advance; set it when
  Solo is reachable from an untrusted network.
* `SSL_CERTFILE` / `SSL_KEYFILE` — Solo terminates TLS itself.
* `./solo.sh cert` — generates a self-signed certificate whose SAN covers
  `localhost`, `127.0.0.1`, the hostname and the LAN IP, and turns HTTPS on.
* `./solo.sh access` — explains how each device reaches Solo, and states plainly
  whether voice will work there and why.

## Files

`backend/app/services/openrouter.py` (`complete_json`, `_schema_instructions`,
`_structured_output_rejected`), `backend/app/adapters/pi_agent.py`,
`backend/app/config.py`, `backend/app/__main__.py`, `backend/app/main.py`,
`solo.sh` (`cert`, `access`, TLS-aware URLs), `backend/tests/test_orchestration_layer.py`.
