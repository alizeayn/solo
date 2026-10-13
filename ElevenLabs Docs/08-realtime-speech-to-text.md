# Realtime Speech to Text (verified protocol)

The browser streams microphone audio to ElevenLabs and receives live transcripts.
This is what makes Voice Mode feel like speech instead of a recording.

## Why this document records the wire format explicitly

The API reference names frames in camelCase (`inputAudioChunk`,
`partialTranscript`). The **actual protocol uses a `message_type` field with
snake_case values**, in both directions. Sending `type` produces:

```json
{"message_type":"input_error","error":"Message must be a valid protocol message"}
```

The socket stays connected and the session then does nothing at all — the
microphone is open, the connection looks healthy, and no text ever arrives. Every
frame below was therefore confirmed against the live service rather than taken
from the documentation alone.

## Handshake

```
wss://api.elevenlabs.io/v1/speech-to-text/realtime
      ?model_id=scribe_v2_realtime
      &audio_format=pcm_16000
      &commit_strategy=vad
      &no_verbatim=true
      &token=<single-use token>
```

| Parameter | Notes |
|---|---|
| `model_id` | `scribe_v2_realtime` |
| `audio_format` | `pcm_8000` … `pcm_48000`, `ulaw_8000`. Solo uses `pcm_16000`. |
| `commit_strategy` | `manual`, `vad`, or `turn_prediction`. Solo uses `vad` for hands-free turns. |
| `token` | Single-use token. When present, `xi-api-key` is not required. |
| `include_timestamps` | Off by default; adds `committed_transcript_with_timestamps`. |
| `no_verbatim` | Removes filler words — useful when the transcript becomes a task instruction. |
| `keepalive_interval_ms` | 500–10000. Emits `partial_transcript` during silence so read timeouts do not drop the socket. |
| `vad_silence_threshold_secs` | How much silence ends a segment. |
| `enable_logging` | `false` requests zero-retention (enterprise only). |

## Authentication

Two options, per the docs:

1. `xi-api-key` header — server-side only.
2. `token` query parameter — **required for client-side use**, so the API key
   never reaches a browser.

Tokens come from `POST /v1/single-use-token/{token_type}`. Valid types are
`realtime_scribe`, `batch_scribe`, `tts_websocket`, `ttd_websocket`. Any other
spelling is a 422:

```json
{"detail":[{"type":"enum","loc":["path","token_type"],
 "msg":"Input should be 'realtime_scribe', 'batch_scribe', 'tts_websocket' or 'ttd_websocket'"}]}
```

**Minting a token consumes no credits.** Only the audio that follows does.

## Send

```json
{"message_type": "input_audio_chunk", "audio_base_64": "<base64 signed 16-bit PCM>"}
```

Verified accepted. Note the field is `audio_base_64`, and the audio must already
be in the format the handshake declared.

## Receive

| `message_type` | Meaning |
|---|---|
| `session_started` | Connected; returns `session_id` and the resolved `config` |
| `partial_transcript` | **Interim**, changes. Also used as a keepalive (empty `text`). |
| `committed_transcript` | **Stable, final text for that segment.** Never changes. |
| `committed_transcript_with_timestamps` | Only with `include_timestamps` |
| `committed_transcript_entities` | Only with `entity_detection` |
| `edited_transcript` | Only with `transcript_edit` |
| `quota_exceeded`, `auth_error`, `input_error`, `throttled`, … | Failures, each as its own `message_type` |

There is **no `final_transcript`** event; `committed_transcript` is the final one.

## Rules Solo follows

* **Dispatch only on `committed_transcript`.** Partials change; dispatching one
  would create tasks from half-sentences.
* **Show partials as interim text.** Rendering them is what makes the interaction
  feel live, and it costs nothing because they are never acted upon.
* **Report every error `message_type`.** The service names its own failures
  precisely; a generic error would throw that away.
* **Close the session when done.** An open socket consumes credits even in
  silence.

## Observed frames

```json
{"message_type":"session_started","session_id":"a76fb871…",
 "config":{"sample_rate":16000,"audio_format":"pcm_16000","vad_commit_strategy":true,
           "vad_silence_threshold_secs":1.5,"vad_threshold":0.4,…}}
{"message_type":"quota_exceeded","error":"You have exceeded your quota."}
```

The second was followed by a WebSocket close with reason
`insufficient_funds_initial_check`.

Source: <https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime>
