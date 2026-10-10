/** Non-blocking error toasts. */

import { useWorkspace } from '../state/WorkspaceProvider'

export default function Toasts() {
  const { error, dismissError } = useWorkspace()
  if (!error) return null

  return (
    <div className="toasts" role="status" aria-live="polite">
      <div className="toast">
        <span aria-hidden="true">!</span>
        <span style={{ flex: 1 }}>{error}</span>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={dismissError}
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
    </div>
  )
}
