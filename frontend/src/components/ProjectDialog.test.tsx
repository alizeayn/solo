import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  refreshProjects: vi.fn(),
  selectProject: vi.fn(),
  dismissError: vi.fn(),
}))

vi.mock('../state/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    refreshProjects: mocks.refreshProjects,
    selectProject: mocks.selectProject,
    dismissError: mocks.dismissError,
  }),
}))

vi.mock('../api/client', () => ({
  api: {
    projects: {
      create: vi.fn(),
      open: vi.fn(),
      upload: vi.fn(),
    },
    fs: { list: vi.fn() },
  },
  ApiError: class ApiError extends Error {},
}))

import { api } from '../api/client'
import ProjectDialog from './ProjectDialog'

const create = vi.mocked(api.projects.create)
const open = vi.mocked(api.projects.open)
const list = vi.mocked(api.fs.list)

const PROJECT = {
  id: 'p1',
  name: 'demo',
  slug: 'demo',
  source: 'created',
  status: 'ready',
  location: 'managed',
  root: '/data/workspaces/demo',
  metadata_dir: '.solo',
  is_managed: true,
  created_at: '2026-10-10T12:00:00Z',
  updated_at: '2026-10-10T12:00:00Z',
  file_count: 0,
}

/** Choose a folder the way a user does: type a path into the browser. */
async function pickFolder(path: string) {
  const input = await screen.findByLabelText('Directory path')
  await userEvent.clear(input)
  await userEvent.type(input, `${path}{Enter}`)
  await waitFor(() =>
    expect(screen.getByText(path, { selector: '.mono' })).toBeInTheDocument(),
  )
}

describe('ProjectDialog', () => {
  beforeEach(() => {
    create.mockReset().mockResolvedValue(PROJECT as never)
    open.mockReset().mockResolvedValue(PROJECT as never)
    list.mockReset().mockImplementation(
      async (path?: string) =>
        ({
          path: path ?? '/home/tester',
          parent: '/home',
          roots: ['/home/tester'],
          entries: [],
          truncated: false,
        }) as never,
    )
    mocks.refreshProjects.mockReset().mockResolvedValue(undefined)
    mocks.selectProject.mockReset()
    mocks.dismissError.mockReset()
  })

  it('offers three distinct entry points', () => {
    render(<ProjectDialog onClose={vi.fn()} />)
    expect(screen.getByRole('tab', { name: 'Create Project' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Open Project' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Import ZIP' })).toBeInTheDocument()
  })

  it('opens on the tab it is asked to', () => {
    render(<ProjectDialog initialMode="open" onClose={vi.fn()} />)
    expect(screen.getByRole('tab', { name: 'Open Project' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  it('creates a project in the managed folder by default', async () => {
    render(<ProjectDialog onClose={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('Project name'), 'demo')
    await userEvent.click(screen.getByRole('button', { name: /create project/i }))

    await waitFor(() => expect(create).toHaveBeenCalledWith('demo', undefined))
    expect(mocks.selectProject).toHaveBeenCalledWith('p1')
  })

  it('creates a project at a folder the user chooses', async () => {
    render(<ProjectDialog onClose={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('Project name'), 'demo')
    await userEvent.click(screen.getByLabelText(/a folder i choose/i))

    await pickFolder('/srv/code')
    await userEvent.click(screen.getByRole('button', { name: /create project/i }))

    await waitFor(() => expect(create).toHaveBeenCalledWith('demo', '/srv/code'))
  })

  it('requires a folder when a custom location is chosen', async () => {
    render(<ProjectDialog onClose={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('Project name'), 'demo')
    await userEvent.click(screen.getByLabelText(/a folder i choose/i))
    await userEvent.click(screen.getByRole('button', { name: /create project/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /choose a parent folder/i,
    )
    expect(create).not.toHaveBeenCalled()
  })

  it('requires a name before creating', async () => {
    render(<ProjectDialog onClose={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /create project/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/give the project a name/i)
    expect(create).not.toHaveBeenCalled()
  })

  it('opens an existing folder in place and explains that nothing is copied', async () => {
    render(<ProjectDialog initialMode="open" onClose={vi.fn()} />)

    expect(screen.getByText(/never copied, moved or uploaded/i)).toBeInTheDocument()

    await pickFolder('/home/tester/code/my-service')
    await userEvent.click(screen.getByRole('button', { name: /open project/i }))

    await waitFor(() =>
      expect(open).toHaveBeenCalledWith('/home/tester/code/my-service', undefined),
    )
  })

  it('refuses to open without a folder', async () => {
    render(<ProjectDialog initialMode="open" onClose={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /open project/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/choose a folder to open/i)
    expect(open).not.toHaveBeenCalled()
  })

  it('surfaces a rejected open path from the backend', async () => {
    open.mockRejectedValue(new Error('that location is not allowed'))
    render(<ProjectDialog initialMode="open" onClose={vi.fn()} />)

    await pickFolder('/etc')
    await userEvent.click(screen.getByRole('button', { name: /open project/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/not allowed/i)
  })

  it('imports a zip archive', async () => {
    render(<ProjectDialog initialMode="import" onClose={vi.fn()} />)
    const file = new File(['zip-bytes'], 'my-service.zip', { type: 'application/zip' })
    await userEvent.upload(screen.getByLabelText('Archive (.zip)'), file)

    // The name is prefilled from the archive filename.
    expect(screen.getByLabelText('Project name')).toHaveValue('my-service')

    await userEvent.click(screen.getByRole('button', { name: /import project/i }))
    await waitFor(() => expect(api.projects.upload).toHaveBeenCalled())
  })
})
