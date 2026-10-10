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
  const [projectDialog, setProjectDialog] = useState<'create' | 'open' | null>(null)
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const { project } = useWorkspace()

  return (
    <div className="app">
      <Header
        username={username}
        onOpenSettings={() => setSettingsOpen(true)}
        onNewProject={() => setProjectDialog('create')}
        onOpenProject={() => setProjectDialog('open')}
        onSignedOut={onSignedOut}
      />

      <main className="main">
        {project === null ? (
          <div className="empty">
            <div className="empty__glyph">🗂</div>
            <div className="empty__title">No project selected</div>
            <div className="empty__text">
              <strong>Create Project</strong> makes a new folder with Solo
              project state. <strong>Open Project</strong> adopts a folder you
              already have — your files stay exactly where they are.
            </div>
            <div className="header__group">
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => setProjectDialog('create')}
              >
                Create Project
              </button>
              <button
                type="button"
                className="btn"
                onClick={() => setProjectDialog('open')}
              >
                Open Project
              </button>
            </div>
          </div>
        ) : isNarrow ? (
          <StackedLayout />
        ) : (
          <DockLayout />
        )}
      </main>

      {settingsOpen && <SettingsView onClose={() => setSettingsOpen(false)} />}
      {projectDialog && (
        <ProjectDialog
          initialMode={projectDialog}
          onClose={() => setProjectDialog(null)}
        />
      )}
      <Toasts />
    </div>
  )
}
