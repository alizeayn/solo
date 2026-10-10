/**
 * Open Project dialog: create an empty workspace or import a ZIP archive.
 *
 * The browser only ever sends a name and/or a file — never a server path.
 */

import { useRef, useState, type ChangeEvent, type FormEvent } from 'react'

import { api } from '../api/client'
import { useWorkspace } from '../state/WorkspaceProvider'

type Mode = 'create' | 'upload'

export default function ProjectDialog({ onClose }: { onClose: () => void }) {
  const { refreshProjects, selectProject, dismissError } = useWorkspace()
  const [mode, setMode] = useState<Mode>('create')
  const [name, setName] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  function pickFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null
    setFile(selected)
    if (selected && !name) {
      setName(selected.name.replace(/\.zip$/i, ''))
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)

    if (mode === 'upload' && !file) {
      setError('Choose a .zip archive to upload.')
      return
    }
    if (!name.trim()) {
      setError('Give the project a name.')
      return
    }

    setBusy(true)
    try {
      const project =
        mode === 'create'
          ? await api.projects.create(name.trim())
          : await api.projects.upload(file as File, name.trim())
      await refreshProjects()
      selectProject(project.id)
      dismissError()
      onClose()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Open project">
      <form className="card" onSubmit={submit}>
        <h1 className="card__title">Open a project</h1>
        <p className="card__subtitle">
          Projects live in the application-managed workspaces directory. Uploaded
          archives are extracted safely; no setup scripts are executed.
        </p>

        <div className="stacked__tabs" style={{ border: 'none', padding: '0 0 14px' }}>
          <button
            type="button"
            className={`stacked__tab ${mode === 'create' ? 'stacked__tab--active' : ''}`}
            onClick={() => setMode('create')}
          >
            New empty project
          </button>
          <button
            type="button"
            className={`stacked__tab ${mode === 'upload' ? 'stacked__tab--active' : ''}`}
            onClick={() => setMode('upload')}
          >
            Upload ZIP archive
          </button>
        </div>

        {error && (
          <div className="alert alert--error" role="alert" style={{ marginBottom: 14 }}>
            {error}
          </div>
        )}

        <div className="form-stack">
          {mode === 'upload' && (
            <div className="field">
              <label htmlFor="project-archive">Archive (.zip)</label>
              <input
                id="project-archive"
                className="input"
                type="file"
                accept=".zip,application/zip"
                ref={fileInputRef}
                onChange={pickFile}
              />
            </div>
          )}

          <div className="field">
            <label htmlFor="project-name">Project name</label>
            <input
              id="project-name"
              className="input"
              value={name}
              placeholder="my-service"
              onChange={(event) => setName(event.target.value)}
              required
            />
          </div>

          <div className="header__group" style={{ justifyContent: 'flex-end' }}>
            <button type="button" className="btn btn--ghost" onClick={onClose}>
              Cancel
            </button>
            <button className="btn btn--primary" type="submit" disabled={busy}>
              {busy ? 'Working…' : mode === 'create' ? 'Create project' : 'Upload project'}
            </button>
          </div>
        </div>
      </form>
    </div>
  )
}
