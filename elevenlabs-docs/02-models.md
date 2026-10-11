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

### Versions that do **not** exist

Checked deliberately, because the request named them as possibilities:

- There is **no `eleven_v4_conversational`**. The realtime v4 family member is
  `eleven_v4_turbo`. The conversational variant exists only for v3
  (`eleven_v3_conversational`).
- There is **no `eleven_turbo_v2_5`**. The v2.5 fast model is
  `eleven_flash_v2_5`.
- "Eleven v3" and "Eleven v4" are real; "Eleven v5" is not documented.

A static allowlist would therefore have been wrong in both directions: it would
have offered IDs that do not exist and hidden account-specific ones that do. This
is why discovery drives the UI.

## Choosing a default

Solo defaults to a model whose latency suits conversational feedback rather than
to the highest-quality one. `eleven_flash_v2_5` (~75 ms) is the default for
spoken progress, because a milestone that arrives seconds late is worse than one
that sounds slightly less rich. The selected model is always shown in Settings
and is configurable.
