# Live-verified behaviour

What a **real API key** actually returned, recorded because three things here are
not discoverable from the documentation at all, and one documented assumption
turned out to be wrong.

Checked on 2026-10-12 against `https://api.elevenlabs.io`.

---

## 1. API keys can be scoped, and scoping is not a bad key

A restricted key authenticates successfully and then fails a **permission**
check. The two are reported differently and must not be confused:

```json
{
  "detail": {
    "type": "authentication_error",
    "code": "unauthorized",
    "message": "The API key you used is missing the permission user_read to execute this operation.",
    "status": "missing_permissions"
  }
}
```

Note `status: "missing_permissions"` inside a `401`. The HTTP status alone cannot
distinguish "this key is wrong" from "this key may not do that", so a client must
read the body — and must not tell the user to regenerate a key that works.

### Observed permission map

| Endpoint | Requires | Observed |
|---|---|---|
| `GET /v1/models` | *(none observed)* | **200**, 11 models |
| `POST /v1/text-to-speech/{voice_id}` | `text_to_speech` | **200**, valid MP3 |
| `POST /v1/speech-to-text` | `speech_to_text` | **200**, correct transcript |
| `GET /v1/user` | `user_read` | **401** `missing_permissions` |
| `GET /v2/voices` | `voices_read` | **401** `missing_permissions` |
| `GET /v1/voices` | `voices_read` | **401** `missing_permissions` |

**Design consequence.** A key that can *speak* may not be able to *list voices*
or *read the account*. So validation must not depend on `user_read`, and voice
selection must work without `voices_read` — by setting a voice id directly.

## 2. The free plan restricts library voices

Synthesis is separately gated by plan. Two voices worked; five returned
`402 paid_plan_required`:

```
{"detail":{"code":"paid_plan_required",
 "message":"Free users cannot use library voices via the API. Please upgrade your subscription to use this voice."}}
```

| Voice id | Result |
|---|---|
| `EXAVITQu4vr4xnSDxMaL` | **200** — usable |
| `pNInz6obpgDQGcFmaJgB` | **200** — usable |
| `21m00Tcm4TlvDq8ikWAM`, `AZnzlk1XvdvUeBnXmlld`, `MF3mGyEYCl7XYWbV9V6O`, `TxGEqnHWrfWFTfGW9XjX`, `yoZ06aMxZJJ28mfd3POQ` | **402** — library voice, paid plan required |

A `402` is therefore a *plan* problem, not a *configuration* problem, and the
API's own message is the most useful thing to show.

## 3. Errors arrive as a nested object

Every failure observed used this envelope:

```json
{"detail": {"type": "...", "code": "...", "message": "...", "status": "..."}}
```

Reading only a string or a list from `detail` discards the message and produces a
generic error — which is what happened before this was fixed. A client that has
not handled the nested object will misreport **every** failure it encounters.

## 4. Round trip

```
"text": "Solo live voice check."   →  POST /v1/text-to-speech/EXAVITQu4vr4xnSDxMaL/stream
                                   →  200, 20,524 bytes, ID3 (MP3)
                                   →  POST /v1/speech-to-text  (model_id=scribe_v2)
                                   →  200, {"text": "Solo voice check", "language_code": "eng"}
```

Both capabilities the integration depends on work with the same key.

## 5. Model catalogue correction

`eleven_turbo_v2_5` **exists** — a TTS model with a 40,000-character limit — even
though the documentation's model table does not list it. An earlier revision of
`02-models.md` claimed it did not exist. See that file for the correction and the
full list of 11 models returned.

The lesson generalises: documentation drifts, entitlements differ per account, so
the client discovers rather than validating against a list.
