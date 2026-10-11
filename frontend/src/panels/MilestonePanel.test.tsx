import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  state: {} as Record<string, unknown>,
}))

vi.mock('../state/WorkspaceProvider', () => ({
  useWorkspace: () => mocks.state,
}))

import MilestonePanel from './MilestonePanel'
import type { Milestone } from '../types'

function milestone(partial: Partial<Milestone> & Pick<Milestone, 'id' | 'stage'>): Milestone {
  return {
    task_id: 't1',
    project_id: 'p1',
    title: 'A milestone',
    detail: null,
    status: 'done',
    evidence: [],
    sequence: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    worded_by: 'evidence',
    ...partial,
  } as Milestone
}

const CHAIN: Milestone[] = [
  milestone({
    id: 'm1',
    stage: 'understanding',
    title: 'Understanding the request',
    detail: 'Write a simple Python calculator',
    evidence: ['task created'],
    sequence: 1,
  }),
  milestone({
    id: 'm2',
    stage: 'implementing',
    title: 'Making the changes',
    detail: 'First change: calculator.py',
    evidence: ['file changed: calculator.py'],
    status: 'active',
    sequence: 2,
  }),
]

describe('MilestonePanel', () => {
  beforeEach(() => {
    mocks.state = {
      milestones: [],
      selectedTask: { id: 't1', instruction: 'x' },
      activeTask: null,
      connection: 'open',
    }
  })

  it('explains the empty state honestly', () => {
    render(<MilestonePanel />)
    expect(screen.getByText(/No milestones yet/i)).toBeInTheDocument()
    expect(screen.getByText(/Nothing is shown that did not happen/i)).toBeInTheDocument()
  })

  it('renders the chain in sequence with stages and evidence', () => {
    mocks.state = { ...mocks.state, milestones: CHAIN }
    render(<MilestonePanel />)

    expect(screen.getByText('Understanding the request')).toBeInTheDocument()
    expect(screen.getByText('Making the changes')).toBeInTheDocument()
    // Evidence is shown, so a milestone can always be explained.
    expect(screen.getByText('file changed: calculator.py')).toBeInTheDocument()
    // The current stage is surfaced in the panel bar.
    expect(screen.getAllByText('Implementing').length).toBeGreaterThan(0)
  })

  it('orders by sequence, not by arrival', () => {
    mocks.state = {
      ...mocks.state,
      milestones: [CHAIN[1], CHAIN[0]],
    }
    render(<MilestonePanel />)
    const titles = screen
      .getAllByText(/Understanding the request|Making the changes/)
      .map((node) => node.textContent)
    expect(titles).toEqual(['Understanding the request', 'Making the changes'])
  })

  it('distinguishes the current milestone from completed ones', () => {
    mocks.state = { ...mocks.state, milestones: CHAIN }
    const { container } = render(<MilestonePanel />)
    expect(container.querySelectorAll('.milestone--active')).toHaveLength(1)
    expect(container.querySelectorAll('.milestone--success').length).toBeGreaterThan(0)
    expect(screen.getByText('in progress')).toBeInTheDocument()
  })

  it('marks a failed milestone clearly', () => {
    mocks.state = {
      ...mocks.state,
      milestones: [
        milestone({
          id: 'm3',
          stage: 'blocked',
          title: 'Blocked',
          detail: 'Insufficient credits',
          status: 'failed',
        }),
      ],
    }
    const { container } = render(<MilestonePanel />)
    expect(container.querySelector('.milestone--danger')).toBeTruthy()
    expect(screen.getByText('Insufficient credits')).toBeInTheDocument()
  })

  it('reveals the current detail progressively rather than all at once', async () => {
    const long = 'Implementing the calculator now, one function at a time.'.repeat(2)
    mocks.state = {
      ...mocks.state,
      milestones: [milestone({ id: 'm9', stage: 'implementing', detail: long, status: 'active' })],
    }
    const { container } = render(<MilestonePanel />)

    // The reveal starts short and grows towards the full text.
    const initial = container.querySelector('.milestone__detail')?.textContent ?? ''
    expect(initial.length).toBeLessThan(long.length)

    await waitFor(
      () => {
        const shown = container.querySelector('.milestone__detail')?.textContent ?? ''
        expect(shown.length).toBeGreaterThan(initial.length)
      },
      { timeout: 2000 },
    )
    // The stage and status are correct immediately — nothing waits on the reveal.
    expect(screen.getByText('in progress')).toBeInTheDocument()
  })

  it('shows a completed milestone in full without animating', () => {
    mocks.state = {
      ...mocks.state,
      milestones: [
        milestone({
          id: 'm4',
          stage: 'completed',
          title: 'Task complete',
          detail: 'Tests passed.',
        }),
      ],
    }
    render(<MilestonePanel />)
    expect(screen.getByText('Tests passed.')).toBeInTheDocument()
  })

  it('notes when the model worded a milestone', () => {
    mocks.state = {
      ...mocks.state,
      milestones: [
        milestone({
          id: 'm5',
          stage: 'understanding',
          detail: 'Reading the request.',
          worded_by: 'orchestrator-model',
        }),
      ],
    }
    render(<MilestonePanel />)
    expect(screen.getByText(/described by the Orchestrator model/i)).toBeInTheDocument()
  })

  it('shows an offline indicator when the stream is down', () => {
    mocks.state = { ...mocks.state, connection: 'closed' }
    render(<MilestonePanel />)
    expect(screen.getByText('offline')).toBeInTheDocument()
  })
})
