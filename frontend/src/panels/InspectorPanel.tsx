/**
 * Panel C — Inspector / Artifacts.
 *
 * Initially passive: it lists task history and shows details for the selected
 * task. It is deliberately generic so later phases can render a file excerpt, a
 * diagram or a generated artifact here without restructuring the layout.
 */

import { useEffect, useState } from 'react'

import { api } from '../api/client'
import { useWorkspace } from '../state/WorkspaceProvider'
import type { TaskDetail } from '../types'
import { relativeTime, statusLabel, statusTone } from '../utils/format'

export default function InspectorPanel() {
  const { tasks, selectedTaskId, selectTask, project } = useWorkspace()
  const [detail, setDetail] = useState<TaskDetail | null>(null)

  useEffect(() => {
    if (!selectedTaskId) {
      setDetail(null)
      return
    }
    let cancelled = false
    const load = async () => {
      try {
        const task = await api.tasks.get(selectedTaskId)
        if (!cancelled) setDetail(task)
      } catch {
        if (!cancelled) setDetail(null)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [selectedTaskId])

  return (
    <div className="panel">
      <div className="panel__bar">
        <span className="panel__bar-title">Inspector</span>
        <span className="header__spacer" />
        <span className="hint">
          {project ? `${tasks.length} task(s)` : 'no project'}
        </span>
      </div>

      <div className="panel__body">
        {project === null ? (
          <div className="empty">
            <div className="empty__glyph">◇</div>
            <div className="empty__title">Nothing to inspect</div>
            <div className="empty__text">
              Select or create a project. Task details, changed files and future
              artifacts will appear here.
            </div>
          </div>
        ) : tasks.length === 0 ? (
          <div className="empty">
            <div className="empty__glyph">◇</div>
            <div className="empty__title">No tasks yet</div>
            <div className="empty__text">
              Task history for this project will be listed here.
            </div>
          </div>
        ) : (
          <>
            <div className="section">
              <h2 className="section__title">Task history</h2>
              <ul className="list">
                {tasks.map((task) => (
                  <li key={task.id}>
                    <button
                      type="button"
                      className={`list__item ${
                        task.id === selectedTaskId ? 'list__item--selected' : ''
                      }`}
                      onClick={() => selectTask(task.id)}
                    >
                      <span className="list__row">
                        <span className={`pill pill--${statusTone(task.status)}`}>
                          {statusLabel(task.status)}
                        </span>
                        <span className="hint">{relativeTime(task.created_at)}</span>
                      </span>
                      <span className="list__text">{task.instruction}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>

            {detail && (
              <div className="section">
                <h2 className="section__title">Selected task</h2>
                <dl className="detail-grid">
                  <dt>ID</dt>
                  <dd className="mono">{detail.id}</dd>
                  <dt>Type</dt>
                  <dd>{detail.task_type}</dd>
                  <dt>Status</dt>
                  <dd>{statusLabel(detail.status)}</dd>
                  <dt>Created</dt>
                  <dd>{new Date(detail.created_at).toLocaleString()}</dd>
                  {detail.completed_at && (
                    <>
                      <dt>Completed</dt>
                      <dd>{new Date(detail.completed_at).toLocaleString()}</dd>
                    </>
                  )}
                  {detail.files.length > 0 && (
                    <>
                      <dt>Files</dt>
                      <dd>{detail.files.map((file) => file.path).join(', ')}</dd>
                    </>
                  )}
                </dl>

                {detail.result_summary && (
                  <div style={{ marginTop: 12 }}>
                    <h3 className="section__title">Result</h3>
                    <div className="alert alert--info">{detail.result_summary}</div>
                  </div>
                )}
                {detail.error && (
                  <div style={{ marginTop: 12 }}>
                    <h3 className="section__title">Error</h3>
                    <div className="alert alert--error">{detail.error}</div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
