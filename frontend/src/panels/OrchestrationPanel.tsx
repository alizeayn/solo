/**
 * Orchestration panel: the Orchestrator's working memory for the open project.
 *
 * Shows the prioritised plan the Orchestrator built (order, dependencies,
 * status), the instructions it recorded while a task was running, and controls
 * to skip, remove or start a queued step.
 *
 * This is the visible surface of the state model that Phases 3–5 extend for the
 * reasoning and voice models: decomposition, prioritisation, dependency
 * ordering and context retention are all expressed here.
 */

import { useCallback, useEffect, useState } from 'react'

import { api } from '../api/client'
import { useWorkspace } from '../state/WorkspaceProvider'
import type { OrchestrationView, PlannedTask } from '../types'
import { relativeTime } from '../utils/format'

const STATUS_TONE: Record<string, string> = {
  pending: 'neutral',
  running: 'active',
  done: 'success',
  failed: 'danger',
  skipped: 'warning',
}

export default function OrchestrationPanel({ projectId }: { projectId: string }) {
  const { orchestration: liveSummary, reportError } = useWorkspace()
  const [view, setView] = useState<OrchestrationView | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  // When the Orchestrator model cannot be reached -- a rate limit, a quota, a
  // bad key -- Solo falls back to deterministic rules. That fallback is by
  // design, but staying quiet about it makes a limited account look like a
  // working one, which is how an exhausted free tier goes unnoticed.
  const [degraded, setDegraded] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setView(await api.orchestration.get(projectId))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
    try {
      const status = await api.orchestrator.status()
      setDegraded(
        status.failure_count > 0 && status.last_error ? status.last_error : null,
      )
    } catch {
      // Status is advisory; never let it break the panel.
      setDegraded(null)
    }
  }, [projectId])

  useEffect(() => {
    void load()
  }, [load])

  // Refresh when the orchestrator publishes a state change.
  useEffect(() => {
    if (liveSummary) void load()
  }, [liveSummary, load])

  async function guarded(key: string, action: () => Promise<void>) {
    setBusy(key)
    setError(null)
    setNotice(null)
    try {
      await action()
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      setError(message)
      reportError(message)
    } finally {
      setBusy(null)
    }
  }

  const queue: PlannedTask[] = view?.state.queue ?? []
  const notes = view?.state.notes ?? []
  const pendingNotes = notes.filter((note) => note.applied === null)
  const summary = view?.summary ?? liveSummary ?? null

  return (
    <div className="state-panel">
      <div className="state-panel__toolbar">
        <span className="panel__bar-title">Plan</span>
        <div className="form-actions">
          <button
            type="button"
            className="btn btn--sm"
            disabled={busy === 'advance' || queue.length === 0}
            onClick={() =>
              void guarded('advance', async () => {
                const result = await api.orchestration.advance(projectId)
                setNotice(
                  result.started
                    ? `Started '${result.title}'.`
                    : `Nothing started: ${result.reason ?? 'unavailable'}.`,
                )
                await load()
              })
            }
          >
            Start next step
          </button>
          <button type="button" className="btn btn--sm" onClick={() => void load()}>
            Refresh
          </button>
        </div>
      </div>

      {summary && (
        <div className="stat-grid">
          <Stat label="Queued" value={summary.queue_size ?? 0} />
          <Stat label="Pending" value={summary.status_counts?.pending ?? 0} />
          <Stat label="Done" value={summary.status_counts?.done ?? 0} />
          <Stat label="Failed" value={summary.status_counts?.failed ?? 0} />
          <Stat label="Notes" value={summary.pending_notes ?? 0} />
        </div>
      )}

      {error && <div className="alert alert--error">{error}</div>}
      {notice && !error && <div className="alert alert--info">{notice}</div>}
      {/* Reported rather than swallowed: Solo keeps working on deterministic
          rules, and the user is told why the model's help is missing. */}
      {degraded && !error && (
        <div className="alert alert--warn">
          Orchestrator model unavailable, so Solo is using deterministic rules and
          snapshot answers. Tasks are unaffected.
          <br />
          <span className="mono">{degraded}</span>
        </div>
      )}

      {queue.length === 0 ? (
        <div className="empty">
          <div className="empty__glyph">◎</div>
          <div className="empty__title">No plan yet</div>
          <div className="empty__text">
            When the Orchestrator model is configured, a compound request is decomposed into an
            ordered plan here. With it disabled, instructions run immediately as a single task.
          </div>
        </div>
      ) : (
        <div className="section">
          <h3 className="section__title">Prioritised queue</h3>
          <ul className="list">
            {queue.map((item) => (
              <li key={item.id} className="plan-item">
                <div className="plan-item__head">
                  <span className={`pill pill--${STATUS_TONE[item.status] ?? 'neutral'}`}>
                    {item.status}
                  </span>
                  <span className="hint">priority {item.priority}</span>
                  {item.depends_on.length > 0 && (
                    <span className="hint">
                      after {item.depends_on.length} step(s)
                    </span>
                  )}
                  <span className="header__spacer" />
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    disabled={busy === item.id || item.status === 'running'}
                    title="Skip this step"
                    onClick={() =>
                      void guarded(item.id, async () => {
                        setView(await api.orchestration.skip(projectId, item.id))
                      })
                    }
                  >
                    skip
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost btn--sm"
                    disabled={busy === item.id || item.status === 'running'}
                    title="Remove this step"
                    onClick={() =>
                      void guarded(item.id, async () => {
                        setView(await api.orchestration.remove(projectId, item.id))
                      })
                    }
                  >
                    ✕
                  </button>
                </div>
                <div className="plan-item__title">{item.title}</div>
                <div className="plan-item__instruction">{item.instruction}</div>
                {item.note && <div className="hint">{item.note}</div>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {notes.length > 0 && (
        <div className="section">
          <h3 className="section__title">
            Recorded instructions {pendingNotes.length > 0 && `(${pendingNotes.length} not yet applied)`}
          </h3>
          <ul className="list">
            {notes
              .slice()
              .reverse()
              .slice(0, 20)
              .map((note) => (
                <li key={note.id} className="memory__item">
                  <div className="memory__head">
                    <span className={`pill ${note.applied ? 'pill--success' : 'pill--warning'}`}>
                      {note.applied ? `applied · ${note.applied}` : 'pending'}
                    </span>
                    <span className="hint">{relativeTime(note.created_at)}</span>
                  </div>
                  <div className="memory__text">{note.text}</div>
                </li>
              ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat">
      <span className="stat__value">{value}</span>
      <span className="stat__label">{label}</span>
    </div>
  )
}
