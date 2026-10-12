# Text to speech

## Endpoints

```
POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream
```

Both take the same JSON body; `/stream` returns the audio as a stream as it is
generated. Solo uses `/stream`, because the first audio arrives sooner and the
narration pipeline is already incremental.

## Body

| Field | Required | Notes |
|---|---|---|
| `text` | yes | The text to speak |
| `model_id` | no | Defaults to `eleven_multilingual_v2`; must have `can_do_text_to_speech` |
| `language_code` | no | ISO 639-1; **not supported by `eleven_multilingual_v2`** |
| `voice_settings` | no | Per-request override of the voice's stored settings |
| `seed` | no | For reproducible generation |
| `previous_text` / `next_text` | no | Request stitching for prosody across chunks |
| `pronunciation_dictionary_locators` | no | Up to 3 |

## Query parameters

| Parameter | Notes |
|---|---|
| `output_format` | Default `mp3_44100_128`. Format is `codec_sample_rate_bitrate` |
| `enable_logging` | Default `true`; `false` is zero-retention (enterprise only) |
| `optimize_streaming_latency` | **Deprecated.** 0–4, trades quality for latency |

### Output formats

`mp3_22050_32`, `mp3_24000_48`, `mp3_44100_32/64/96/128/192`, `pcm_8000` …
`pcm_48000`, `ulaw_8000`, `alaw_8000`, `opus_48000_32/64/96/128/192`.

- `mp3_44100_128` is the default and needs no special tier.
- `mp3_44100_192` requires Creator tier or above.
- `pcm_*`/`wav` at 44.1 kHz requires Pro tier or above.

Solo requests `mp3_44100_128`: it needs no tier, and `audio/mpeg` plays in every
browser without a decoder.

## Character limits

`maximum_text_length_per_request` differs per model (5,000 for `eleven_v3`,
10,000 for v4 and multilingual v2, 40,000 for Flash v2.5). Solo splits long text
into sentence-bounded chunks well below the smallest limit, so a single long
milestone cannot fail the request.

## Latency

The deprecated `optimize_streaming_latency` knob is **not** used. Latency is
managed by model choice (`eleven_flash_v2_5`) and by streaming, both of which are
current API surface.

## Cost

Billed per character, multiplied by the model's cost factor. This is why Solo
narrates **milestones only** and coalesces superseded progress lines: narrating
every agent event would be both unintelligible and expensive.
