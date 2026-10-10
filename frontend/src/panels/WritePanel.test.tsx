import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  reportError: vi.fn(),
  refreshProjects: vi.fn(),
  project: { id: 'p1', name: 'demo' } as { id: string; name: string } | null,
}))

vi.mock('../state/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    project: mocks.project,
    reportError: mocks.reportError,
    refreshProjects: mocks.refreshProjects,
  }),
}))

vi.mock('../api/client', () => ({
  api: {
    files: { read: vi.fn(), write: vi.fn(), upload: vi.fn(), limits: vi.fn() },
  },
}))

import { api } from '../api/client'
import WritePanel from './WritePanel'

const files = api.files
const LIMITS = { max_read_bytes: 524288, max_write_bytes: 1048576, max_upload_bytes: 52428800 }

describe('WritePanel', () => {
  beforeEach(() => {
    mocks.project = { id: 'p1', name: 'demo' }
    mocks.reportError.mockReset()
    mocks.refreshProjects.mockReset().mockResolvedValue(undefined)
    vi.mocked(files.limits).mockReset().mockResolvedValue(LIMITS as never)
    vi.mocked(files.read).mockReset()
    vi.mocked(files.write).mockReset()
    vi.mocked(files.upload).mockReset()
  })

  it('asks for a project before offering to write', () => {
    mocks.project = null
    render(<WritePanel />)
    expect(screen.getByText(/No project open/i)).toBeInTheDocument()
  })

  it('opens an existing file', async () => {
    vi.mocked(files.read).mockResolvedValue({
      path: 'docs/notes.md',
      content: '# Notes',
      size: 7,
      truncated: false,
      binary: false,
    } as never)

    render(<WritePanel />)
    await userEvent.type(screen.getByLabelText('File path'), 'docs/notes.md')
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))

    await waitFor(() => expect(files.read).toHaveBeenCalledWith('p1', 'docs/notes.md'))
    expect(await screen.findByLabelText('File content')).toHaveValue('# Notes')
    expect(screen.getByText(/Opened docs\/notes.md/i)).toBeInTheDocument()
  })

  it('saves edited content', async () => {
    vi.mocked(files.read).mockResolvedValue({
      path: 'notes.md',
      content: 'old',
      size: 3,
      truncated: false,
      binary: false,
    } as never)
    vi.mocked(files.write).mockResolvedValue({
      path: 'notes.md',
      content: 'old plus more',
      size: 13,
      truncated: false,
      binary: false,
    } as never)

    render(<WritePanel />)
    await userEvent.type(screen.getByLabelText('File path'), 'notes.md')
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))
    const editor = await screen.findByLabelText('File content')
    await userEvent.type(editor, ' plus more')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() =>
      expect(files.write).toHaveBeenCalledWith('p1', 'notes.md', 'old plus more'),
    )
    expect(await screen.findByText(/Saved notes.md/i)).toBeInTheDocument()
  })

  it('marks unsaved changes and can revert them', async () => {
    vi.mocked(files.read).mockResolvedValue({
      path: 'notes.md',
      content: 'original',
      size: 8,
      truncated: false,
      binary: false,
    } as never)

    render(<WritePanel />)
    await userEvent.type(screen.getByLabelText('File path'), 'notes.md')
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))
    const editor = await screen.findByLabelText('File content')
    await userEvent.type(editor, ' changed')

    expect(screen.getByText('unsaved')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Revert' }))
    expect(screen.queryByText('unsaved')).not.toBeInTheDocument()
  })

  it('surfaces a rejected path rather than silently failing', async () => {
    vi.mocked(files.read).mockRejectedValue(
      new Error('path traversal is not allowed'),
    )

    render(<WritePanel />)
    await userEvent.type(screen.getByLabelText('File path'), '../etc/passwd')
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'path traversal is not allowed',
    )
  })

  it('refuses to open a binary file in the editor', async () => {
    vi.mocked(files.read).mockResolvedValue({
      path: 'logo.png',
      content: '',
      size: 2048,
      truncated: false,
      binary: true,
    } as never)

    render(<WritePanel />)
    await userEvent.type(screen.getByLabelText('File path'), 'logo.png')
    await userEvent.click(screen.getByRole('button', { name: 'Open' }))

    // The empty state replaces the editor…
    expect(await screen.findByText('Not a text file')).toBeInTheDocument()
    // …and the reason is stated in the footer.
    expect(
      screen.getByText(/cannot be edited here/i),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText('File content')).not.toBeInTheDocument()
  })

  it('uploads a file into the project', async () => {
    vi.mocked(files.upload).mockResolvedValue({
      path: 'spec.pdf',
      content: '',
      size: 4096,
      truncated: false,
      binary: true,
    } as never)

    render(<WritePanel />)
    const input = screen.getByLabelText('Upload a file into the project')
    await userEvent.upload(input, new File(['%PDF'], 'spec.pdf'))

    await waitFor(() => expect(files.upload).toHaveBeenCalled())
    expect(await screen.findByText(/Uploaded spec.pdf/i)).toBeInTheDocument()
    expect(mocks.refreshProjects).toHaveBeenCalled()
  })

  it('reports an upload failure', async () => {
    vi.mocked(files.upload).mockRejectedValue(new Error('upload limit exceeded'))
    render(<WritePanel />)
    await userEvent.upload(
      screen.getByLabelText('Upload a file into the project'),
      new File(['x'], 'big.bin'),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('upload limit exceeded')
    expect(mocks.reportError).toHaveBeenCalledWith('upload limit exceeded')
  })
})
