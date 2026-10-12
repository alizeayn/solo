# Voices

## Listing voices

```
GET https://api.elevenlabs.io/v2/voices
xi-api-key: <key>
```

| Parameter | Notes |
|---|---|
| `page_size` | Max 100, default 10 |
| `next_page_token` | With `has_more` for pagination |
| `` | Filters on name, description, labels, category |
| `voice_type` | `personal`, `community`, `default`, `workspace`, `saved`, `non-default`, … |
| `sort` / `sort_direction` | `created_at_unix` or `name`; `asc`/`desc` |

Each voice carries an identifier used as `{voice_id}` in the synthesis URL, plus
a name, category and labels.

## Which voice Solo uses

`elevenlabs_tts_voice_id` in Settings. When it is empty, Solo picks a sensible
default **from the account's own voice list** rather than hardcoding an ID: a
hardcoded voice may not exist for a given account, and a request naming an
unknown `voice_id` fails at synthesis time rather than at configuration time.

## Why Solo lists voices at all

Because the alternative — asking the user to paste a `voice_id` — is not a
configuration flow. Listing them turns an opaque identifier into a choice, which
is the same principle already applied to OpenRouter models and Pi providers.
