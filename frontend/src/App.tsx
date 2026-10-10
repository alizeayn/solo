/**
 * Top-level routing between first-run setup, login and the workspace.
 *
 * There is deliberately no router dependency: the app has three mutually
 * exclusive views and a settings overlay, which is simple state, not routing.
 */

import { useCallback, useEffect, useState } from 'react'

import { api } from './api/client'
import LoginView from './components/LoginView'
import SetupView from './components/SetupView'
import WorkspaceView from './components/WorkspaceView'
import { WorkspaceProvider } from './state/WorkspaceProvider'
import type { AuthStatus } from './types'

export default function App() {
  const [auth, setAuth] = useState<AuthStatus | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refreshAuth = useCallback(async () => {
    try {
      setAuth(await api.auth.status())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }, [])

  useEffect(() => {
    void refreshAuth()
  }, [refreshAuth])

  if (error && auth === null) {
    return (
      <div className="centered">
        <div className="card">
          <h1 className="card__title">Cannot reach the server</h1>
          <p className="card__subtitle">
            The API did not respond. Check that the backend is running and reload.
          </p>
          <div className="alert alert--error">{error}</div>
        </div>
      </div>
    )
  }

  if (auth === null) {
    return (
      <div className="centered">
        <div className="empty">
          <div className="empty__glyph">◆</div>
          <div className="empty__title">Loading workspace…</div>
        </div>
      </div>
    )
  }

  if (!auth.initialized) {
    return <SetupView onComplete={refreshAuth} />
  }

  if (!auth.authenticated) {
    return <LoginView onComplete={refreshAuth} />
  }

  return (
    <WorkspaceProvider onSignedOut={refreshAuth}>
      <WorkspaceView username={auth.username ?? 'user'} onSignedOut={refreshAuth} />
    </WorkspaceProvider>
  )
}
