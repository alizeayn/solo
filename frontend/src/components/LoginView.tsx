/** Sign-in form for the single-user workspace. */

import { useState, type FormEvent } from 'react'

import { api } from '../api/client'

export default function LoginView({
  onComplete,
}: {
  onComplete: () => void | Promise<void>
}) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.auth.login(username, password)
      await onComplete()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="centered">
      <form className="card" onSubmit={submit}>
        <h1 className="card__title">Solo</h1>
        <p className="card__subtitle">Voice-first AI workspace. Sign in to continue.</p>

        {error && (
          <div className="alert alert--error" role="alert" style={{ marginBottom: 14 }}>
            {error}
          </div>
        )}

        <div className="form-stack">
          <div className="field">
            <label htmlFor="login-username">Username</label>
            <input
              id="login-username"
              className="input"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </div>

          <div className="field">
            <label htmlFor="login-password">Password</label>
            <input
              id="login-password"
              className="input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </div>

          <button className="btn btn--primary" type="submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </div>
      </form>
    </div>
  )
}
