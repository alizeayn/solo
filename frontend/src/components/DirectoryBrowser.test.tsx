import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/client', () => ({
  api: {
    fs: { list: vi.fn() },
  },
  ApiError: class ApiError extends Error {},
}))

import { api } from '../api/client'
import DirectoryBrowser from './DirectoryBrowser'

const list = vi.mocked(api.fs.list)

/** Echo the requested path so navigation behaves like the real endpoint. */
function echoListing(parent: string | null = '/') {
  list.mockImplementation(
    async (path?: string) =>
      ({
        path: path ?? '/home/tester',
        parent,
        roots: ['/home/tester'],
        entries: [],
        truncated: false,
      }) as never,
  )
}

describe('DirectoryBrowser', () => {
  beforeEach(() => {
    list.mockReset()
  })

  it('lists the directories the backend returns', async () => {
    list.mockResolvedValue({
      path: '/home/tester',
      parent: '/home',
      roots: ['/home/tester'],
      entries: [
        { name: 'code', path: '/home/tester/code', hidden: false, is_project: false },
        { name: 'notes', path: '/home/tester/notes', hidden: false, is_project: true },
      ],
      truncated: false,
    } as never)

    render(<DirectoryBrowser value="" onChange={vi.fn()} />)

    expect(await screen.findByText('code')).toBeInTheDocument()
    expect(screen.getByText('notes')).toBeInTheDocument()
    // A directory that already carries Solo state is flagged.
    expect(screen.getByText('Solo')).toBeInTheDocument()
  })

  it('does not claim a selection on mount, only on navigation', async () => {
    echoListing()
    const onChange = vi.fn()

    render(<DirectoryBrowser value="" onChange={onChange} />)
    await screen.findByLabelText('Directory path')

    // Browsing is informational until the user picks something.
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByText(/none — choose a folder below/i)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /home/i }))
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('/home/tester'))
  })

  it('navigates into a directory when it is clicked', async () => {
    list.mockResolvedValueOnce({
      path: '/home/tester',
      parent: '/home',
      roots: [],
      entries: [
        { name: 'code', path: '/home/tester/code', hidden: false, is_project: false },
      ],
      truncated: false,
    } as never)
    echoListing('/home/tester')

    render(<DirectoryBrowser value="" onChange={vi.fn()} />)
    await userEvent.click(await screen.findByText('code'))

    await waitFor(() => expect(list).toHaveBeenLastCalledWith('/home/tester/code'))
  })

  it('navigates to the parent directory', async () => {
    echoListing()
    render(<DirectoryBrowser value="" onChange={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: /↑ up/i }))
    await waitFor(() => expect(list).toHaveBeenLastCalledWith('/'))
  })

  it('disables Up when there is no parent', async () => {
    echoListing(null)
    render(<DirectoryBrowser value="/" onChange={vi.fn()} />)
    await waitFor(() =>
      expect(screen.getByLabelText('Directory path')).toHaveValue('/'),
    )
    expect(screen.getByRole('button', { name: /↑ up/i })).toBeDisabled()
  })

  it('surfaces a rejected path from the backend', async () => {
    list.mockRejectedValue(new Error('that location is not allowed'))

    render(<DirectoryBrowser value="" onChange={vi.fn()} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'that location is not allowed',
    )
  })

  it('navigates to a typed path on Enter', async () => {
    echoListing()
    const onChange = vi.fn()

    render(<DirectoryBrowser value="" onChange={onChange} />)
    const input = await screen.findByLabelText('Directory path')
    await userEvent.clear(input)
    await userEvent.type(input, '/srv/projects{Enter}')

    await waitFor(() => expect(onChange).toHaveBeenCalledWith('/srv/projects'))
  })
})
