/**
 * Application header: branding, project selection, task status, provider
 * connection indicators and the settings action.
 */

import { api } from '../api/client'
import { useWorkspace } from '../state/WorkspaceProvider'
import StatusBadge, { realtimeTone } from './StatusBadge'

export default function Header({
  username,
  onOpenSettings,
  onNewProject,
  onOpenProject,
  onSignedOut,
}: {
  username: string
  onOpenSettings: () => void
  onNewProject: () => void
  onOpenProject: () => void
  onSignedOut: () => void | Promise<void>
}) {
  const { projects, project, selectProject, runningCount, settings, connection } =
    useWorkspace()

  const taskLabel =
    runningCount === 0
      ? 'No task running'
      : runningCount === 1
        ? '1 task running'
        : `${runningCount} tasks running`

  async function signOut() {
    try {
      await api.auth.logout()
    } finally {
      await onSignedOut()
    }
  }

  return (
    <header className="header">
      <div className="header__brand">
        <span className="header__mark" aria-hidden="true">
          ◆
        </span>
        <span>Solo</span>
      </div>

      <div className="header__group">
        <label className="sr-only" htmlFor="project-select" style={{ display: 'none' }}>
          Active project
        </label>
        <select
          id="project-select"
          className="input header__select"
          value={project?.id ?? ''}
          onChange={(event) => selectProject(event.target.value || null)}
          aria-label="Active project"
        >
          {projects.length === 0 && <option value="">No projects yet</option>}
          {projects.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <button type="button" className="btn" onClick={onNewProject}>
          + Create Project
        </button>
        <button type="button" className="btn" onClick={onOpenProject}>
          Open Project
        </button>
        {project?.location === 'external' && (
          <span
            className="context-chip"
            title={`Opened in place: ${project.root ?? ''}`}
          >
            in place
          </span>
        )}
      </div>

      <div className="header__spacer" />

      <div className="status-strip">
        <span className="status-strip__item">
          <span
            className={`dot ${runningCount > 0 ? 'dot--warn' : 'dot--off'}`}
            aria-hidden="true"
          />
          {taskLabel}
        </span>
        <StatusBadge
          label="OpenRouter"
          tone={settings?.openrouter_api_key.configured ? 'on' : 'off'}
        />
        <StatusBadge
          label="ElevenLabs"
          tone={
            settings?.elevenlabs_api_key.configured
              ? settings.elevenlabs_agent_id
                ? 'on'
                : 'warn'
              : 'off'
          }
        />
        <StatusBadge
          label="Pi"
          tone={settings?.pi_version ? 'on' : 'off'}
        />
        <StatusBadge
          label="Live"
          tone={realtimeTone(connection)}
        />
      </div>

      <div className="header__group">
        <span className="mono" style={{ color: 'var(--text-faint)' }}>
          {username}
        </span>
        <button type="button" className="btn" onClick={onOpenSettings}>
          Settings
        </button>
        <button type="button" className="btn btn--ghost" onClick={signOut}>
          Sign out
        </button>
      </div>
    </header>
  )
}
