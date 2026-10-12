# Authentication

## The API key

Every request carries the key in a header:

```
xi-api-key: <api-key>
```

It is **not** a `Bearer` token and not a query parameter. (ElevenLabs also
accepts `Authorization: Bearer <key>` on some endpoints, but `xi-api-key` is what
the documentation shows throughout and is what Solo sends.)

Some endpoints additionally accept a single-use `?token=` created via
`POST /v1/single-use-token/batch_scribe`, for browser clients that must not hold
the API key. Solo does not use this: the key never leaves the backend.

## Verifying a key

`GET /v1/user` returns the account for the key. This is the cheapest real check —
it proves the key is accepted by the service rather than merely well-formed.

- `200` — key is valid.
- `401` / `403` — key rejected.

Solo maps those to `configured` / `failed` and never reports a key as verified
without a successful response.

## Base URLs

| Region | Base URL |
|---|---|
| Production (default) | `https://api.elevenlabs.io` |
| US | `https://api.us.elevenlabs.io` |
| EU residency | `https://api.eu.residency.elevenlabs.io` |
| India residency | `https://api.in.residency.elevenlabs.io` |
| Singapore residency | `https://api.sg.residency.elevenlabs.io` |

Solo defaults to `https://api.elevenlabs.io` and exposes it as configuration
(`ELEVENLABS_BASE_URL`) so a residency-pinned deployment can change one value.

## Key handling in Solo

- Stored encrypted at rest (`SecretCipher`), alongside the OpenRouter key.
- Never returned by any endpoint: settings expose only
  `{"configured": true|false, "name": "...", "detail": "..."}`.
- Never logged. `ConnectionTestResult.detail` carries a status code or an
  exception *type*, never the key.
