/**
 * Panel — Write.
 *
 * A focused writing surface for the open project: open a file by path, edit and
 * save it, or upload a file into the project. It is deliberately not a code
 * editor — Solo coordinates the coding agent rather than replacing it — but it
 * gives the workspace a place to write notes, docs, config and small changes
 * without leaving the browser.
 *
 * Every path is validated on the server inside the project root; Solo's own
 * metadata directory is not writable here, and nothing is executed.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '../api/client'
import { useWorkspace } from '../state/WorkspaceProvider'
import type { FileLimits } from '../types'

const DEFAULT_LIMITS: FileLimits = {
  max_read_bytes: 512 * 1024,
  max_write_bytes: 1024 * 1024,
  max_upload_bytes: 50 * 1024 * 1024,
}

function humanBytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

export default function WritePanel() {
  const { project, reportError, refreshProjects } = useWorkspace()

  const [path, setPath] = useState('')
  const [content, setContent] = useState('')
  const [original, setOriginal] = useState('')
  const [binary, setBinary] = useState(false)
  const [limits, setLimits] = useState<FileLimits>(DEFAULT_LIMITS)
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const dirty = content !== original

  useEffect(() => {
    if (!project) return
    let cancelled = false
    api.files
      .limits(project.id)
      .then((value) => {
        if (!cancelled) setLimits(value)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [project])

  const openFile = useCallback(
    async (target?: string) => {
      const wanted = (target ?? path).trim()
      if (!wanted || !project) return
      setBusy('open')
      setError(null)
      setNotice(null)
      try {
        const file = await api.files.read(project.id, wanted)
        setPath(file.path)
        setContent(file.binary ? '' : file.content)
        setOriginal(file.binary ? '' : file.content)
        setBinary(file.binary)
        setNotice(
          file.binary
            ? `${file.path} is not a text file (${humanBytes(file.size)}), so it cannot be edited here.`
            : file.truncated
              ? `Opened the first ${humanBytes(limits.max_read_bytes)} of ${file.path}.`
              : `Opened ${file.path}.`,
        )
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause))
      } finally {
        setBusy(null)
      }
    },
    [path, project, limits.max_read_bytes],
  )

  async function save() {
    if (!project || !path.trim()) return
    setBusy('save')
    setError(null)
    setNotice(null)
    try {
      const saved = await api.files.write(project.id, path.trim(), content)
      setOriginal(content)
      setPath(saved.path)
      setBinary(false)
      setNotice(`Saved ${saved.path} (${humanBytes(saved.size)}).`)
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      setError(message)
      reportError(message)
    } finally {
      setBusy(null)
    }
  }

  async function upload(file: File | undefined | null) {
    if (!file || !project) return
    setBusy('upload')
    setError(null)
    setNotice(null)
    try {
      const stored = await api.files.upload(project.id, file)
      setPath(stored.path)
      setOriginal('')
      setContent('')
      setBinary(true)
      setNotice(`Uploaded ${stored.path} (${humanBytes(stored.size)}).`)
      await refreshProjects()
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      setError(message)
      reportError(message)
    } finally {
      setBusy(null)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  if (!project) {
    return (
      <div className="panel">
        <div className="panel__bar">
          <span className="panel__bar-title">Write</span>
        </div>
        <div className="empty">
          <div className="empty__glyph">✎</div>
          <div className="empty__title">No project open</div>
          <div className="empty__text">
            Open or create a project to write files into it.
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="panel">
      <div className="panel__bar">
        <span className="panel__bar-title">Write</span>
        <span className="header__spacer" />
        {dirty && <span className="pill pill--warning">unsaved</span>}
        <span className="hint mono">project: {project.name}</span>
      </div>

      <div className="write__toolbar">
        <input
          className="input mono"
          aria-label="File path"
          placeholder="docs/notes.md"
          value={path}
          onChange={(event) => setPath(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              void openFile()
            }
          }}
        />
        <button
          type="button"
          className="btn btn--sm"
          disabled={busy !== null || !path.trim()}
          onClick={() => void openFile()}
        >
          {busy === 'open' ? 'Opening…' : 'Open'}
        </button>
        <button
          type="button"
          className="btn btn--sm"
          disabled={busy !== null || !path.trim()}
          title="Upload a file into the project, using this path's folder and name"
          onClick={() => fileInput.current?.click()}
        >
          {busy === 'upload' ? 'Uploading…' : 'Upload file'}
        </button>
        <input
          ref={fileInput}
          type="file"
          className="write__file"
          aria-label="Upload a file into the project"
          onChange={(event) => void upload(event.target.files?.[0])}
        />
      </div>

      <div className="panel__body panel__body--flush write__body">
        {binary ? (
          <div className="empty">
            <div className="empty__glyph">📄</div>
            <div className="empty__title">Not a text file</div>
            <div className="empty__text">
              This file was uploaded or is binary. Choose another path, or write to a
              text file instead.
            </div>
          </div>
        ) : (
          <textarea
            className="write__editor mono"
            aria-label="File content"
            placeholder={
              path.trim()
                ? 'Write here, then Save. The coding agent can see this file.'
                : 'Enter a path above and press Open, or start typing to create a new file.'
            }
            value={content}
            spellCheck={false}
            onChange={(event) => setContent(event.target.value)}
          />
        )}
      </div>

      <div className="panel__footer">
        <div className="write__footer">
          <span className="hint">
            {content.length > 0
              ? `${content.length} characters · limit ${humanBytes(limits.max_write_bytes)}`
              : 'Nothing to save yet'}
          </span>
          <div className="form-actions">
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              disabled={!dirty || busy !== null}
              onClick={() => setContent(original)}
            >
              Revert
            </button>
            <button
              type="button"
              className="btn btn--primary btn--sm"
              disabled={!dirty || busy !== null || !path.trim()}
              onClick={() => void save()}
            >
              {busy === 'save' ? 'Saving…' : 'Save'}
            </button>
          </div>
        </div>

        {error && <div className="alert alert--error" role="alert">{error}</div>}
        {notice && !error && (
          <div className="alert alert--info" style={{ marginTop: 8 }}>
            {notice}
          </div>
        )}
      </div>
    </div>
  )
}
