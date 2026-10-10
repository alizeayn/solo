/**
 * Panel B — Coding Agent Activity (monitor).
 *
 * Shows high-level, user-facing activity derived from normalised events. It is
 * intentionally not a terminal: raw protocol output and internal
 * chain-of-thought are never displayed.
 */

import { useMemo } from 'react'

import { useWorkspace } from '../state/WorkspaceProvider'
import type { CheckResult } from '../types'
import {
  clockTime,
  eventGlyph,
  eventLabel,
  relativeTime,
  statusLabel,
  statusTone,
} from '../utils/format'

export default function ActivityPanel() {
  const { selectedTask, activeTask, events, orchestration } = useWorkspace()
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

  const check = useMemo(() => {
    const runs = events.filter((event) => event.type === 'check.result')
    return runs.length ? (runs[runs.length - 1].data as unknown as CheckResult) : null
  }, [events])

  return (
    <div className="panel">
      <div className="panel__bar">
        <span className="panel__bar-title">Coding Agent Activity</span>
        <span className="header__spacer" />
        {orchestration?.queue_size ? (
          <span className="pill pill--neutral" title="Steps queued by the Orchestrator">
            {orchestration.queue_size} queued
          </span>
        ) : null}
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

          {check && (
            <>
              <div className="section__title" style={{ padding: '12px 12px 0' }}>
                Static checks
              </div>
              <div className="check-card">
                <div className="check-card__head">
                  <span
                    className={`pill pill--${
                      check.outcome === 'passed'
                        ? 'success'
                        : check.outcome === 'failed'
                          ? 'danger'
                          : check.outcome === 'skipped'
                            ? 'neutral'
                            : 'warning'
                    }`}
                  >
                    {check.tool} · {check.outcome}
                  </span>
                  <span className="hint">
                    {check.files_checked} file(s) · {check.duration_ms} ms
                  </span>
                </div>
                <p className="check-card__summary">{check.summary}</p>
                {check.diagnostics.length > 0 && (
                  <ul className="diagnostics">
                    {check.diagnostics.slice(0, 12).map((item, index) => (
                      <li key={`${item.file}:${item.line}:${index}`} className="diagnostics__item">
                        <span className="diagnostics__where mono">
                          {item.file}:{item.line}:{item.column}
                        </span>
                        <span className="diagnostics__message">{item.message}</span>
                        {item.rule && <span className="hint">{item.rule}</span>}
                      </li>
                    ))}
                  </ul>
                )}
                {check.diagnostics.length > 12 && (
                  <p className="hint">
                    Showing 12 of {check.diagnostics.length} diagnostics.
                  </p>
                )}
              </div>
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
