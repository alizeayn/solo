/** First-run account creation. Only reachable while no admin exists. */

import { useState, type FormEvent } from 'react'

import { api } from '../api/client'

const MIN_PASSWORD_LENGTH = 8

export default function SetupView({
  onComplete,
}: {
  onComplete: () => void | Promise<void>
}) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Choose a password of at least ${MIN_PASSWORD_LENGTH} characters.`)
      return
    }
    if (password !== confirm) {
      setError('The two passwords do not match.')
      return
    }

    setBusy(true)
    try {
      await api.auth.setup(username, password)
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
        <h1 className="card__title">Create your account</h1>
        <p className="card__subtitle">
          This workspace can run code and edit files, so it must be protected.
          Choose the single administrator password now — it is stored only as a
          salted hash.
        </p>

        {error && (
          <div className="alert alert--error" role="alert" style={{ marginBottom: 14 }}>
            {error}
          </div>
        )}

        <div className="form-stack">
          <div className="field">
            <label htmlFor="setup-username">Username</label>
            <input
              id="setup-username"
              className="input"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </div>

          <div className="field">
            <label htmlFor="setup-password">Password</label>
            <input
              id="setup-password"
              className="input"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <span className="hint">At least {MIN_PASSWORD_LENGTH} characters.</span>
          </div>

          <div className="field">
            <label htmlFor="setup-confirm">Confirm password</label>
            <input
              id="setup-confirm"
              className="input"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              required
            />
          </div>

          <button className="btn btn--primary" type="submit" disabled={busy}>
            {busy ? 'Creating account…' : 'Create account and continue'}
          </button>
        </div>
      </form>
    </div>
  )
}
