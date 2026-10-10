import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { AppEvent, Task } from '../types'

const mocks = vi.hoisted(() => ({
  state: {} as Record<string, unknown>,
}))

vi.mock('../state/WorkspaceProvider', () => ({
  useWorkspace: () => mocks.state,
}))

import ActivityPanel from './ActivityPanel'

const runningTask: Task = {
  id: 'task-1',
  project_id: 'project-1',
  conversation_id: null,
  parent_task_id: null,
  task_type: 'CODING',
  status: 'RUNNING',
  instruction: 'add a health endpoint',
  progress_summary: 'Located the relevant module.',
  result_summary: null,
  error: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  completed_at: null,
}

function event(partial: Partial<AppEvent> & Pick<AppEvent, 'id' | 'type'>): AppEvent {
  return {
    task_id: 'task-1',
    project_id: 'project-1',
    message: 'something happened',
    data: {},
    created_at: new Date().toISOString(),
    ...partial,
  } as AppEvent
}

const events: AppEvent[] = [
  event({ id: 1, type: 'run.started', message: 'Working on it' }),
  event({
    id: 2,
    type: 'file.changed',
    message: 'Modified src/app.py',
    data: { path: 'src/app.py', change_type: 'modified' },
  }),
  event({ id: 3, type: 'test.result', message: 'Tests passed', data: { passed: 3 } }),
  event({
    id: 4,
    type: 'progress.summary',
    message: 'Implementation in place.',
  }),
]

describe('ActivityPanel', () => {
  it('shows an empty state when nothing is selected', () => {
    mocks.state = { selectedTask: null, activeTask: null, events: [] }
    render(<ActivityPanel />)
    expect(screen.getByText(/no task selected/i)).toBeInTheDocument()
  })

  it('renders the task summary, status and metrics', () => {
    mocks.state = { selectedTask: runningTask, activeTask: null, events }
    render(<ActivityPanel />)

    expect(screen.getByText('add a health endpoint')).toBeInTheDocument()
    expect(screen.getByText('Running')).toBeInTheDocument()
    expect(screen.getByText('Located the relevant module.')).toBeInTheDocument()
    expect(screen.getByText('Files: 1')).toBeInTheDocument()
    expect(screen.getByText('Test runs: 1')).toBeInTheDocument()
  })

  it('lists changed files derived from events', () => {
    mocks.state = { selectedTask: runningTask, activeTask: null, events }
    render(<ActivityPanel />)
    expect(screen.getByText('src/app.py')).toBeInTheDocument()
  })

  it('renders the activity timeline in order', () => {
    mocks.state = { selectedTask: runningTask, activeTask: null, events }
    render(<ActivityPanel />)
    const items = screen.getAllByText(/Working on it|Modified src\/app\.py|Tests passed|Implementation in place\./)
    expect(items).toHaveLength(4)
  })

  it('surfaces task errors', () => {
    mocks.state = {
      selectedTask: { ...runningTask, status: 'FAILED', error: 'boom: adapter failed' },
      activeTask: null,
      events: [],
    }
    render(<ActivityPanel />)
    expect(screen.getByText('boom: adapter failed')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
  })

  it('falls back to the active task when nothing is selected', () => {
    mocks.state = { selectedTask: null, activeTask: runningTask, events: [] }
    render(<ActivityPanel />)
    expect(screen.getByText('add a health endpoint')).toBeInTheDocument()
  })
})
