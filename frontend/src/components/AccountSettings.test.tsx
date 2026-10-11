import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ reportError: vi.fn() }))

vi.mock('../state/WorkspaceProvider', () => ({
  useWorkspace: () => ({ reportError: mocks.reportError }),
}))

vi.mock('../api/client', () => ({
  api: {
    account: {
      get: vi.fn(),
      changeUsername: vi.fn(),
      changePassword: vi.fn(),
      revokeOtherSessions: vi.fn(),
    },
  },
}))

import { api } from '../api/client'
import AccountSettings from './AccountSettings'

const account = api.account

const BASE = {
  username: 'admin',
  role: 'owner',
  created_at: '2026-10-10T12:00:00Z',
  active_sessions: 2,
  has_session: true,
}

describe('AccountSettings', () => {
  beforeEach(() => {
    mocks.reportError.mockReset()
    vi.mocked(account.get).mockReset().mockResolvedValue(BASE as never)
    vi.mocked(account.changeUsername).mockReset()
    vi.mocked(account.changePassword).mockReset()
    vi.mocked(account.revokeOtherSessions).mockReset()
  })

  it('shows the account and its session count', async () => {
    render(<AccountSettings />)
    expect(await screen.findByText('admin')).toBeInTheDocument()
    expect(screen.getByText(/2 signed in/)).toBeInTheDocument()
  })

  it('requires the current password to change the username', async () => {
    render(<AccountSettings />)
    await screen.findByText('admin')
    const button = screen.getByRole('button', { name: /change username/i })
    // Disabled until both fields are filled.
    expect(button).toBeDisabled()

    await userEvent.type(screen.getByLabelText('New username'), 'owner')
    expect(button).toBeDisabled()
    await userEvent.type(screen.getByLabelText('Confirm with your password'), 'current-secret')
    expect(button).toBeEnabled()
  })

  it('changes the username and reports the new one', async () => {
    vi.mocked(account.changeUsername).mockResolvedValue({
      ...BASE,
      username: 'owner',
    } as never)

    render(<AccountSettings />)
    await screen.findByText('admin')
    await userEvent.type(screen.getByLabelText('New username'), 'owner')
    await userEvent.type(screen.getByLabelText('Confirm with your password'), 'current-secret')
    await userEvent.click(screen.getByRole('button', { name: /change username/i }))

    await waitFor(() =>
      expect(account.changeUsername).toHaveBeenCalledWith('owner', 'current-secret'),
    )
    expect(await screen.findByText(/Username changed to owner/i)).toBeInTheDocument()
  })

  it('surfaces a rejected username change', async () => {
    vi.mocked(account.changeUsername).mockRejectedValue(
      new Error('that username is already taken'),
    )

    render(<AccountSettings />)
    await screen.findByText('admin')
    await userEvent.type(screen.getByLabelText('New username'), 'taken')
    await userEvent.type(screen.getByLabelText('Confirm with your password'), 'current-secret')
    await userEvent.click(screen.getByRole('button', { name: /change username/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('already taken')
    expect(mocks.reportError).toHaveBeenCalledWith('that username is already taken')
  })

  it('refuses mismatched new passwords before calling the API', async () => {
    render(<AccountSettings />)
    await screen.findByText('admin')
    await userEvent.type(screen.getByLabelText('Current password'), 'current-secret')
    await userEvent.type(screen.getByLabelText('New password'), 'a-new-password')
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'a-different-one')
    await userEvent.click(screen.getByRole('button', { name: /change password/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/do not match/i)
    expect(account.changePassword).not.toHaveBeenCalled()
  })

  it('changes the password and explains that other devices are signed out', async () => {
    vi.mocked(account.changePassword).mockResolvedValue({
      ...BASE,
      active_sessions: 1,
    } as never)

    render(<AccountSettings />)
    await screen.findByText('admin')
    await userEvent.type(screen.getByLabelText('Current password'), 'current-secret')
    await userEvent.type(screen.getByLabelText('New password'), 'a-new-password')
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'a-new-password')
    await userEvent.click(screen.getByRole('button', { name: /change password/i }))

    await waitFor(() =>
      expect(account.changePassword).toHaveBeenCalledWith('current-secret', 'a-new-password'),
    )
    expect(await screen.findByText(/Every other signed-in device has been signed out/i)).toBeInTheDocument()
  })

  it('signs out other devices without changing the password', async () => {
    vi.mocked(account.revokeOtherSessions).mockResolvedValue({
      ...BASE,
      active_sessions: 1,
    } as never)

    render(<AccountSettings />)
    await screen.findByText('admin')
    await userEvent.click(screen.getByRole('button', { name: /sign out other devices/i }))

    await waitFor(() => expect(account.revokeOtherSessions).toHaveBeenCalled())
    expect(await screen.findByText(/other session was signed out/i)).toBeInTheDocument()
  })

  it('states that the password is never returned', async () => {
    render(<AccountSettings />)
    await screen.findByText('admin')
    expect(screen.getByText(/salted scrypt hash and is never returned/i)).toBeInTheDocument()
  })
})
