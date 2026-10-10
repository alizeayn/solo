/**
 * Panel C — Inspector / Artifacts.
 *
 * Two views:
 * * **Task** — history and details for the selected task.
 * * **Project state** — the structured `.solo/` store: state tree, memory and
 *   per-project configuration.
 *
 * It is deliberately generic so later phases can render a file excerpt or a
 * generated diagram here without restructuring the layout.
 */

import { useEffect, useState } from 'react'

import { api } from '../api/client'
import { useWorkspace } from '../state/WorkspaceProvider'
import type { TaskDetail } from '../types'
import { relativeTime, statusLabel, statusTone } from '../utils/format'
import OrchestrationPanel from './OrchestrationPanel'
import ProjectStatePanel from './ProjectStatePanel'

type Tab = 'task' | 'plan' | 'state'

export default function InspectorPanel() {
  const { tasks, selectedTaskId, selectTask, project } = useWorkspace()
  const [tab, setTab] = useState<Tab>('task')
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
        {project && (
          <div className="stacked__tabs" style={{ border: 'none', padding: 0 }}>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'task'}
              className={`stacked__tab ${tab === 'task' ? 'stacked__tab--active' : ''}`}
              onClick={() => setTab('task')}
            >
              Task
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'plan'}
              className={`stacked__tab ${tab === 'plan' ? 'stacked__tab--active' : ''}`}
              onClick={() => setTab('plan')}
            >
              Plan
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'state'}
              className={`stacked__tab ${tab === 'state' ? 'stacked__tab--active' : ''}`}
              onClick={() => setTab('state')}
            >
              Project state
            </button>
          </div>
        )}
      </div>

      <div className="panel__body">
        {project === null ? (
          <div className="empty">
            <div className="empty__glyph">◇</div>
            <div className="empty__title">Nothing to inspect</div>
            <div className="empty__text">
              Create or open a project. Task details, the project state tree and
              memory will appear here.
            </div>
          </div>
        ) : tab === 'state' ? (
          <ProjectStatePanel projectId={project.id} />
        ) : tab === 'plan' ? (
          <OrchestrationPanel projectId={project.id} />
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
