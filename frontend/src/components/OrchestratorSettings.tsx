/**
 * Orchestrator (OpenRouter) configuration.
 *
 * The Orchestrator model handles intent detection, task prioritisation, state
 * management and progress summarisation. This pane configures it end to end:
 * key entry, connectivity test, model discovery, model selection and the
 * enabled toggle — and the selected model is what the backend actually calls.
 *
 * Three states are shown distinctly and honestly: a key can be *saved*, the key
 * can be *valid*, and the selected model can be *verified* by a real completion.
 * Nothing is labelled verified until a real request succeeds.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '../api/client'
import { useWorkspace } from '../state/WorkspaceProvider'
import type { ConnectionTestResult, OpenRouterModel, OrchestratorStatus } from '../types'

const MAX_RENDERED = 60

export default function OrchestratorSettings() {
  const { settings, refreshSettings, reportError } = useWorkspace()

  const [status, setStatus] = useState<OrchestratorStatus | null>(null)
  const [models, setModels] = useState<OpenRouterModel[]>([])
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [search, setSearch] = useState('')
  const [result, setResult] = useState<ConnectionTestResult | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const loadStatus = useCallback(async () => {
    try {
      const data = await api.orchestrator.status()
      setStatus(data)
      setModel((current) => current || data.model || '')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }, [])

  useEffect(() => {
    void loadStatus()
  }, [loadStatus])

  const hasStoredKey = settings?.openrouter_api_key.configured ?? false

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return models
    return models.filter(
      (item) =>
        item.id.toLowerCase().includes(needle) || item.name.toLowerCase().includes(needle),
    )
  }, [models, search])

  async function guarded(key: string, action: () => Promise<void>) {
    setBusy(key)
    setError(null)
    setNotice(null)
    try {
      await action()
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause)
      setError(message)
      reportError(message)
    } finally {
      setBusy(null)
    }
  }

  const saveKey = () =>
    guarded('key', async () => {
      if (!apiKey.trim()) return
      await api.settings.update({ openrouter_api_key: apiKey.trim() })
      setApiKey('')
      await refreshSettings()
      await loadStatus()
      setResult(null)
      setNotice('API key saved. Run a test to confirm the key and model work.')
    })

  const removeKey = () =>
    guarded('key', async () => {
      await api.settings.removeSecret('openrouter_api_key')
      await refreshSettings()
      await loadStatus()
      setModels([])
      setResult(null)
      setNotice('API key removed. The Orchestrator will fall back to deterministic rules.')
    })

  const testKey = (deep: boolean) =>
    guarded('test', async () => {
      const outcome = await api.orchestrator.test({ model: model || undefined, deep })
      setResult(outcome)
    })

  const discover = () =>
    guarded('models', async () => {
      const list = await api.orchestrator.models()
      setModels(list)
      setNotice(`${list.length} model(s) available from OpenRouter.`)
    })

  const saveModel = () =>
    guarded('model', async () => {
      await api.orchestrator.config({ model })
      await refreshSettings()
      await loadStatus()
      setResult(null)
      setNotice(`The Orchestrator will use ${model}.`)
    })

  const toggleEnabled = (enabled: boolean) =>
    guarded('toggle', async () => {
      await api.orchestrator.config({ enabled })
      await refreshSettings()
      await loadStatus()
      setNotice(
        enabled
          ? 'The Orchestrator model is enabled.'
          : 'The Orchestrator model is disabled; deterministic rules will be used.',
      )
    })

  const state = result
    ? result.ok
      ? (result.state ?? 'configured')
      : 'failed'
    : status?.configured
      ? 'configured'
      : status?.has_key
        ? 'saved'
        : 'not configured'

  return (
    <div className="settings-pane">
      <section className="settings-section">
        <div className="settings-section__head">
          <h3 className="settings-section__title">OpenRouter</h3>
          <StatePill state={state} />
        </div>

        <div className="settings-grid">
          <div className="field">
            <label htmlFor="or-key">
              API key{' '}
              <span className="hint">
                {hasStoredKey ? `— saved (${status?.key_masked ?? 'stored'})` : '— not saved'}
              </span>
            </label>
            <input
              id="or-key"
              className="input"
              type="password"
              autoComplete="off"
              placeholder={hasStoredKey ? 'Replace the saved key' : 'sk-or-v1-…'}
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
            />
            <span className="hint">
              Stored encrypted on the server and never returned to the browser.
            </span>
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn btn--primary btn--sm"
              disabled={!apiKey.trim() || busy === 'key'}
              onClick={() => void saveKey()}
            >
              {busy === 'key' ? 'Saving…' : 'Save key'}
            </button>
            <button
              type="button"
              className="btn btn--sm"
              disabled={!hasStoredKey || busy === 'test'}
              onClick={() => void testKey(false)}
            >
              Test key
            </button>
            <button
              type="button"
              className="btn btn--sm"
              disabled={!hasStoredKey || !model || busy === 'test'}
              title="Runs one real completion with the selected model"
              onClick={() => void testKey(true)}
            >
              Verify model
            </button>
            <button
              type="button"
              className="btn btn--danger btn--sm"
              disabled={!hasStoredKey || busy === 'key'}
              onClick={() => void removeKey()}
            >
              Remove key
            </button>
          </div>

          {result && (
            <div
              className={`test-result alert ${result.ok ? 'alert--info' : 'alert--error'}`}
              role="status"
            >
              <strong>{result.state ?? (result.ok ? 'ok' : 'failed')}</strong> — {result.message}
              {result.model && <span className="hint"> · {result.model}</span>}
              {result.latency_ms != null && (
                <span className="hint"> · {result.latency_ms} ms</span>
              )}
              {result.detail && <div className="hint">{result.detail}</div>}
            </div>
          )}
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section__head">
          <h3 className="settings-section__title">Orchestrator model</h3>
          <button
            type="button"
            className="btn btn--sm"
            disabled={!hasStoredKey || busy === 'models'}
            onClick={() => void discover()}
          >
            {busy === 'models' ? 'Loading…' : 'Retrieve models'}
          </button>
        </div>

        <div className="settings-grid">
          <div className="field">
            <label htmlFor="or-model">Model ID</label>
            <input
              id="or-model"
              className="input mono"
              placeholder="e.g. anthropic/claude-sonnet-4.5"
              value={model}
              onChange={(event) => setModel(event.target.value)}
            />
            <span className="hint">
              Used for intent detection, task prioritisation, state management and progress
              summaries.
            </span>
          </div>

          {models.length > 0 && (
            <>
              <input
                className="input"
                placeholder="Filter models…"
                aria-label="Filter models"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              <ul className="model-list" role="listbox" aria-label="Available OpenRouter models">
                {filtered.slice(0, MAX_RENDERED).map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={item.id === model}
                      className={`model-list__item ${item.id === model ? 'model-list__item--selected' : ''}`}
                      onClick={() => setModel(item.id)}
                    >
                      <span className="model-list__id mono">{item.id}</span>
                      <span className="model-list__meta">
                        {item.supports_structured_output && (
                          <span className="pill pill--active">structured</span>
                        )}
                        {item.context_length && (
                          <span className="hint">{Math.round(item.context_length / 1000)}K ctx</span>
                        )}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              <p className="hint">
                Showing {Math.min(filtered.length, MAX_RENDERED)} of {filtered.length} models.
              </p>
            </>
          )}

          <div className="form-actions">
            <button
              type="button"
              className="btn btn--primary btn--sm"
              disabled={!model || busy === 'model'}
              onClick={() => void saveModel()}
            >
              {busy === 'model' ? 'Saving…' : 'Save model'}
            </button>
          </div>
        </div>
      </section>

      <section className="settings-section">
        <h3 className="settings-section__title">Behaviour</h3>
        <div className="settings-grid">
          <label className="checkbox">
            <input
              type="checkbox"
              checked={status?.enabled ?? true}
              disabled={busy === 'toggle'}
              onChange={(event) => void toggleEnabled(event.target.checked)}
            />
            Use the Orchestrator model for intent detection, planning and summaries
          </label>
          <span className="hint">
            When disabled — or when no key is saved — Solo falls back to deterministic rules and
            answers questions from the project snapshot. Nothing stops working.
          </span>

          {status && status.call_count > 0 && (
            <dl className="detail-grid">
              <dt>Calls</dt>
              <dd>
                {status.call_count} ({status.failure_count} failed)
              </dd>
              <dt>Last model</dt>
              <dd className="mono">{status.last_model ?? '—'}</dd>
              <dt>Last latency</dt>
              <dd>{status.last_latency_ms != null ? `${status.last_latency_ms} ms` : '—'}</dd>
              {status.last_error && (
                <>
                  <dt>Last error</dt>
                  <dd className="text-danger">{status.last_error}</dd>
                </>
              )}
            </dl>
          )}
        </div>
      </section>

      {error && <div className="alert alert--error">{error}</div>}
      {notice && !error && <div className="alert alert--info">{notice}</div>}
    </div>
  )
}

function StatePill({ state }: { state: string }) {
  const tone =
    state === 'verified'
      ? 'success'
      : state === 'configured'
        ? 'warning'
        : state === 'failed'
          ? 'danger'
          : 'neutral'
  return (
    <span className={`pill pill--${tone}`} aria-label="configuration state">
      {state === 'saved' ? 'key saved' : state}
    </span>
  )
}
