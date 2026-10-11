/**
 * Account settings.
 *
 * Solo's installer generates a password so the first sign-in needs no manual
 * configuration. This pane is where it is replaced: both changes are made from
 * the workspace, and both require the **current password** even though the
 * browser already holds a session — a session proves the browser signed in at
 * some point, not that the person at the keyboard owns the account, and this
 * account can run code and edit files.
 *
 * Changing the password signs out every *other* device and keeps this one, so a
 * password change is also the way to end access elsewhere.
 */

import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { api } from '../api/client'
import { useWorkspace } from '../state/WorkspaceProvider'
import type { Account } from '../types'

export default function AccountSettings() {
  const { reportError } = useWorkspace()

  const [account, setAccount] = useState<Account | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // Username form
  const [newUsername, setNewUsername] = useState('')
  const [usernamePassword, setUsernamePassword] = useState('')

  // Password form
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const load = useCallback(async () => {
    try {
      setAccount(await api.account.get())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function guarded(key: string, action: () => Promise<void>) {
    setBusy(key)
    setError(null)
    setNotice(null)
    try {
      await action()
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      setError(message)
      reportError(message)
    } finally {
      setBusy(null)
    }
  }

  function submitUsername(event: FormEvent) {
    event.preventDefault()
    void guarded('username', async () => {
      const updated = await api.account.changeUsername(newUsername.trim(), usernamePassword)
      setAccount(updated)
      setNewUsername('')
      setUsernamePassword('')
      setNotice(`Username changed to ${updated.username}.`)
    })
  }

  function submitPassword(event: FormEvent) {
    event.preventDefault()
    if (newPassword !== confirmPassword) {
      setError('The two new passwords do not match.')
      return
    }
    void guarded('password', async () => {
      const updated = await api.account.changePassword(currentPassword, newPassword)
      setAccount(updated)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setNotice(
        'Password changed. Every other signed-in device has been signed out; ' +
          'this browser stays signed in.',
      )
    })
  }

  return (
    <div className="settings-pane">
      <section className="settings-section">
        <div className="settings-section__head">
          <h3 className="settings-section__title">Account</h3>
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => void load()}>
            Refresh
          </button>
        </div>
        <dl className="detail-grid">
          <dt>Username</dt>
          <dd className="mono">{account?.username ?? '…'}</dd>
          <dt>Role</dt>
          <dd>{account?.role ?? '—'}</dd>
          <dt>Created</dt>
          <dd>
            {account?.created_at ? new Date(account.created_at).toLocaleString() : '—'}
          </dd>
          <dt>Sessions</dt>
          <dd>
            {account?.active_sessions ?? 1} signed in
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              style={{ marginLeft: 10 }}
              disabled={busy !== null}
              onClick={() =>
                void guarded('revoke', async () => {
                  const updated = await api.account.revokeOtherSessions()
                  setAccount(updated)
                  setNotice('Every other session was signed out.')
                })
              }
            >
              Sign out other devices
            </button>
          </dd>
        </dl>
        <p className="hint">
          Solo is a single-user workspace. The password is stored only as a salted
          scrypt hash and is never returned by the API.
        </p>
      </section>

      <section className="settings-section">
        <h3 className="settings-section__title">Change username</h3>
        <form className="settings-grid" onSubmit={submitUsername}>
          <div className="field">
            <label htmlFor="account-username">New username</label>
            <input
              id="account-username"
              className="input"
              value={newUsername}
              placeholder={account?.username ?? 'admin'}
              autoComplete="username"
              onChange={(event) => setNewUsername(event.target.value)}
            />
            <span className="hint">
              3–64 characters: letters, digits, dot, dash, underscore.
            </span>
          </div>
          <div className="field">
            <label htmlFor="account-username-password">Confirm with your password</label>
            <input
              id="account-username-password"
              className="input"
              type="password"
              autoComplete="current-password"
              value={usernamePassword}
              onChange={(event) => setUsernamePassword(event.target.value)}
            />
          </div>
          <div className="form-actions">
            <button
              type="submit"
              className="btn btn--primary btn--sm"
              disabled={busy !== null || !newUsername.trim() || !usernamePassword}
            >
              {busy === 'username' ? 'Saving…' : 'Change username'}
            </button>
          </div>
        </form>
      </section>

      <section className="settings-section">
        <h3 className="settings-section__title">Change password</h3>
        <form className="settings-grid" onSubmit={submitPassword}>
          <div className="field">
            <label htmlFor="account-current">Current password</label>
            <input
              id="account-current"
              className="input"
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="account-new">New password</label>
            <input
              id="account-new"
              className="input"
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
            <span className="hint">At least 8 characters.</span>
          </div>
          <div className="field">
            <label htmlFor="account-confirm">Confirm new password</label>
            <input
              id="account-confirm"
              className="input"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
            />
          </div>
          <div className="form-actions">
            <button
              type="submit"
              className="btn btn--primary btn--sm"
              disabled={busy !== null || !currentPassword || !newPassword || !confirmPassword}
            >
              {busy === 'password' ? 'Changing…' : 'Change password'}
            </button>
          </div>
          <p className="hint">
            Changing the password signs out every other device. This browser stays
            signed in so your work is not interrupted.
          </p>
        </form>
      </section>

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}
      {notice && !error && <div className="alert alert--info">{notice}</div>}
    </div>
  )
}
