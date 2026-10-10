/**
 * Project dialog with three clearly separated entry points:
 *
 * * **Create** — a new directory with Solo state, either in Solo's managed
 *   workspaces folder or at a location you choose.
 * * **Open** — an existing directory on this machine, adopted in place.
 *   Nothing is copied and nothing is uploaded.
 * * **Import** — a ZIP archive extracted into Solo's managed folder.
 *
 * The browser never sends a filesystem path it did not receive from the user,
 * and every path is validated again on the backend.
 */

import { useRef, useState, type ChangeEvent, type FormEvent } from 'react'

import { api } from '../api/client'
import { useWorkspace } from '../state/WorkspaceProvider'
import DirectoryBrowser from './DirectoryBrowser'

type Mode = 'create' | 'open' | 'import'

const TABS: { id: Mode; label: string }[] = [
  { id: 'create', label: 'Create Project' },
  { id: 'open', label: 'Open Project' },
  { id: 'import', label: 'Import ZIP' },
]

export default function ProjectDialog({
  initialMode = 'create',
  onClose,
}: {
  initialMode?: Mode
  onClose: () => void
}) {
  const { refreshProjects, selectProject, dismissError } = useWorkspace()

  const [mode, setMode] = useState<Mode>(initialMode)
  const [name, setName] = useState('')
  const [file, setFile] = useState<File | null>(null)

  // Create: managed folder by default, or a chosen parent directory.
  const [useCustomLocation, setUseCustomLocation] = useState(false)
  const [parent, setParent] = useState('')

  // Open: the directory to adopt.
  const [openPath, setOpenPath] = useState('')

  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  function switchMode(next: Mode) {
    setMode(next)
    setError(null)
  }

  function pickFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null
    setFile(selected)
    if (selected && !name) setName(selected.name.replace(/\.zip$/i, ''))
  }

  function validate(): string | null {
    if (mode === 'open') {
      if (!openPath.trim()) return 'Choose a folder to open.'
      return null
    }
    if (mode === 'import' && !file) return 'Choose a .zip archive to upload.'
    if (!name.trim()) {
      return mode === 'create' ? 'Give the project a name.' : 'Give the import a name.'
    }
    if (mode === 'create' && useCustomLocation && !parent.trim()) {
      return 'Choose a parent folder, or use the Solo workspaces folder.'
    }
    return null
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const problem = validate()
    if (problem) {
      setError(problem)
      return
    }

    setBusy(true)
    setError(null)
    try {
      const project =
        mode === 'create'
          ? await api.projects.create(
              name.trim(),
              useCustomLocation ? parent.trim() : undefined,
            )
          : mode === 'open'
            ? await api.projects.open(openPath.trim(), name.trim() || undefined)
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
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Project">
      <form className="card card--wide" onSubmit={submit}>
        <div className="settings-section__head">
          <div>
            <h1 className="card__title">Projects</h1>
            <p className="card__subtitle" style={{ marginBottom: 0 }}>
              Each project keeps its own configuration, memory, sessions, task
              history and state tree inside a{' '}
              <span className="mono">.solo/</span> directory in the project root.
            </p>
          </div>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="stacked__tabs" style={{ border: 'none', padding: '14px 0' }}>
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={mode === tab.id}
              className={`stacked__tab ${mode === tab.id ? 'stacked__tab--active' : ''}`}
              onClick={() => switchMode(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {error && (
          <div className="alert alert--error" role="alert" style={{ marginBottom: 14 }}>
            {error}
          </div>
        )}

        {/* ---------------------------- Create ---------------------------- */}
        {mode === 'create' && (
          <div className="form-stack">
            <div className="field">
              <label htmlFor="project-name">Project name</label>
              <input
                id="project-name"
                className="input"
                value={name}
                placeholder="my-service"
                onChange={(event) => setName(event.target.value)}
              />
              <span className="hint">
                A new folder is created and initialised with Solo project state.
              </span>
            </div>

            <fieldset className="fieldset">
              <legend>Where should it live?</legend>
              <label className="checkbox">
                <input
                  type="radio"
                  name="create-location"
                  checked={!useCustomLocation}
                  onChange={() => setUseCustomLocation(false)}
                />
                Solo workspaces folder (recommended)
              </label>
              <label className="checkbox">
                <input
                  type="radio"
                  name="create-location"
                  checked={useCustomLocation}
                  onChange={() => setUseCustomLocation(true)}
                />
                A folder I choose
              </label>
            </fieldset>

            {useCustomLocation && (
              <>
                <p className="hint">
                  The project is created at{' '}
                  <span className="mono">
                    {parent
                      ? `${parent.replace(/\/$/, '')}/${name || '<name>'}`
                      : '<parent>/<name> — choose a parent folder below'}
                  </span>
                </p>
                <DirectoryBrowser value={parent} onChange={setParent} />
              </>
            )}
          </div>
        )}

        {/* ----------------------------- Open ----------------------------- */}
        {mode === 'open' && (
          <div className="form-stack">
            <div className="alert alert--info">
              Solo reads the project where it already is. Your files are never
              copied, moved or uploaded — only a{' '}
              <span className="mono">.solo/</span> folder is added for project
              state. Deleting the project later leaves your directory untouched.
            </div>

            <div className="field">
              <label htmlFor="open-name">Display name (optional)</label>
              <input
                id="open-name"
                className="input"
                value={name}
                placeholder="defaults to the folder name"
                onChange={(event) => setName(event.target.value)}
              />
            </div>

            <DirectoryBrowser value={openPath} onChange={setOpenPath} />
          </div>
        )}

        {/* ---------------------------- Import ---------------------------- */}
        {mode === 'import' && (
          <div className="form-stack">
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
              <span className="hint">
                Extracted into the Solo workspaces folder. Traversal, symlink and
                oversized archives are rejected, and nothing is executed.
              </span>
            </div>

            <div className="field">
              <label htmlFor="import-name">Project name</label>
              <input
                id="import-name"
                className="input"
                value={name}
                placeholder="my-service"
                onChange={(event) => setName(event.target.value)}
              />
            </div>
          </div>
        )}

        <div className="header__group" style={{ justifyContent: 'flex-end', marginTop: 18 }}>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn--primary" type="submit" disabled={busy}>
            {busy
              ? 'Working…'
              : mode === 'create'
                ? 'Create project'
                : mode === 'open'
                  ? 'Open project'
                  : 'Import project'}
          </button>
        </div>
      </form>
    </div>
  )
}
