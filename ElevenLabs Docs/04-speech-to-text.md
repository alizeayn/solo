# Speech to text

## Batch transcription

```
POST https://api.elevenlabs.io/v1/speech-to-text
Content-Type: multipart/form-data
xi-api-key: <key>
```

| Field | Required | Notes |
|---|---|---|
| `model_id` | yes | e.g. `scribe_v2` |
| `file` | one of `file`/`cloud_storage_url` | 100 ms minimum, < 5 GB, major audio and video formats |
| `language_code` | no | ISO-639-1 or ISO-639-3; auto-detected when omitted |
| `tag_audio_events` | no | Annotate `(laughter)`, `(footsteps)` |
| `diarize` | no | Label which speaker is talking |
| `num_speakers` | no | Up to 32 |
| `timestamps_granularity` | no | `word` or `character` |
| `transcript_edit` | no | Natural-language edit; +30% surcharge |
| `webhook` | no | Process asynchronously |

### Response

A transcript object. Solo reads `text` (and `language_code` when present) and
ignores the rest.

## Realtime recognition

`scribe_v2_realtime` (~150 ms) is designed for a streaming socket rather than a
file. Solo does not use it in this phase: the browser records a short utterance,
posts it as a file, and gets one transcript back. That is a coarser interaction
than true streaming, but it is reliable, needs no socket lifecycle management,
and is enough for "speak a task". It is recorded here as the upgrade path.

## Errors Solo distinguishes

| Situation | Cause | Reported as |
|---|---|---|
| `401` / `403` | Key rejected | "ElevenLabs rejected the API key" |
| `422` | Model rejected the request (e.g. wrong `model_id`) | The API's validation detail |
| `400` | Audio too short / unreadable | The API's detail |
| Network failure | Offline, DNS, timeout | "Could not reach ElevenLabs" |

An empty transcript is a **normal** outcome, not an error: the user may simply
not have spoken. Solo reports it as "no speech detected" and leaves the task
untouched, rather than dispatching an empty instruction into the agent pipeline.
