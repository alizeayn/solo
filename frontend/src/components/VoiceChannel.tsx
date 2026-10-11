/**
 * Voice channel panel.
 *
 * The visible half of Solo's voice-native design: what the agent would say, in
 * order, with controls for barge-in.
 *
 * Audio itself arrives in Phase 4. Rather than a decorative mock-up, this shows
 * the **real narration pipeline** — the lines the agent produced, their
 * priority, whether they were spoken, and how many were dropped — while stating
 * plainly that to playback is not implemented yet. When Phase 4 attaches an
 * audio transport, this panel becomes the transcript of the conversation with
 * no change to its contract.
 */

import { useCallback, useEffect, useState } from 'react'

import { api } from '../api/client'
import { useWorkspace } from '../state/WorkspaceProvider'
import type { VoiceState } from '../types'
import { relativeTime } from '../utils/format'
import VoiceOrb from './VoiceOrb'

const KIND_LABEL: Record<string, string> = {
  progress: 'Progress',
  summary: 'Summary',
  outcome: 'Result',
  error: 'Error',
  interrupt: 'Interrupted',
  resume: 'Resumed',
}

export default function VoiceChannel() {
  const { reportError, narration: lines, connection } = useWorkspace()
  const [state, setState] = useState<VoiceState | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

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

  const spoken = lines.filter((line) => line.spoken).length
  const audioAvailable = state?.audio_available ?? false

  return (
    <div className="panel voice-panel" aria-label="Voice channel">
      <div className="panel__bar">
        <span className="panel__bar-title">Voice</span>
        <span className="header__spacer" />
        {state?.listening ? (
          <span className="pill pill--active">listening</span>
        ) : (
          <span className="pill pill--neutral">
            {connection === 'open' ? 'ready' : 'offline'}
          </span>
        )}
        <button
          type="button"
          className="btn btn--sm"
          disabled={busy !== null}
          title="Stop speech and drop lower-priority announcements"
          onClick={() =>
            void guarded('interrupt', async () => {
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
            onClick={() => void guarded('resume', async () => setState(await api.voice.resume()))}
          >
            Resume
          </button>
        )}
      </div>

      <div className="voice-panel__orb">
        <VoiceOrb state="preview" />
      </div>

      <p className="hint voice-channel__note">
        {audioAvailable
          ? 'Narration is being spoken.'
          : 'Narration is recorded and shown here; audio playback arrives in Phase 4.'}
        {state ? ` · ${spoken} spoken · ${state.dropped} dropped as stale` : ''}
      </p>

      <ul className="voice-channel__lines" aria-live="polite">
        {lines.length === 0 ? (
          <li className="voice-channel__empty">
            Nothing to say yet. Progress summaries, errors and the final result will
            appear here as the agent works.
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
                  {line.spoken && <span className="hint" title="Delivered to the transport">✓ spoken</span>}
                </span>
                <span className="voice-line__text">{line.text}</span>
              </li>
            ))
        )}
      </ul>
    </div>
  )
}
