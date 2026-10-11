import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/client', () => ({
  api: {
    auth: { login: vi.fn(), setup: vi.fn() },
    health: vi.fn(),
  },
  ApiError: class ApiError extends Error {},
}))

vi.mock('./ThemeToggle', () => ({ default: () => <div>theme-toggle</div> }))

import { api } from '../api/client'
import AuthView from './AuthView'

const login = vi.mocked(api.auth.login)
const setup = vi.mocked(api.auth.setup)
const health = vi.mocked(api.health)

const HEALTH = {
  status: 'ok' as const,
  version: '2.2.0',
  database: true,
  workspaces_dir: true,
  coding_agent: 'pi',
  pi_version: '1.1.0',
}

describe('AuthView', () => {
  beforeEach(() => {
    login.mockReset()
    setup.mockReset()
    health.mockReset().mockResolvedValue(HEALTH as never)
  })

  it('presents the product, not just a form', async () => {
    render(<AuthView mode="login" onComplete={vi.fn()} />)
    expect(screen.getByText('Solo')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /welcome back/i })).toBeInTheDocument()
    // The differentiators are stated on the entry screen.
    expect(screen.getByText(/Voice-native: talk to your coding agent/i)).toBeInTheDocument()
    expect(screen.getByText(/real Pi Agent, in its own isolated install/i)).toBeInTheDocument()
    // And the running version is shown once health resolves.
    expect(await screen.findByText(/v2\.2\.0 · agent pi 1\.1\.0/)).toBeInTheDocument()
  })

  it('offers the appearance control on the sign-in screen', async () => {
    render(<AuthView mode="login" onComplete={vi.fn()} />)
    expect(await screen.findByText('theme-toggle')).toBeInTheDocument()
  })

  it('signs in and notifies completion', async () => {
    login.mockResolvedValue({ initialized: true, authenticated: true, username: 'admin' })
    const onComplete = vi.fn()

    render(<AuthView mode="login" onComplete={onComplete} />)
    await userEvent.type(screen.getByLabelText('Password'), 'secret-password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1))
    expect(login).toHaveBeenCalledWith('admin', 'secret-password')
  })

  it('shows an error and stays put when credentials are rejected', async () => {
    login.mockRejectedValue(new Error('invalid username or password'))
    const onComplete = vi.fn()

    render(<AuthView mode="login" onComplete={onComplete} />)
    await userEvent.type(screen.getByLabelText('Password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'invalid username or password',
    )
    expect(onComplete).not.toHaveBeenCalled()
  })

  it('in setup mode explains the account and asks for confirmation', async () => {
    render(<AuthView mode="setup" onComplete={vi.fn()} />)
    expect(screen.getByRole('heading', { name: /create your workspace account/i })).toBeInTheDocument()
    expect(screen.getByLabelText('Confirm password')).toBeInTheDocument()
    expect(screen.getByText(/stored as a salted hash/i)).toBeInTheDocument()
    expect(screen.getByText(/can be changed later in Settings → Account/i)).toBeInTheDocument()
  })

  it('rejects a short password in setup mode without calling the API', async () => {
    render(<AuthView mode="setup" onComplete={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('Password'), 'short')
    await userEvent.type(screen.getByLabelText('Confirm password'), 'short')
    await userEvent.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/at least 8 characters/i)
    expect(setup).not.toHaveBeenCalled()
  })

  it('rejects mismatched passwords in setup mode', async () => {
    render(<AuthView mode="setup" onComplete={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('Password'), 'a-good-password')
    await userEvent.type(screen.getByLabelText('Confirm password'), 'a-different-one')
    await userEvent.click(screen.getByRole('button', { name: /create account/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/do not match/i)
    expect(setup).not.toHaveBeenCalled()
  })

  it('creates the account in setup mode', async () => {
    setup.mockResolvedValue({ initialized: true, authenticated: true, username: 'admin' })
    const onComplete = vi.fn()

    render(<AuthView mode="setup" onComplete={onComplete} />)
    await userEvent.type(screen.getByLabelText('Password'), 'a-good-password')
    await userEvent.type(screen.getByLabelText('Confirm password'), 'a-good-password')
    await userEvent.click(screen.getByRole('button', { name: /create account/i }))

    await waitFor(() => expect(setup).toHaveBeenCalledWith('admin', 'a-good-password'))
    expect(onComplete).toHaveBeenCalledTimes(1)
  })
})
