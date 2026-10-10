/**
 * Project state panel (shown in the Inspector).
 *
 * Renders the structured, tree-shaped project state written by Solo into
 * `<project-root>/.solo/`, plus the project's memory entries and per-project
 * configuration (tree bounds, memory limits, session retention, auto-refresh).
 */

import { useCallback, useEffect, useState } from 'react'

import { api } from '../api/client'
import type {
  MemoryEntry,
  ProjectConfig,
  ProjectSummary,
  ProjectTree,
  TreeNode,
} from '../types'
import { relativeTime } from '../utils/format'

type Tab = 'tree' | 'memory' | 'config'

const TABS: { id: Tab; label: string }[] = [
  { id: 'tree', label: 'State tree' },
  { id: 'memory', label: 'Memory' },
  { id: 'config', label: 'Config' },
]

export default function ProjectStatePanel({ projectId }: { projectId: string }) {
  const [tab, setTab] = useState<Tab>('tree')
  const [tree, setTree] = useState<ProjectTree | null>(null)
  const [summary, setSummary] = useState<ProjectSummary | null>(null)
  const [memory, setMemory] = useState<MemoryEntry[]>([])
  const [config, setConfig] = useState<ProjectConfig | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(
    async (refresh = false) => {
      setLoading(true)
      setError(null)
      try {
        const [treeData, summaryData, memoryData, configData] = await Promise.all([
          api.projects.tree(projectId, refresh),
          api.projects.summary(projectId),
          api.projects.memory.list(projectId),
          api.projects.config(projectId),
        ])
        setTree(treeData)
        setSummary(summaryData)
        setMemory(memoryData)
        setConfig(configData)
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause))
      } finally {
        setLoading(false)
      }
    },
    [projectId],
  )

  useEffect(() => {
    void load(false)
  }, [load])

  return (
    <div className="state-panel">
      <div className="state-panel__toolbar">
        <div className="stacked__tabs" style={{ border: 'none', padding: 0 }}>
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              className={`stacked__tab ${tab === item.id ? 'stacked__tab--active' : ''}`}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="btn btn--sm"
          disabled={loading}
          onClick={() => void load(true)}
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}
      {notice && <div className="alert alert--info">{notice}</div>}

      {tab === 'tree' && (
        <>
          {summary && (
            <>
              <div className="stat-grid">
                <Stat label="Files" value={summary.file_count} />
                <Stat label="Folders" value={summary.directory_count} />
                <Stat label="Tasks" value={summary.task_count} />
                <Stat label="Sessions" value={summary.session_count} />
                <Stat label="Memory" value={summary.memory_count} />
              </div>
              <dl className="detail-grid" style={{ marginTop: 10 }}>
                <dt>Root</dt>
                <dd className="mono">{summary.root}</dd>
                <dt>State</dt>
                <dd className="mono">
                  {summary.metadata_dir}/state/tree.json
                </dd>
                <dt>Built</dt>
                <dd>
                  {summary.tree_generated_at
                    ? relativeTime(summary.tree_generated_at)
                    : '—'}
                </dd>
              </dl>
            </>
          )}

          {tree ? (
            <div className="tree" role="tree" aria-label="Project state tree">
              <TreeNodeRow node={tree.root} depth={0} defaultOpen />
            </div>
          ) : (
            !error && <p className="hint">Loading project state…</p>
          )}
        </>
      )}

      {tab === 'memory' && (
        <MemorySection
          projectId={projectId}
          entries={memory}
          onChanged={async () => {
            await load(true)
          }}
        />
      )}

      {tab === 'config' && config && (
        <ConfigSection
          projectId={projectId}
          config={config}
          onSaved={async (saved) => {
            setConfig(saved)
            setNotice('Project configuration saved.')
            await load(true)
          }}
        />
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat">
      <span className="stat__value">{value}</span>
      <span className="stat__label">{label}</span>
    </div>
  )
}

/** Recursive tree row with expand/collapse. */
function TreeNodeRow({
  node,
  depth,
  defaultOpen = false,
}: {
  node: TreeNode
  depth: number
  defaultOpen?: boolean
}) {
  const children = node.children ?? []
  const [open, setOpen] = useState(defaultOpen || node.kind === 'group')
  const hasChildren = children.length > 0

  const glyph =
    node.kind === 'group'
      ? '▣'
      : node.kind === 'directory'
        ? '📁'
        : node.kind === 'task'
          ? '◆'
          : node.kind === 'memory'
            ? '✎'
            : node.kind === 'session'
              ? '✦'
              : node.kind === 'project'
                ? '◆'
                : '·'

  return (
    <div className="tree__node" role="treeitem" aria-expanded={hasChildren ? open : undefined}>
      <button
        type="button"
        className="tree__row"
        style={{ paddingLeft: 6 + depth * 14 }}
        onClick={() => hasChildren && setOpen((value) => !value)}
        disabled={!hasChildren}
      >
        <span className="tree__chevron" aria-hidden="true">
          {hasChildren ? (open ? '▾' : '▸') : ''}
        </span>
        <span className="tree__glyph" aria-hidden="true">
          {glyph}
        </span>
        <span className="tree__name" title={node.ref ?? node.path ?? node.name}>
          {node.name}
        </span>
        {node.status && <span className="pill pill--neutral">{node.status}</span>}
        {typeof node.messages === 'number' && (
          <span className="hint">{node.messages} msg</span>
        )}
        {node.kind === 'file' && node.ext && <span className="hint">{node.ext}</span>}
      </button>

      {open && hasChildren && (
        <div role="group">
          {children.map((child) => (
            <TreeNodeRow key={child.id} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

function MemorySection({
  projectId,
  entries,
  onChanged,
}: {
  projectId: string
  entries: MemoryEntry[]
  onChanged: () => Promise<void>
}) {
  const [text, setText] = useState('')
  const [kind, setKind] = useState('note')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function add() {
    if (!text.trim()) return
    setBusy(true)
    setError(null)
    try {
      await api.projects.memory.add(projectId, { text: text.trim(), kind })
      setText('')
      await onChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  async function remove(id: string) {
    try {
      await api.projects.memory.remove(projectId, id)
      await onChanged()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }

  return (
    <div className="memory">
      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}

      <div className="memory__compose">
        <input
          className="input"
          aria-label="New memory entry"
          placeholder="Record a decision, fact or note…"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault()
              void add()
            }
          }}
        />
        <select
          className="input"
          aria-label="Memory kind"
          value={kind}
          onChange={(event) => setKind(event.target.value)}
        >
          <option value="note">Note</option>
          <option value="decision">Decision</option>
          <option value="fact">Fact</option>
          <option value="todo">Todo</option>
        </select>
        <button
          type="button"
          className="btn btn--primary btn--sm"
          disabled={busy || !text.trim()}
          onClick={() => void add()}
        >
          Add
        </button>
      </div>

      {entries.length === 0 ? (
        <p className="hint">
          No memory yet. Entries are stored in{' '}
          <span className="mono">.solo/memory/entries/</span> and travel with the
          project.
        </p>
      ) : (
        <ul className="list">
          {entries.map((entry) => (
            <li key={entry.id} className="memory__item">
              <div className="memory__head">
                <span className="pill pill--neutral">{entry.kind}</span>
                <span className="hint">{relativeTime(entry.created_at ?? '')}</span>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  aria-label="Delete memory entry"
                  onClick={() => void remove(entry.id)}
                >
                  ✕
                </button>
              </div>
              <div className="memory__text">{entry.text}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ConfigSection({
  projectId,
  config,
  onSaved,
}: {
  projectId: string
  config: ProjectConfig
  onSaved: (saved: ProjectConfig) => Promise<void> | void
}) {
  const [draft, setDraft] = useState<ProjectConfig>(config)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => setDraft(config), [config])

  function numberOrNull(value: string): number | null {
    const trimmed = value.trim()
    if (!trimmed) return null
    const parsed = Number(trimmed)
    return Number.isFinite(parsed) ? parsed : null
  }

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const saved = await api.projects.updateConfig(projectId, draft)
      await onSaved(saved)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="config">
      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}

      <h3 className="section__title">Project tree</h3>
      <div className="settings-grid">
        <div className="field">
          <label htmlFor="cfg-depth">Max depth</label>
          <input
            id="cfg-depth"
            className="input"
            type="number"
            min={1}
            max={40}
            placeholder="application default"
            value={draft.tree?.max_depth ?? ''}
            onChange={(event) =>
              setDraft({
                ...draft,
                tree: { ...draft.tree, max_depth: numberOrNull(event.target.value) },
              })
            }
          />
        </div>
        <div className="field">
          <label htmlFor="cfg-entries">Max entries</label>
          <input
            id="cfg-entries"
            className="input"
            type="number"
            min={100}
            placeholder="application default"
            value={draft.tree?.max_entries ?? ''}
            onChange={(event) =>
              setDraft({
                ...draft,
                tree: { ...draft.tree, max_entries: numberOrNull(event.target.value) },
              })
            }
          />
        </div>
        <div className="field">
          <label htmlFor="cfg-exclude">Excluded names (comma separated)</label>
          <input
            id="cfg-exclude"
            className="input mono"
            placeholder="node_modules, dist"
            value={(draft.tree?.exclude ?? []).join(', ')}
            onChange={(event) =>
              setDraft({
                ...draft,
                tree: {
                  ...draft.tree,
                  exclude: event.target.value
                    .split(',')
                    .map((item) => item.trim())
                    .filter(Boolean),
                },
              })
            }
          />
        </div>
      </div>

      <h3 className="section__title" style={{ marginTop: 16 }}>
        Memory
      </h3>
      <div className="settings-grid">
        <div className="field">
          <label htmlFor="cfg-memory-max">Max retained entries</label>
          <input
            id="cfg-memory-max"
            className="input"
            type="number"
            min={1}
            value={draft.memory?.max_entries ?? ''}
            onChange={(event) =>
              setDraft({
                ...draft,
                memory: {
                  ...draft.memory,
                  max_entries: numberOrNull(event.target.value) ?? undefined,
                },
              })
            }
          />
        </div>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={draft.memory?.auto_capture ?? true}
            onChange={(event) =>
              setDraft({
                ...draft,
                memory: { ...draft.memory, auto_capture: event.target.checked },
              })
            }
          />
          Capture memory automatically from completed tasks
        </label>
      </div>

      <h3 className="section__title" style={{ marginTop: 16 }}>
        Sessions and state
      </h3>
      <div className="settings-grid">
        <div className="field">
          <label htmlFor="cfg-sessions">Retained session records</label>
          <input
            id="cfg-sessions"
            className="input"
            type="number"
            min={1}
            value={draft.sessions?.max_sessions ?? ''}
            onChange={(event) =>
              setDraft({
                ...draft,
                sessions: {
                  ...draft.sessions,
                  max_sessions: numberOrNull(event.target.value) ?? undefined,
                },
              })
            }
          />
        </div>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={draft.state?.auto_refresh ?? true}
            onChange={(event) =>
              setDraft({
                ...draft,
                state: { ...draft.state, auto_refresh: event.target.checked },
              })
            }
          />
          Refresh the state tree automatically when a task settles
        </label>
      </div>

      <div className="header__group" style={{ justifyContent: 'flex-end', marginTop: 16 }}>
        <button type="button" className="btn btn--ghost btn--sm" onClick={() => setDraft(config)}>
          Reset
        </button>
        <button
          type="button"
          className="btn btn--primary btn--sm"
          disabled={busy}
          onClick={() => void save()}
        >
          {busy ? 'Saving…' : 'Save configuration'}
        </button>
      </div>

      <details style={{ marginTop: 14 }}>
        <summary className="hint">Stored configuration (config.json)</summary>
        <pre className="mono config__json">{JSON.stringify(config, null, 2)}</pre>
      </details>
    </div>
  )
}
