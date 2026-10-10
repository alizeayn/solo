import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/client', () => ({
  api: {
    auth: {
      login: vi.fn(),
    },
  },
  ApiError: class ApiError extends Error {},
}))

import { api } from '../api/client'
import LoginView from './LoginView'

const login = vi.mocked(api.auth.login)

describe('LoginView', () => {
  beforeEach(() => {
    login.mockReset()
  })

  it('renders the sign-in form', () => {
    render(<LoginView onComplete={() => undefined} />)
    expect(screen.getByRole('heading', { name: /voice-first ai workspace/i })).toBeInTheDocument()
    expect(screen.getByLabelText('Username')).toHaveValue('admin')
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('submits credentials and notifies completion', async () => {
    login.mockResolvedValue({ initialized: true, authenticated: true, username: 'admin' })
    const onComplete = vi.fn()

    render(<LoginView onComplete={onComplete} />)
    await userEvent.type(screen.getByLabelText('Password'), 'secret-password')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1))
    expect(login).toHaveBeenCalledWith('admin', 'secret-password')
  })

  it('shows an error and stays put when the credentials are rejected', async () => {
    login.mockRejectedValue(new Error('invalid username or password'))
    const onComplete = vi.fn()

    render(<LoginView onComplete={onComplete} />)
    await userEvent.type(screen.getByLabelText('Password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'invalid username or password',
    )
    expect(onComplete).not.toHaveBeenCalled()
  })
})
