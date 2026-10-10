/**
 * Server-side directory browser used by "Open Project".
 *
 * Lists directories only — never file contents — and delegates every policy
 * decision to the backend (`GET /api/fs/list`), which enforces the blocked-path
 * list, the optional allow-list and symlink resolution.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '../api/client'
import type { FsListing } from '../types'

export default function DirectoryBrowser({
  value,
  onChange,
}: {
  value: string
  onChange: (path: string) => void
}) {
  const [listing, setListing] = useState<FsListing | null>(null)
  const [draft, setDraft] = useState(value)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  const load = useCallback(
    async (target?: string, notify = true) => {
      setLoading(true)
      setError(null)
      try {
        const result = await api.fs.list(target)
        setListing(result)
        setDraft(result.path)
        // The initial listing is informational; the parent is only updated once
        // the user actually navigates, so a typed path is never overwritten.
        if (notify) onChangeRef.current(result.path)
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause))
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  // Load once on mount without claiming a selection.
  useEffect(() => {
    void load(value || undefined, false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="browser">
      <div className="browser__bar">
        <button
          type="button"
          className="btn btn--sm"
          disabled={!listing?.parent || loading}
          onClick={() => void load(listing?.parent ?? undefined)}
        >
          ↑ Up
        </button>
        <button type="button" className="btn btn--sm" onClick={() => void load()}>
          Home
        </button>
        {listing && listing.roots.length > 0 && (
          <select
            className="input browser__roots"
            aria-label="Jump to a root"
            value=""
            onChange={(event) => {
              if (event.target.value) void load(event.target.value)
            }}
          >
            <option value="">Jump to…</option>
            {listing.roots.map((root) => (
              <option key={root} value={root}>
                {root}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="browser__bar">
        <input
          className="input mono"
          aria-label="Directory path"
          value={draft}
          spellCheck={false}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              void load(draft)
            }
          }}
        />
        <button
          type="button"
          className="btn btn--sm"
          disabled={loading}
          onClick={() => void load(draft)}
        >
          Go
        </button>
      </div>

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}

      <ul className="browser__list">
        {listing?.entries.length === 0 && !loading && !error && (
          <li className="browser__empty">No sub-directories here.</li>
        )}
        {listing?.entries.map((entry) => (
          <li key={entry.path}>
            <button
              type="button"
              className="browser__entry"
              onClick={() => void load(entry.path)}
              title={entry.path}
            >
              <span aria-hidden="true">{entry.hidden ? '·' : '📁'}</span>
              <span className="browser__name">{entry.name}</span>
              {entry.is_project && <span className="pill pill--active">Solo</span>}
            </button>
          </li>
        ))}
      </ul>

      {listing?.truncated && (
        <p className="hint">
          Only the first {listing.entries.length} directories are listed.
        </p>
      )}

      <p className="hint">
        Selected folder:{' '}
        <span className="mono">{value || 'none — choose a folder below'}</span>
      </p>
    </div>
  )
}
