# ElevenLabs — technical notes

Verified notes on the ElevenLabs APIs Solo uses, kept next to the code so future
work starts from checked facts rather than assumptions or outdated examples.

Every statement here was read from the official documentation at
<https://elevenlabs.io/docs> (the `.md` form of each page) on **2026-10-11**.
Where something could be checked against the live API it was checked on
**2026-10-12**, and the results are in [07-live-verified.md](07-live-verified.md) —
including one claim in this folder that turned out to be wrong.

| File | Covers |
|---|---|
| [01-authentication.md](01-authentication.md) | API key, header, base URLs, residency |
| [02-models.md](02-models.md) | Model IDs, families, discovery endpoint, capabilities |
| [03-text-to-speech.md](03-text-to-speech.md) | Speech synthesis, streaming, output formats |
| [04-speech-to-text.md](04-speech-to-text.md) | Transcription, realtime recognition |
| [05-voices.md](05-voices.md) | Voice discovery and selection |
| [06-solo-integration.md](06-solo-integration.md) | How Solo wires these into the narration pipeline |
| [07-live-verified.md](07-live-verified.md) | What a real key actually returned: permissions, plan limits, error shapes |

## Sources

- Documentation index: <https://elevenlabs.io/docs/llms.txt>
- Full documentation in one file: <https://elevenlabs.io/docs/llms-full.txt>
- Any page as markdown: append `.md` to its URL.

## What is deliberately not used

Solo does **not** use the ElevenLabs **Agents Platform** (conversational AI
agents, `agent_id`, WebRTC/WebSocket conversation sessions). That platform owns
the conversation loop and the language model, which would put it in front of
Solo's Orchestrator and Pi Agent. Solo's architecture puts the Orchestrator in
charge of what is worth saying, so only two capabilities are used:

1. **Text to speech** — to say lines the narration pipeline selected.
2. **Speech to text** — to turn the user's speech into text for the existing
   task dispatch path.

The API key field `elevenlabs_agent_id` exists in Solo's settings schema from
earlier scaffolding. It is **not** required by this integration and is no longer
part of the validation flow.
