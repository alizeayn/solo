/**
 * Voice channel: a live conversation with the workspace.
 *
 * One click opens a session and it stays open. There is no hold-to-talk: the
 * user talks normally and the interface follows, showing whether Solo is
 * listening, thinking about what it heard, or speaking back. The session ends
 * only when the user ends it.
 *
 * The loop is the existing one, unchanged:
 *
 *   speech → transcribed by the backend → posted to the same endpoint a typed
 *   message uses → Orchestrator → Pi Agent → milestones → narration → speech
 *
 * Two behaviours worth knowing:
 *
 * * **Solo stops speaking when you start talking.** Interrupting is not a button
 *   press, it is just talking; the input level is compared against the playback
 *   state.
 * * **Capture pauses while Solo speaks**, because the microphone would otherwise
 *   hear the assistant and transcribe it as a new instruction.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { api } from '../api/client'
import { useSpeechPlayback } from '../hooks/useSpeechPlayback'
import { useVoiceSession } from '../hooks/useVoiceSession'
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

/** How loud input must be to count as the user interrupting. */
const BARGE_IN_LEVEL = 0.3

export default function VoiceChannel() {
  const { reportError, sendMessage, narration: lines, connection, project, tasks } = useWorkspace()
  const [state, setState] = useState<VoiceState | null>(null)
  const [heard, setHeard] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const playback = useSpeechPlayback(lines)
  const { speaking: isSpeaking, stop: stopSpeaking, setEnabled: setPlaybackEnabled } = playback
  const playbackEnabled = playback.enabled
  const playbackBlocked = playback.blocked

  /** One spoken turn: transcribe, then send it down the normal task path. */
  const handleUtterance = useCallback(
    async (audio: Blob) => {
      try {
        const transcript = await api.voice.transcribe(audio)
        if (transcript.empty) {
          setNotice('No speech was detected in that turn.')
          return
        }
        setHeard(transcript.text)
        setNotice(null)
        await sendMessage(transcript.text)
      } catch (cause) {
        reportError(cause instanceof Error ? cause.message : String(cause))
      }
    },
    [reportError, sendMessage],
  )

  const session = useVoiceSession(handleUtterance)
  const { active, state: sessionState, level, error: sessionError, start, stop, setPaused } = session

  // Refresh on mount, when the session changes, and on a slow interval — never
  // once per narration line, which would put a request on every agent event.
  const load = useCallback(async () => {
    try {
      setState(await api.voice.state())
    } catch {
      /* the panel still works from the live stream */
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load, active])

  useEffect(() => {
    const timer = window.setInterval(() => void load(), 15000)
    return () => window.clearInterval(timer)
  }, [load])

  // Capture pauses while Solo speaks, so the microphone does not hear it.
  useEffect(() => {
    setPaused(isSpeaking)
  }, [isSpeaking, setPaused])

  // Open the conversation. A voice session that begins with silence gives the
  // user nothing to respond to, so Solo greets them and asks what they want --
  // spoken through the same pipeline as everything else, which means it is also
  // written into the transcript below.
  const greeted = useRef(false)
  const activeTask = tasks.find((task) =>
    ['running', 'RUNNING', 'queued', 'QUEUED', 'pending'].includes(String(task.status)),
  )
  const greeting = useMemo(() => {
    if (activeTask) {
      return 'Hello again. I am still working on the current task. What would you like me to change?'
    }
    if (project?.name) {
      return `Hello. I am listening. What would you like me to do in ${project.name}?`
    }
    return 'Hello. I am listening. What would you like me to work on?'
  }, [activeTask, project?.name])

  useEffect(() => {
    if (!active) {
      greeted.current = false
      return
    }
    if (greeted.current) return
    greeted.current = true
    void api.voice.say(greeting, 'greeting').catch(() => {
      /* the session still works without the spoken greeting */
    })
  }, [active, greeting])

  // Interrupting is just talking: no button, no shortcut.
  const levelRef = useRef(level)
  levelRef.current = level
  useEffect(() => {
    if (isSpeaking && levelRef.current > BARGE_IN_LEVEL) stopSpeaking()
  }, [level, isSpeaking, stopSpeaking])

  const audioAvailable = state?.audio_available ?? false
  const configured = state?.configured ?? false
  const spoken = useMemo(() => lines.filter((line) => line.spoken).length, [lines])

  // The orb shows the most interesting thing happening right now.
  const orbState: VoiceOrbState = isSpeaking
    ? 'speaking'
    : sessionState === 'thinking'
      ? 'connecting'
      : active
        ? 'listening'
        : configured
          ? 'ready'
          : 'preview'

  const status = isSpeaking
    ? 'Solo is speaking'
    : sessionState === 'starting'
      ? 'Opening the microphone…'
      : sessionState === 'thinking'
        ? 'Working out what you said…'
        : active
          ? 'Listening — speak normally, then pause'
          : configured
            ? 'Session closed'
            : 'Speech is not configured'

  return (
    <div className={`panel voice-panel ${active ? 'voice-panel--live' : ''}`} aria-label="Voice channel">
      <div className="panel__bar">
        <span className="panel__bar-title">Voice</span>
        {active && <span className="pill pill--active">session open</span>}
        <span className="header__spacer" />
        {isSpeaking && (
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => stopSpeaking()}
            title="Stop Solo speaking"
          >
            Stop speaking
          </button>
        )}
        {audioAvailable && (
          <button
            type="button"
            className="btn btn--sm"
            aria-pressed={playbackEnabled}
            onClick={() => setPlaybackEnabled(!playbackEnabled)}
            title={playbackEnabled ? 'Stop speaking milestones aloud' : 'Speak milestones aloud'}
          >
            {playbackEnabled ? '🔊 Voice on' : '🔇 Voice off'}
          </button>
        )}
        {/* The audio exists but the browser refused to play it until the user
            interacts. Saying so turns a silent panel into a one-tap fix. */}
        {playbackBlocked && playbackEnabled && (
          <span className="pill pill--warning" role="status">
            tap anywhere to enable sound
          </span>
        )}
        {!active && connection !== 'open' && <span className="pill pill--neutral">offline</span>}
      </div>

      <div className="voice-panel__stage">
        <VoiceOrb state={orbState} />
        {/* A live level meter: proof the microphone is actually open. */}
        <div
          className={`voice-meter ${active ? 'voice-meter--live' : ''}`}
          role="img"
          aria-label={active ? 'Microphone input level' : 'Microphone closed'}
        >
          <span
            className="voice-meter__fill"
            style={{ width: active ? `${Math.round(Math.max(level, 0.04) * 100)}%` : '0%' }}
          />
        </div>
        <p className="voice-panel__status" aria-live="polite">{status}</p>
      </div>

      <div className="voice-panel__controls">
        {active ? (
          <button type="button" className="btn voice-session voice-session--on" onClick={stop}>
            End voice session
          </button>
        ) : (
          <button
            type="button"
            className="btn btn--primary voice-session"
            disabled={!session.supported || !configured}
            title={
              !session.supported
                ? 'This browser cannot record audio'
                : !configured
                  ? 'Add an ElevenLabs key in Settings → Voice'
                  : 'Open the microphone; the session stays open until you end it'
            }
            onClick={() => void start()}
          >
            {sessionState === 'starting' ? 'Starting…' : 'Start voice session'}
          </button>
        )}
      </div>

      {(sessionError || state?.needs_voice || state?.audio_error || notice) && (
        <div className="voice-panel__feedback">
          {sessionError && <div className="alert alert--error">{sessionError}</div>}
          {/* Speech failing is reported even when the configuration looks
              complete: an account can be fully configured and still silent. */}
          {!sessionError && state?.audio_error && (
            <div className="alert alert--warn">
              <strong>Voice output is not working.</strong>{' '}
              {state.audio_error.message}
              <br />
              Progress is still shown here as text, and tasks are unaffected.
            </div>
          )}
          {!sessionError && !state?.audio_error && state?.needs_voice && (
            <div className="alert alert--warn">
              A voice id is required for speech output. This key cannot list voices,
              so set one in Settings → Voice.
            </div>
          )}
          {!sessionError && notice && <div className="alert alert--info">{notice}</div>}
        </div>
      )}

      {heard && (
        <div className="voice-panel__heard">
          <span className="hint">Heard</span>
          <p className="voice-panel__heard-text">{heard}</p>
        </div>
      )}

      <ul className="voice-channel__lines" aria-live="polite">
        {lines.length === 0 ? (
          <li className="voice-channel__empty">
            Nothing to say yet. Milestones, errors and the final result appear here
            as the agent works, and are spoken when voice output is on.
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
                  {playback.currentId === line.id && <span className="hint">▶ speaking</span>}
                  {line.spoken && playback.currentId !== line.id && (
                    <span className="hint" title="Delivered to the transport">✓ spoken</span>
                  )}
                </span>
                <span className="voice-line__text">{line.text}</span>
              </li>
            ))
        )}
      </ul>

      <p className="hint voice-channel__note">
        {!configured
          ? 'Narration is recorded and shown but not spoken until a key is added in Settings → Voice.'
          : `Turn-taking is silence-based, not the realtime socket. ${spoken} line(s) spoken · ${state?.dropped ?? 0} dropped as stale.`}
      </p>
    </div>
  )
}
