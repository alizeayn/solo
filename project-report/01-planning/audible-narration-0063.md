# Scope — making narration actually audible

| | |
|---|---|
| **Stage** | 2.5.3 — narration playback and stream recovery |
| **Date** | 2026-10-13 |

## Reported

A new ElevenLabs key was used and **credits were consumed**, but no narration or
audio was heard, and the Voice component still did not work. The connection also
seemed to drop when switching tiles. Voice *input* may stay unsupported for now;
milestone narration must be audible.

## What the evidence showed

The provider usage log settled it. **All 82 requests returned HTTP 200**, of which
**13 were successful text-to-speech calls** to
`/v1/text-to-speech/hpp4J3VqNfWAUOO0d1Us/stream`. So ElevenLabs *was* generating
audio and credits *were* being spent.

Solo's own log then showed the decisive line: **`/api/voice/audio` had been
requested zero times.** The audio existed and the browser never asked for it.

The cause was a default, not a fault: `useSpeechPlayback` initialised
`enabled = false`, so the panel offered a quiet "🔇 Voice off" button and the
client silently declined audio the server had already paid for.

## Principle

**A configured voice must be heard.** "Off by default" was defended as avoiding an
autoplay fight, but it produced the worst of both outcomes: full cost, no audio.
Browsers still refuse playback before any interaction, so that case is *reported
and recovered* rather than silently obeyed.

## Related

- [Implementation 0064](../02-implementation/audible-narration-0064.md)
- [Defect log 0066](../04-defects/defect-log-0066.md)
