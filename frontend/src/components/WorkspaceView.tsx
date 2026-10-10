/** Authenticated application shell: header, workspace and overlays. */

import { useState } from 'react'

import { useMediaQuery } from '../hooks/useMediaQuery'
import { useWorkspace } from '../state/WorkspaceProvider'
import DockLayout from './DockLayout'
import Header from './Header'
import ProjectDialog from './ProjectDialog'
import SettingsView from './SettingsView'
import StackedLayout from './StackedLayout'
import Toasts from './Toasts'

export default function WorkspaceView({
  username,
  onSignedOut,
}: {
  username: string
  onSignedOut: () => void | Promise<void>
}) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [projectOpen, setProjectOpen] = useState(false)
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const { project } = useWorkspace()

  return (
    <div className="app">
      <Header
        username={username}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenProject={() => setProjectOpen(true)}
        onSignedOut={onSignedOut}
      />

      <main className="main">
        {project === null ? (
          <div className="empty">
            <div className="empty__glyph">🗂</div>
            <div className="empty__title">No project selected</div>
            <div className="empty__text">
              Create an empty workspace or upload a ZIP archive to begin. The
              project directory becomes the working directory for the coding
              agent.
            </div>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setProjectOpen(true)}
            >
              Open a project
            </button>
          </div>
        ) : isNarrow ? (
          <StackedLayout />
        ) : (
          <DockLayout />
        )}
      </main>

      {settingsOpen && <SettingsView onClose={() => setSettingsOpen(false)} />}
      {projectOpen && <ProjectDialog onClose={() => setProjectOpen(false)} />}
      <Toasts />
    </div>
  )
}
