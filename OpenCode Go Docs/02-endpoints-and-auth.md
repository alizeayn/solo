# Endpoints, authentication and errors (verified)

Everything here was confirmed against the live service.

## Base URL

```
https://opencode.ai/inference/go/v1
```

The vendor documentation names this prefix. A second prefix,
`https://opencode.ai/zen/go/v1`, **also answers identically** — both were checked
and both returned the same 39 models. Solo uses the documented one.

The API is **OpenAI-compatible**: `GET /models` and `POST /chat/completions`
under the same prefix, with an `Authorization: Bearer <key>` header.

## Authentication

`Authorization: Bearer <api key>` from <https://opencode.ai/console>.

## The required session header

```
x-opencode-session: <stable id per conversation>
```

The documentation phrases this as something a client *should* do. It is enforced:

```json
400 {"type":"error","error":{"type":"MissingSessionID",
     "message":"Request is missing x-opencode-session and cannot be routed
                efficiently. Please see https://opencode.ai/docs/go/#where-can-i-use-it"}}
```

**Every** inference request without it fails. This is the single most important
detail for an integration, because a provider wired up without it looks like a
broken API key rather than a malformed request. Solo sends a session id that is
stable for the life of the process.

The documentation also asks for an identifying User-Agent (`my-coding-agent/1.0`
rather than a library name). Solo sends `solo/<version> (coding-agent)`.

## `GET /models`

**Public.** Returns OpenAI's shape:

```json
{"object":"list","data":[{"id":"kimi-k3","object":"model","created":1791901832,"owned_by":"opencode"}]}
```

**Verified nuance:** a request with *no* `Authorization` header returns 200, but a
request with an **invalid** key returns 401 `Invalid credential`. So the endpoint
is readable without a credential, yet not usable to validate a wrong one.

## `POST /chat/completions`

Standard OpenAI chat completions.

## Errors (verified)

| Condition | Status | Message |
|---|---|---|
| No `x-opencode-session` | **400** | `Request is missing x-opencode-session and cannot be routed efficiently.` |
| Session header, no key | **401** | `Upstream request failed: Go requires a credential` |
| Session header, invalid key | **401** | `Upstream request failed: Invalid credential` |
| Session header, unknown model | **400** | `Upstream request failed: Model is unavailable.` |

Envelope:

```json
{"type":"error","error":{"type":"MissingSessionID","message":"..."}}
```

Note the double nesting: `error.message`, with a machine-readable `error.type`.
This differs from OpenRouter's `{"error":{"message":...}}` only in the extra
`type`, so one error parser handles both.
