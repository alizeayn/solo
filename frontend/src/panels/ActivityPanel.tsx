/**
 * Panel B — Coding Agent Activity (monitor).
 *
 * Shows high-level, user-facing activity derived from normalised events. It is
 * intentionally not a terminal: raw protocol output and internal
 * chain-of-thought are never displayed.
 */

import { useMemo } from 'react'

import { useWorkspace } from '../state/WorkspaceProvider'
import {
  clockTime,
  eventGlyph,
  eventLabel,
  relativeTime,
  statusLabel,
  statusTone,
} from '../utils/format'

export default function ActivityPanel() {
  const { selectedTask, activeTask, events } = useWorkspace()
  const task = selectedTask ?? activeTask

  const changedFiles = useMemo(() => {
    const seen = new Map<string, string>()
    for (const event of events) {
      if (event.type === 'file.changed') {
        const path = typeof event.data.path === 'string' ? event.data.path : null
        if (path) seen.set(path, String(event.data.change_type ?? 'modified'))
      }
    }
    return [...seen.entries()]
  }, [events])

  const testResults = useMemo(
    () => events.filter((event) => event.type === 'test.result'),
    [events],
  )

  return (
    <div className="panel">
      <div className="panel__bar">
        <span className="panel__bar-title">Coding Agent Activity</span>
        <span className="header__spacer" />
        {task && (
          <span className={`pill pill--${statusTone(task.status)}`}>
            {statusLabel(task.status)}
          </span>
        )}
      </div>

      {task === null ? (
        <div className="empty">
          <div className="empty__glyph">⚙</div>
          <div className="empty__title">No task selected</div>
          <div className="empty__text">
            Ask for a code change in the Conversation panel and live activity will
            appear here.
          </div>
        </div>
      ) : (
        <>
          <div className="activity__summary">
            <div className="activity__instruction">{task.instruction}</div>
            <div className="activity__metrics">
              <Meta label="Type" value={task.task_type.toLowerCase()} />
              <Meta label="Started" value={relativeTime(task.created_at)} />
              {task.completed_at && (
                <Meta label="Finished" value={relativeTime(task.completed_at)} />
              )}
              {changedFiles.length > 0 && (
                <Meta label="Files" value={String(changedFiles.length)} />
              )}
              {testResults.length > 0 && (
                <Meta label="Test runs" value={String(testResults.length)} />
              )}
            </div>
            {task.progress_summary && (
              <div className="alert alert--info">{task.progress_summary}</div>
            )}
            {task.error && <div className="alert alert--error">{task.error}</div>}
            {task.result_summary && !task.error && (
              <div className="hint">{task.result_summary}</div>
            )}
          </div>

          {changedFiles.length > 0 && (
            <>
              <div className="section__title" style={{ padding: '12px 12px 0' }}>
                Changed files
              </div>
              <ul className="file-list">
                {changedFiles.map(([path, change]) => (
                  <li key={path} className="file-list__item">
                    <span aria-hidden="true">✎</span>
                    <span style={{ flex: 1 }}>{path}</span>
                    <span className="pill pill--neutral">{change}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          <div className="section__title" style={{ padding: '12px 12px 0' }}>
            Activity timeline
          </div>
          {events.length === 0 ? (
            <div className="empty">
              <div className="empty__text">Waiting for the first event…</div>
            </div>
          ) : (
            <ul className="timeline">
              {events.map((event) => (
                <li
                  key={event.id}
                  className={`timeline__item ${
                    event.type === 'error'
                      ? 'timeline__item--error'
                      : event.type === 'progress.summary'
                        ? 'timeline__item--summary'
                        : ''
                  }`}
                >
                  <span className="timeline__glyph" aria-hidden="true">
                    {eventGlyph(event.type)}
                  </span>
                  <div>
                    <div className="timeline__type">{eventLabel(event.type)}</div>
                    <div className="timeline__message">{event.message}</div>
                  </div>
                  <span className="timeline__time" title={clockTime(event.created_at)}>
                    {relativeTime(event.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <span className="pill pill--neutral">
      {label}: {value}
    </span>
  )
}
