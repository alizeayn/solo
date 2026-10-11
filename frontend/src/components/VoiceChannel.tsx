/**
 * Voice channel panel.
 *
 * This is the whole voice loop in one panel:
 *
 *   press to talk → the browser records → the backend transcribes with
 *   ElevenLabs Scribe → the transcript is posted to the *existing* message
 *   endpoint → Orchestrator → Pi Agent → milestones → narration → ElevenLabs
 *   speech → played back here.
 *
 * Two properties matter more than the controls:
 *
 * * **Nothing is a mock.** The transcript goes down the same path a typed
 *   message takes, so intent classification, task creation, Pi Agent execution
 *   and milestone persistence are all unchanged. Speech is a way to produce
 *   text and to hear milestones — not a parallel system.
 * * **It does not overstate itself.** With no API key the panel says audio is
 *   unavailable rather than showing a dead microphone. Turn-taking is
 *   push-to-talk, and it says so instead of implying full duplex.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '../api/client'
import { useSpeechPlayback } from '../hooks/useSpeechPlayback'
import { useVoiceInput } from '../hooks/useVoiceInput'
import { useWorkspace } from '../state/WorkspaceProvider'
import type { VoiceState } from '../types'
import { relativeTime } from '../utils/format'
import VoiceOrb, { type VoiceState as VoiceOrbState } from './VoiceOrb'

const KIND_LABEL: Record<string, string> = {
  progress: 'Progress',
  summary: 'Summary',
  outcome: 'Result',
  error: 'Error',
  interrupt: 'Interrupted',
  resume: 'Resumed',
}

export default function VoiceChannel() {
  const { reportError, sendMessage, narration: lines, connection } = useWorkspace()
  const [state, setState] = useState<VoiceState | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [heard, setHeard] = useState<string | null>(null)

  const input = useVoiceInput()
  const playback = useSpeechPlayback(lines)

  const load = useCallback(async () => {
    try {
      setState(await api.voice.state())
    } catch {
      /* the panel degrades to the live stream only */
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  // Refresh the summary whenever a new line arrives.
  useEffect(() => {
    if (lines.length) void load()
  }, [lines.length, load])

  async function guarded(key: string, action: () => Promise<void>) {
    setBusy(key)
    try {
      await action()
    } catch (cause) {
      reportError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(null)
    }
  }

  /**
   * Push to talk: start on the first press, transcribe and dispatch on the
   * second. The recording is stopped *before* transcription so the microphone
   * is released even if the request fails.
   */
  const toggleRecording = () =>
    guarded('talk', async () => {
      if (input.recording) {
        const audio = await input.stop()
        if (!audio) {
          reportError('Nothing was recorded. Hold the button a moment longer.')
          return
        }
        const transcript = await api.voice.transcribe(audio)
        if (transcript.empty) {
          reportError('No speech was detected in that recording.')
          return
        }
        setHeard(transcript.text)
        // The same endpoint a typed message uses, so the whole pipeline is
        // unchanged: intent, task, Pi Agent, milestones.
        await sendMessage(transcript.text)
        return
      }

      // Barge-in: stop speaking before opening the microphone, so Solo never
      // talks over the person.
      if (playback.speaking) playback.stop()
      await api.voice.interrupt('user').then(setState).catch(() => undefined)
      await input.start()
    })

  const audioAvailable = state?.audio_available ?? false
  const configured = state?.configured ?? false
  const spoken = useMemo(() => lines.filter((line) => line.spoken).length, [lines])

  // Mapped onto the orb's own vocabulary rather than inventing states it does
  // not know how to render.
  const orbState: VoiceOrbState = input.recording
    ? 'listening'
    : playback.speaking
      ? 'speaking'
      : busy === 'talk'
        ? 'connecting'
        : configured
          ? 'ready'
          : 'preview'

  return (
    <div className="panel voice-panel" aria-label="Voice channel">
      <div className="panel__bar">
        <span className="panel__bar-title">Voice</span>
        <span className="header__spacer" />
        {state?.listening ? (
          <span className="pill pill--active">listening</span>
        ) : (
          <span className="pill pill--neutral">
            {connection === 'open' ? (configured ? 'ready' : 'text only') : 'offline'}
          </span>
        )}
        <button
          type="button"
          className="btn btn--sm"
          disabled={busy !== null}
          title="Stop speech and drop lower-priority announcements"
          onClick={() =>
            void guarded('interrupt', async () => {
              playback.stop()
              setState(await api.voice.interrupt('user'))
            })
          }
        >
          {busy === 'interrupt' ? 'Interrupting…' : 'Interrupt'}
        </button>
        {state?.listening && (
          <button
            type="button"
            className="btn btn--sm"
            disabled={busy !== null}
            onClick={() =>
              void guarded('resume', async () => setState(await api.voice.resume()))
            }
          >
            Resume
          </button>
        )}
      </div>

      <div className="voice-panel__orb">
        <VoiceOrb state={orbState} />
      </div>

      <div className="voice-panel__controls">
        <button
          type="button"
          className={`btn btn--primary voice-talk ${input.recording ? 'voice-talk--live' : ''}`}
          disabled={!input.supported || busy !== null}
          title={
            input.supported
              ? 'Press to start, press again to send'
              : 'This browser cannot record audio'
          }
          onClick={() => void toggleRecording()}
        >
          {input.recording
            ? 'Stop and send'
            : busy === 'talk'
              ? 'Transcribing…'
              : input.supported
                ? 'Hold a thought'
                : 'Microphone unavailable'}
        </button>

        {audioAvailable && (
          <button
            type="button"
            className="btn btn--sm"
            aria-pressed={playback.enabled}
            onClick={() => playback.setEnabled(!playback.enabled)}
            title={
              playback.enabled
                ? 'Stop speaking milestones aloud'
                : 'Speak milestones aloud'
            }
          >
            {playback.enabled ? '🔊 Speaking' : '🔇 Muted'}
          </button>
        )}
      </div>

      <p className="hint voice-channel__note">
        {!configured
          ? 'No ElevenLabs key is configured, so narration is recorded and shown but not spoken. Add a key in Settings → Voice.'
          : input.recording
            ? 'Recording. Press again to transcribe and send the task.'
            : playback.speaking
              ? 'Speaking a milestone.'
              : 'Press to talk — speech is transcribed and sent through the normal task path.'}
        {state ? ` · ${spoken} spoken · ${state.dropped} dropped as stale` : ''}
      </p>

      {(input.error || heard) && (
        <div className="voice-panel__feedback">
          {input.error && <div className="alert alert--error">{input.error}</div>}
          {heard && !input.error && (
            <div className="alert alert--info">
              <strong>Heard:</strong> {heard}
            </div>
          )}
        </div>
      )}

      <ul className="voice-channel__lines" aria-live="polite">
        {lines.length === 0 ? (
          <li className="voice-channel__empty">
            Nothing to say yet. Milestones, errors and the final result will
            appear here as the agent works — and be spoken when speech is on.
          </li>
        ) : (
          lines
            .slice(-8)
            .reverse()
            .map((line) => (
              <li key={line.id} className={`voice-line voice-line--${line.kind}`}>
                <span className="voice-line__meta">
                  <span
                    className={`pill pill--${
                      line.kind === 'error'
                        ? 'danger'
                        : line.kind === 'outcome' || line.kind === 'summary'
                          ? 'success'
                          : 'neutral'
                    }`}
                  >
                    {KIND_LABEL[line.kind] ?? line.kind}
                  </span>
                  <span className="hint">{relativeTime(line.created_at)}</span>
                  {playback.currentId === line.id && (
                    <span className="hint" title="Playing now">
                      ▶ speaking
                    </span>
                  )}
                  {line.spoken && playback.currentId !== line.id && (
                    <span className="hint" title="Delivered to the transport">
                      ✓ spoken
                    </span>
                  )}
                </span>
                <span className="voice-line__text">{line.text}</span>
              </li>
            ))
        )}
      </ul>
    </div>
  )
}
