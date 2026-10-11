/**
 * Orchestrator Milestones.
 *
 * Deliberately **not** the same as the Pi Agent Activity panel. Activity shows
 * what the agent is doing — tool calls, files, commands. This shows what it
 * *means*: which phase of the task is in progress, what established it, and how
 * it ended. The backend derives both from the same events and publishes them as
 * separate structured streams; the frontend does not infer progress from text.
 *
 * The panel renders the newest state of a structured object, which is also what
 * the future voice integration will consume:
 *
 *   milestone = { stage, status, title, detail, evidence, sequence }
 *
 * Text reveal is progressive but never blocks a result: stages, statuses and
 * evidence update immediately, and a milestone that is no longer current is
 * shown in full.
 */

import { useMemo } from 'react'

import { useTypewriter } from '../hooks/useTypewriter'
import { useWorkspace } from '../state/WorkspaceProvider'
import type { Milestone } from '../types'
import { relativeTime } from '../utils/format'

const STAGE_GLYPH: Record<string, string> = {
  understanding: '◍',
  planning: '◇',
  implementing: '✎',
  verifying: '✓',
  completed: '●',
  blocked: '!',
  cancelled: '⊘',
}

const STAGE_LABEL: Record<string, string> = {
  understanding: 'Understanding',
  planning: 'Planning',
  implementing: 'Implementing',
  verifying: 'Verifying',
  completed: 'Completed',
  blocked: 'Blocked',
  cancelled: 'Cancelled',
}

function tone(milestone: Milestone): 'active' | 'success' | 'danger' | 'neutral' {
  if (milestone.status === 'failed') return 'danger'
  if (milestone.status === 'active') return 'active'
  if (milestone.status === 'done') return 'success'
  return 'neutral'
}

export default function MilestonePanel() {
  const { milestones, selectedTask, activeTask, connection } = useWorkspace()
  const task = selectedTask ?? activeTask

  const ordered = useMemo(
    () => [...milestones].sort((a, b) => a.sequence - b.sequence),
    [milestones],
  )
  const current =
    [...ordered].reverse().find((item) => item.status === 'active') ?? null

  return (
    <div className="panel">
      <div className="panel__bar">
        <span className="panel__bar-title">Orchestrator Milestones</span>
        <span className="header__spacer" />
        {current && (
          <span className={`pill pill--${tone(current)}`}>
            {STAGE_LABEL[current.stage] ?? current.stage}
          </span>
        )}
        {!current && ordered.length > 0 && (
          <span className="pill pill--neutral">no active stage</span>
        )}
        {connection !== 'open' && <span className="pill pill--neutral">offline</span>}
      </div>

      <div className="panel__body">
        {ordered.length === 0 ? (
          <div className="empty">
            <div className="empty__glyph">◎</div>
            <div className="empty__title">No milestones yet</div>
            <div className="empty__text">
              Milestones appear as the Orchestrator finds real evidence of progress:
              a task accepted, a plan made, files changed, tests run, a result
              reached. Nothing is shown that did not happen.
            </div>
          </div>
        ) : (
          <ol className="milestones" aria-label="Task milestones">
            {ordered.map((milestone) => (
              <MilestoneRow
                key={milestone.id}
                milestone={milestone}
                // Only the milestone currently in progress is revealed
                // progressively; everything else is shown in full.
                current={current?.id === milestone.id}
              />
            ))}
          </ol>
        )}
      </div>

      {task && (
        <div className="panel__footer">
          <span className="hint mono">
            task {task.id.slice(0, 8)} · {ordered.length} milestone
            {ordered.length === 1 ? '' : 's'}
          </span>
        </div>
      )}
    </div>
  )
}

function MilestoneRow({
  milestone,
  current,
}: {
  milestone: Milestone
  current: boolean
}) {
  const { shown, revealing } = useTypewriter(milestone.detail, { enabled: current })
  const state = tone(milestone)

  return (
    <li className={`milestone milestone--${state}`} data-stage={milestone.stage}>
      <span className="milestone__rail" aria-hidden="true">
        <span className="milestone__marker">
          {milestone.status === 'done' ? '✓' : (STAGE_GLYPH[milestone.stage] ?? '•')}
        </span>
      </span>

      <div className="milestone__body">
        <div className="milestone__head">
          <span className="milestone__title">{milestone.title}</span>
          <span className={`pill pill--${state}`}>
            {milestone.status === 'active' ? 'in progress' : milestone.status}
          </span>
          <span className="header__spacer" />
          <span className="hint" title={milestone.created_at}>
            {relativeTime(milestone.created_at)}
          </span>
        </div>

        {(shown || milestone.detail) && (
          <p className="milestone__detail">
            {shown}
            {revealing && <span className="milestone__caret" aria-hidden="true" />}
          </p>
        )}

        {milestone.evidence.length > 0 && (
          <ul className="milestone__evidence" aria-label="Evidence">
            {milestone.evidence.slice(0, 3).map((item, index) => (
              <li key={`${milestone.id}-${index}`} className="milestone__evidence-item mono">
                {item}
              </li>
            ))}
          </ul>
        )}

        {milestone.worded_by === 'orchestrator-model' && (
          <span className="hint">described by the Orchestrator model</span>
        )}
      </div>
    </li>
  )
}
