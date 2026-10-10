import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  reportError: vi.fn(),
  orchestration: null as unknown,
}))

vi.mock('../state/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    orchestration: mocks.orchestration,
    reportError: mocks.reportError,
  }),
}))

vi.mock('../api/client', () => ({
  api: {
    orchestration: {
      get: vi.fn(),
      skip: vi.fn(),
      remove: vi.fn(),
      advance: vi.fn(),
    },
  },
}))

import { api } from '../api/client'
import OrchestrationPanel from './OrchestrationPanel'

const orchestration = api.orchestration

function view(queue: object[], notes: object[] = []) {
  return {
    summary: {
      queue_size: queue.length,
      status_counts: { pending: queue.length },
      pending_notes: notes.filter((n) => (n as { applied: unknown }).applied === null).length,
      revision: 3,
    },
    state: { project_id: 'p1', queue, notes },
  }
}

const QUEUE = [
  {
    id: 'a1',
    title: 'Create the module',
    instruction: 'Create src/pkg/mod.py with a hello function',
    priority: 10,
    depends_on: [],
    status: 'pending',
    source: 'orchestrator',
    task_id: null,
    note: null,
    created_at: null,
    updated_at: null,
  },
  {
    id: 'a2',
    title: 'Write tests',
    instruction: 'Add tests for src/pkg/mod.py',
    priority: 20,
    depends_on: ['a1'],
    status: 'pending',
    source: 'orchestrator',
    task_id: null,
    note: null,
    created_at: null,
    updated_at: null,
  },
]

describe('OrchestrationPanel', () => {
  beforeEach(() => {
    mocks.orchestration = null
    vi.mocked(orchestration.get).mockReset().mockResolvedValue(view([]) as never)
    vi.mocked(orchestration.skip).mockReset()
    vi.mocked(orchestration.remove).mockReset()
    vi.mocked(orchestration.advance).mockReset()
  })

  it('explains the empty state', async () => {
    render(<OrchestrationPanel projectId="p1" />)
    expect(await screen.findByText(/No plan yet/i)).toBeInTheDocument()
  })

  it('renders the prioritised queue with dependencies', async () => {
    vi.mocked(orchestration.get).mockResolvedValue(view(QUEUE) as never)
    render(<OrchestrationPanel projectId="p1" />)

    expect(await screen.findByText('Create the module')).toBeInTheDocument()
    expect(screen.getByText('Write tests')).toBeInTheDocument()
    expect(screen.getByText('priority 10')).toBeInTheDocument()
    expect(screen.getByText('after 1 step(s)')).toBeInTheDocument()
  })

  it('skips a queued step', async () => {
    vi.mocked(orchestration.get).mockResolvedValue(view(QUEUE) as never)
    vi.mocked(orchestration.skip).mockResolvedValue(
      view([{ ...QUEUE[0], status: 'skipped' }, QUEUE[1]]) as never,
    )

    render(<OrchestrationPanel projectId="p1" />)
    await screen.findByText('Create the module')
    await userEvent.click(screen.getAllByRole('button', { name: 'skip' })[0])

    await waitFor(() => expect(orchestration.skip).toHaveBeenCalledWith('p1', 'a1'))
    expect(await screen.findByText('skipped')).toBeInTheDocument()
  })

  it('removes a queued step', async () => {
    vi.mocked(orchestration.get).mockResolvedValue(view(QUEUE) as never)
    vi.mocked(orchestration.remove).mockResolvedValue(view([QUEUE[1]]) as never)

    render(<OrchestrationPanel projectId="p1" />)
    await screen.findByText('Create the module')
    await userEvent.click(screen.getAllByRole('button', { name: '✕' })[0])

    await waitFor(() => expect(orchestration.remove).toHaveBeenCalledWith('p1', 'a1'))
    await waitFor(() =>
      expect(screen.queryByText('Create the module')).not.toBeInTheDocument(),
    )
  })

  it('starts the next step on request', async () => {
    vi.mocked(orchestration.get).mockResolvedValue(view(QUEUE) as never)
    vi.mocked(orchestration.advance).mockResolvedValue({
      started: true,
      title: 'Create the module',
    } as never)

    render(<OrchestrationPanel projectId="p1" />)
    await screen.findByText('Create the module')
    await userEvent.click(screen.getByRole('button', { name: /start next step/i }))

    await waitFor(() => expect(orchestration.advance).toHaveBeenCalledWith('p1'))
    expect(await screen.findByText(/Started 'Create the module'/i)).toBeInTheDocument()
  })

  it('reports why nothing started', async () => {
    vi.mocked(orchestration.get).mockResolvedValue(view(QUEUE) as never)
    vi.mocked(orchestration.advance).mockResolvedValue({
      started: false,
      reason: 'a task is already running',
    } as never)

    render(<OrchestrationPanel projectId="p1" />)
    await screen.findByText('Create the module')
    await userEvent.click(screen.getByRole('button', { name: /start next step/i }))

    expect(await screen.findByText(/a task is already running/i)).toBeInTheDocument()
  })

  it('shows recorded instructions with their applied state', async () => {
    const notes = [
      {
        id: 'n1',
        text: 'also update the docs',
        kind: 'instruction',
        task_id: 't1',
        applied: 'steered',
        created_at: new Date().toISOString(),
      },
      {
        id: 'n2',
        text: 'and add a changelog entry',
        kind: 'instruction',
        task_id: 't1',
        applied: null,
        created_at: new Date().toISOString(),
      },
    ]
    vi.mocked(orchestration.get).mockResolvedValue(view(QUEUE, notes) as never)

    render(<OrchestrationPanel projectId="p1" />)
    expect(await screen.findByText('also update the docs')).toBeInTheDocument()
    expect(screen.getByText('and add a changelog entry')).toBeInTheDocument()
    expect(screen.getByText(/1 not yet applied/i)).toBeInTheDocument()
    expect(screen.getByText('applied · steered')).toBeInTheDocument()
    expect(screen.getAllByText('pending').length).toBeGreaterThan(0)
  })
})
