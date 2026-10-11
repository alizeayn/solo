/**
 * Sign-in and first-run screens.
 *
 * A two-panel layout: the form on the left, and a short statement of what Solo
 * is on the right. It is the first thing anyone sees, so it states the product
 * rather than only asking for credentials — and it is the natural place to
 * explain the one thing a new user cannot discover by looking at a form.
 */

import { useEffect, useState, type FormEvent } from 'react'

import { api } from '../api/client'
import ThemeToggle from './ThemeToggle'
import type { Health } from '../types'

const MIN_PASSWORD_LENGTH = 8

type Mode = 'login' | 'setup'

export default function AuthView({
  mode,
  onComplete,
}: {
  mode: Mode
  onComplete: () => void | Promise<void>
}) {
  const isSetup = mode === 'setup'

  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => undefined)
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)

    if (isSetup) {
      if (password.length < MIN_PASSWORD_LENGTH) {
        setError(`Choose a password of at least ${MIN_PASSWORD_LENGTH} characters.`)
        return
      }
      if (password !== confirm) {
        setError('The two passwords do not match.')
        return
      }
    }

    setBusy(true)
    try {
      if (isSetup) {
        await api.auth.setup(username, password)
      } else {
        await api.auth.login(username, password)
      }
      await onComplete()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="auth">
      <div className="auth__panel">
        <div className="auth__brand">
          <span className="header__mark" aria-hidden="true">
            ◆
          </span>
          <span className="auth__brand-name">Solo</span>
        </div>

        <h1 className="auth__headline">
          {isSetup ? 'Create your workspace account' : 'Welcome back'}
        </h1>
        <p className="auth__lede">
          {isSetup
            ? 'Solo can run code and edit files, so it must be protected. This is the only account, and its password is stored as a salted hash.'
            : 'Sign in to open a project and work with your coding agent by voice or text.'}
        </p>

        <ul className="auth__points">
          <li>
            <span aria-hidden="true">🎙</span> Voice-native: talk to your coding agent
          </li>
          <li>
            <span aria-hidden="true">⌘</span> Runs the real Pi Agent, in its own isolated install
          </li>
          <li>
            <span aria-hidden="true">◆</span> Projects, memory and task state stay on your machine
          </li>
        </ul>

        <div className="auth__meta">
          <ThemeToggle compact />
          {health && (
            <span className="hint">
              v{health.version} · agent {health.coding_agent}
              {health.pi_version ? ` ${health.pi_version}` : ''}
            </span>
          )}
        </div>
      </div>

      <div className="auth__form-panel">
        <form className="auth__form" onSubmit={submit}>
          {error && (
            <div className="alert alert--error" role="alert">
              {error}
            </div>
          )}

          <div className="field">
            <label htmlFor="auth-username">Username</label>
            <input
              id="auth-username"
              className="input"
              autoComplete="username"
              autoFocus
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </div>

          <div className="field">
            <label htmlFor="auth-password">Password</label>
            <input
              id="auth-password"
              className="input"
              type="password"
              autoComplete={isSetup ? 'new-password' : 'current-password'}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            {isSetup && (
              <span className="hint">At least {MIN_PASSWORD_LENGTH} characters.</span>
            )}
          </div>

          {isSetup && (
            <div className="field">
              <label htmlFor="auth-confirm">Confirm password</label>
              <input
                id="auth-confirm"
                className="input"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                required
              />
            </div>
          )}

          <button className="btn btn--primary auth__submit" type="submit" disabled={busy}>
            {busy
              ? isSetup
                ? 'Creating account…'
                : 'Signing in…'
              : isSetup
                ? 'Create account'
                : 'Sign in'}
          </button>

          <p className="hint auth__hint">
            {isSetup
              ? 'The installer-generated password can be changed later in Settings → Account.'
              : 'Your session is stored in an HttpOnly cookie and never in browser storage.'}
          </p>
        </form>
      </div>
    </div>
  )
}
