/**
 * The conversation: one surface for talking, typing and attaching files.
 *
 * This replaced a design where `Conversation`, `Voice` and `Write` were three
 * separate panels. That was wrong for a voice-first product in a way that no
 * amount of polish could fix: a sentence spoken in one panel and a correction
 * typed in another *are the same conversation*, and presenting them as separate
 * places meant the user had to remember which one had the context.
 *
 * Everything here writes to the same backend conversation through
 * `sendMessage`, so the context is shared by construction rather than by
 * synchronisation:
 *
 * * **Voice** streams audio to ElevenLabs Realtime and dispatches on each
 *   committed transcript. Interim text appears as ghost text in the composer —
 *   visible, never dispatched.
 * * **Typing** is the escape hatch for exactly the case the request described: a
 *   spoken sentence half-misunderstood, corrected by hand mid-conversation.
 * * **Files** attach from the composer instead of a separate panel.
 * * **Narration** — milestones, acknowledgements, file changes — is interleaved
 *   into the same transcript, so what Solo says and what you said read as one
 *   exchange.
 *
 * Failures are deliberately separated by source. A failed transcription and a
 * failed dispatch are different problems with different remedies, and neither
 * may take the microphone down with it: if the Orchestrator or Pi Agent is
 * broken, you must still be able to speak, be heard, and be told what broke.
 */

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'

import { api } from '../api/client'
import { useRealtimeVoice, BARGE_IN_LEVEL } from '../hooks/useRealtimeVoice'
import { useSpeechPlayback } from '../hooks/useSpeechPlayback'
import { useVoiceSession } from '../hooks/useVoiceSession'
import { useWorkspace } from '../state/WorkspaceProvider'
import type { NarrationLine } from '../types'
import { clockTime, truncate } from '../utils/format'
import VoiceOrb, { type VoiceState as VoiceOrbState } from '../components/VoiceOrb'

/** One line of the transcript, whether it was typed or spoken. */
type Entry =
  | { kind: 'message'; id: string; at: string; role: string; text: string }
  | { kind: 'narration'; id: string; at: string; label: string; text: string; spoken: boolean }

const NARRATION_LABELS: Record<string, string> = {
  milestone: 'Milestone',
  progress: 'Progress',
  reply: 'Solo',
  file: 'File',
  error: 'Problem',
  outcome: 'Result',
  summary: 'Summary',
}

export default function ConversationPanel() {
  const {
    project,
    messages,
    selectedTask,
    activeTask,
    sendMessage,
    busy,
    cancelTask,
    narration,
    reportError,
  } = useWorkspace()

  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const transcriptRef = useRef<HTMLDivElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  // --- delivery: dispatch a turn through the one shared conversation --------
  const deliver = async (text: string) => {
    if (project === null) {
      setNotice('Select a project before sending a message.')
      return
    }
    setSending(true)
    setNotice(null)
    try {
      await sendMessage(text)
    } catch (cause) {
      // The turn is NOT lost: the text is handed back so it can be corrected,
      // and the failure is reported against dispatch specifically.
      const message = cause instanceof Error ? cause.message : String(cause)
      setDraft((current) => (current.trim() ? current : text))
      setNotice(`I heard you, but could not dispatch it: ${message}`)
      reportError(message)
    } finally {
      setSending(false)
    }
  }

  // --- voice: realtime, with the batch transcriber as the fallback ----------
  const realtime = useRealtimeVoice((text) => {
    void deliver(text)
  })
  const batch = useVoiceSession(async (audio) => {
    try {
      const transcript = await api.voice.transcribe(audio)
      if (transcript.empty) {
        setNotice('No speech was detected in that turn.')
        return
      }
      // Transcription and dispatch fail for different reasons, so they are
      // caught separately: a bad transcript must not look like a broken agent.
      await deliver(transcript.text)
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      setVoiceError(`Could not transcribe that turn: ${message}`)
    }
  })

  const playback = useSpeechPlayback(narration)
  const speaking = playback.speaking
  const voiceActive = realtime.active || batch.active
  const partial = realtime.partial
  const inputError = realtime.error ?? batch.error ?? voiceError
  const voiceUnavailable = realtime.reason

  async function toggleVoice() {
    setVoiceError(null)
    if (voiceActive) {
      realtime.stop()
      batch.stop()
      return
    }
    // Prefer realtime. When the service or the browser cannot provide it, say
    // so and use segmentation instead of leaving the button dead.
    if (realtime.supported) {
      await realtime.start()
      if (realtime.active) return
      if (!realtime.error && !realtime.reason) return
    }
    batch.start()
  }

  useEffect(() => {
    if (!batch.active) return
    batch.setPaused(speaking)
  }, [speaking, batch])

  // Interrupting is just talking, on whichever capture path is live.
  const levelRef = useRef(0)
  levelRef.current = realtime.active ? realtime.level : batch.level
  useEffect(() => {
    if (speaking && levelRef.current > BARGE_IN_LEVEL) playback.stop()
  }, [realtime.level, batch.level, speaking, playback])

  // --- the unified transcript ----------------------------------------------
  const entries = useMemo<Entry[]>(() => {
    const typed: Entry[] = messages.map((message) => ({
      kind: 'message',
      id: `m-${message.id}`,
      at: message.created_at,
      role: message.role,
      text: message.content,
    }))
    const spoken: Entry[] = narration.map((line: NarrationLine) => ({
      kind: 'narration',
      id: `n-${line.id}`,
      at: line.created_at,
      label: NARRATION_LABELS[line.kind] ?? line.kind,
      text: line.text,
      spoken: Boolean(line.spoken),
    }))
    return [...typed, ...spoken].sort((a, b) => a.at.localeCompare(b.at))
  }, [messages, narration])

  useEffect(() => {
    const node = transcriptRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [entries.length, partial])

  async function attach(file: File | undefined | null) {
    if (!file || project === null) return
    setUploading(true)
    setNotice(null)
    try {
      await api.files.upload(project.id, file)
      setNotice(`Attached ${file.name}.`)
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      setNotice(`Could not attach ${file.name}: ${message}`)
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends on a physical keyboard; on a touch keyboard it inserts a
    // newline, because the on-screen Enter is the only way to write one.
    const touch = window.matchMedia('(hover: none)').matches
    if (event.key === 'Enter' && !event.shiftKey && !touch) {
      event.preventDefault()
      void submit()
    }
  }

  async function submit() {
    const text = draft.trim()
    if (!text || project === null) return
    setDraft('')
    await deliver(text)
  }

  const disabled = sending || busy || project === null
  const target = selectedTask ?? activeTask
  // VoiceOrb's vocabulary is small; map the session onto it rather than widen
  // the component's API for one caller.
  const orbState: VoiceOrbState = speaking
    ? 'speaking'
    : voiceActive
      ? 'listening'
      : project
        ? 'ready'
        : 'preview'

  return (
    <div className="panel conversation">
      <div className="panel__bar">
        <span className="panel__bar-title">Conversation</span>
        {voiceActive && (
          <span className="pill pill--active" role="status">
            {partial ? 'hearing you' : realtime.active ? 'listening' : 'listening'}
          </span>
        )}
        <span className="header__spacer" />
        {activeTask && (
          <button
            type="button"
            className="btn btn--danger btn--sm"
            onClick={() => void cancelTask(activeTask.id)}
          >
            Cancel task
          </button>
        )}
      </div>

      <div className="panel__body panel__body--flush" ref={transcriptRef}>
        {entries.length === 0 && !partial ? (
          <div className="empty">
            <div className="empty__glyph">✦</div>
            <div className="empty__title">Start the conversation</div>
            <div className="empty__text">
              Tap <strong>Voice</strong> and just say what you want done, or type
              it. Ask a question, describe a change, or correct something Solo
              misunderstood — it is all the same conversation.
            </div>
          </div>
        ) : (
          <div className="transcript">
            {entries.map((entry) =>
              entry.kind === 'message' ? (
                <article key={entry.id} className={`bubble bubble--${entry.role}`}>
                  <div className="bubble__meta">
                    <span>{entry.role === 'assistant' ? 'Assistant' : entry.role}</span>
                    <span>·</span>
                    <span title={clockTime(entry.at)}>{clockTime(entry.at)}</span>
                  </div>
                  {entry.text}
                </article>
              ) : (
                <article key={entry.id} className="bubble bubble--narration">
                  <div className="bubble__meta">
                    <span>{NARRATION_LABELS[entry.label] ?? entry.label}</span>
                    {entry.spoken && <span title="Spoken aloud">🔊</span>}
                    <span>·</span>
                    <span title={clockTime(entry.at)}>{clockTime(entry.at)}</span>
                  </div>
                  {entry.text}
                </article>
              ),
            )}
            {/* Interim speech: visible, never dispatched. */}
            {partial && (
              <article className="bubble bubble--interim" aria-live="polite">
                <div className="bubble__meta">
                  <span>Hearing</span>
                  <span>·</span>
                  <span>unconfirmed</span>
                </div>
                {partial}
              </article>
            )}
          </div>
        )}
      </div>

      {(voiceUnavailable || inputError || notice) && (
        <div className="conversation__feedback">
          {inputError && <div className="alert alert--error">{inputError}</div>}
          {!inputError && voiceUnavailable && (
            <div className="alert alert--warn">
              Realtime voice is unavailable, so Solo is using segmented recording
              instead. {voiceUnavailable}
            </div>
          )}
          {!inputError && notice && <div className="alert alert--info">{notice}</div>}
        </div>
      )}

      <div className="panel__footer">
        <div className="composer">
          <div className="composer__voice">
            <button
              type="button"
              className={`btn btn--voice ${voiceActive ? 'btn--voice-live' : ''}`}
              onClick={() => void toggleVoice()}
              disabled={project === null}
              aria-pressed={voiceActive}
              aria-label={voiceActive ? 'End voice session' : 'Start voice session'}
              title={voiceActive ? 'End the voice session' : 'Start talking'}
            >
              <VoiceOrb state={orbState} />
              <span>{voiceActive ? 'End voice' : 'Voice'}</span>
            </button>
            {voiceActive && (
              <div
                className="voice-meter voice-meter--inline"
                role="img"
                aria-label="microphone level"
              >
                <span
                  className="voice-meter__fill"
                  style={{ width: `${Math.min(100, Math.round((realtime.active ? realtime.level : batch.level) * 140))}%` }}
                />
              </div>
            )}
            {speaking && (
              <button type="button" className="btn btn--sm" onClick={() => playback.stop()}>
                Stop speaking
              </button>
            )}
          </div>

          <div className="composer__row">
            <textarea
              className="composer__input"
              placeholder={
                project === null
                  ? 'Select a project to begin'
                  : voiceActive
                    ? 'Speak, or type a correction…'
                    : 'Say something, or type it…'
              }
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={onKeyDown}
              disabled={disabled}
              rows={2}
              aria-label="Message"
            />
            <button
              type="button"
              className="btn btn--icon"
              onClick={() => fileInput.current?.click()}
              disabled={project === null || uploading}
              title="Attach a file to the project"
              aria-label="Attach a file"
            >
              {uploading ? '…' : '📎'}
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void submit()}
              disabled={disabled || draft.trim().length === 0}
            >
              {sending ? 'Sending…' : 'Send'}
            </button>
          </div>

          <input
            ref={fileInput}
            type="file"
            className="sr-only"
            onChange={(event) => void attach(event.target.files?.[0])}
          />

          <div className="composer__hint">
            <span className="context-chip" title={target?.instruction}>
              {project ? `Project: ${project.name}` : 'No project'}
              {target ? ` · Task: ${truncate(target.instruction, 44)}` : ''}
            </span>
            <span className="header__group">
              <button
                type="button"
                className="context-chip context-chip--button"
                onClick={() => playback.setEnabled(!playback.enabled)}
                aria-pressed={playback.enabled}
                title={playback.enabled ? 'Stop speaking milestones aloud' : 'Speak milestones aloud'}
              >
                {playback.enabled ? '🔊 Speech on' : '🔇 Speech off'}
              </button>
              {playback.blocked && playback.enabled && (
                <span className="pill pill--warning" role="status">
                  tap to enable sound
                </span>
              )}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
