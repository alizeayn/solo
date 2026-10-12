# Models

## Discovery

```
GET https://api.elevenlabs.io/v1/models
xi-api-key: <key>
```

Returns a list of `ModelResponseModel`:

| Field | Meaning |
|---|---|
| `model_id` | The identifier to send as `model_id` when synthesising |
| `name` | Human-readable name |
| `can_do_text_to_speech` | Whether the model can synthesise speech |
| `can_do_voice_conversion` | Whether it can convert voices |
| `can_be_finetuned` | Whether it can be fine-tuned |
| `can_use_style` / `can_use_speaker_boost` | Request options it honours |
| `serves_pro_voices` | Whether it serves professional voice clones |
| `maximum_text_length_per_request` | Hard character limit per request |
| `languages` | Supported languages (`language_id`, `name`) |
| `token_cost_factor`, `model_rates.character_cost_multiplier` | Cost |
| `requires_alpha_access` | Whether the account needs alpha access |
| `description` | Free-text description |

**This endpoint is real discovery**: it reflects the models the *configured
account* can use, including alpha/beta models that a static list would miss. Solo
therefore lists models from the API rather than hardcoding a catalog, and it
flags each one with `can_do_text_to_speech` so a speech-input-only model is never
offered as a voice for output.

## Known model IDs (documentation, 2026-10-11)

Text to speech:

| Model ID | Notes |
|---|---|
| `eleven_v4` | Most emotive; 10,000 char limit; 90+ languages |
| `eleven_v4_turbo` | Realtime, ~100 ms median latency; audio tags |
| `eleven_v3` | Expressive; 5,000 char limit; 70+ languages |
| `eleven_v3_conversational` | Realtime, ~280 ms; audio tags |
| `eleven_multilingual_v2` | Stable long-form; 10,000 char limit; 29 languages |
| `eleven_flash_v2_5` | Fastest and cheapest; ~75 ms; 40,000 char limit; 32 languages |
| `eleven_ttv_v3` | Text-to-*voice* design, not speech synthesis |

Speech to text:

| Model ID | Notes |
|---|---|
| `scribe_v2` | State of the art; 90+ languages; diarization; timestamps |
| `scribe_v2_realtime` | Realtime recognition; ~150 ms latency |
| `scribe_v2_medical` | Fine-tuned for clinical audio |

### What the live API actually returned

`GET /v1/models` on 2026-10-12, with a real key, returned **11 models**:

| Model ID | TTS | Max characters |
|---|---|---|
| `eleven_v4` | yes | 10,000 |
| `eleven_v4_turbo` | yes | 10,000 |
| `eleven_v3` | yes | 5,000 |
| `eleven_v3_conversational` | yes | 5,000 |
| `eleven_multilingual_v2` | yes | 10,000 |
| `eleven_flash_v2_5` | yes | 40,000 |
| `eleven_turbo_v2_5` | yes | 40,000 |
| `eleven_turbo_v2` | yes | 30,000 |
| `eleven_flash_v2` | yes | 30,000 |
| `eleven_english_sts_v2` | no | 5,000 |
| `eleven_multilingual_sts_v2` | no | 10,000 |

Note the two `_sts_` models: they are speech-to-speech, so `can_do_text_to_speech`
is false and they must never be offered for spoken output.

### A correction to an earlier claim

An earlier revision of this file stated that **`eleven_turbo_v2_5` does not
exist**. **That was wrong.** The live API returns it, and it is a full
text-to-speech model with a 40,000-character limit. The model catalog table in
the documentation simply does not list it. The error is recorded rather than
quietly deleted, because it is the clearest possible demonstration of the point
below.

What is still true: there is **no `eleven_v4_conversational`**. The realtime v4
family member is `eleven_v4_turbo`; a conversational variant exists only for v3.

### Why the UI discovers rather than validates against a list

A hardcoded catalogue would have been wrong in **both** directions: it would have
hidden a real model (`eleven_turbo_v2_5`) *and* offered one that does not resolve
(`eleven_v4_conversational`). Documentation drifts; the API is the account's
actual entitlement. Discovery, not a list, is what the UI uses.

## Choosing a default

Solo defaults to a model whose latency suits conversational feedback rather than
to the highest-quality one. `eleven_flash_v2_5` (~75 ms) is the default for
spoken progress, because a milestone that arrives seconds late is worse than one
that sounds slightly less rich. The selected model is always shown in Settings
and is configurable.
