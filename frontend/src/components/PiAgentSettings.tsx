/**
 * Pi Agent configuration, entirely from the Workspace Settings UI.
 *
 * Provider selection, credential entry, validation, model discovery and model
 * selection — the same workflow `/login` and `--model` provide in a terminal,
 * without leaving Solo.
 *
 * The UI distinguishes three states explicitly, and never presents a provider or
 * model as verified unless the corresponding check actually succeeded:
 *
 *   not configured  no credential is stored
 *   configured      a credential is stored (presence checked through Pi)
 *   verified        a real request succeeded with the selected model
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '../api/client'
import { useWorkspace } from '../state/WorkspaceProvider'
import type {
  ConnectionTestResult,
  PiAuthStatus,
  PiModel,
  PiProvider,
  PiStatus,
} from '../types'

const THINKING_LEVELS = ['', 'off', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max']
const MAX_RENDERED_MODELS = 80

type VerifyState = 'unknown' | 'not_configured' | 'configured' | 'verified' | 'failed'

export default function PiAgentSettings() {
  const { refreshSettings, reportError } = useWorkspace()

  const [status, setStatus] = useState<PiStatus | null>(null)
  const [providers, setProviders] = useState<PiProvider[]>([])
  const [models, setModels] = useState<PiModel[]>([])
  const [auth, setAuth] = useState<PiAuthStatus | null>(null)
  const [verify, setVerify] = useState<ConnectionTestResult | null>(null)

  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [thinking, setThinking] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [search, setSearch] = useState('')

  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadStatus = useCallback(async () => {
    try {
      const [statusData, providerData] = await Promise.all([
        api.pi.status(),
        api.pi.providers(),
      ])
      setStatus(statusData)
      setProviders(providerData)
      setProvider((current) => current || statusData.provider || '')
      setModel((current) => current || statusData.model || '')
      setThinking((current) => current || statusData.thinking_level || '')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }, [])

  useEffect(() => {
    void loadStatus()
  }, [loadStatus])

  // Check the credential state whenever the selected provider changes.
  useEffect(() => {
    if (!provider) return
    let cancelled = false
    setVerify(null)
    api.pi
      .auth(provider)
      .then((result) => {
        if (!cancelled) setAuth(result)
      })
      .catch(() => {
        if (!cancelled) setAuth(null)
      })
    return () => {
      cancelled = true
    }
  }, [provider])

  const selected = useMemo(
    () => providers.find((item) => item.id === provider) ?? null,
    [providers, provider],
  )

  const verifyState: VerifyState = useMemo(() => {
    if (verify) {
      if (verify.ok && verify.state === 'verified') return 'verified'
      if (verify.ok) return 'configured'
      return 'failed'
    }
    if (auth?.ready) return 'configured'
    // Pi distinguishes "no credential stored" from other problems; keep that
    // distinction instead of collapsing everything into "unknown".
    if (auth?.reason === 'credentials_not_configured') return 'not_configured'
    return 'unknown'
  }, [verify, auth])

  const filteredModels = useMemo(() => {
    const needle = search.trim().toLowerCase()
    const pool = needle
      ? models.filter(
          (item) =>
            item.id.toLowerCase().includes(needle) || item.name.toLowerCase().includes(needle),
        )
      : models
    return pool
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

  const loadModels = (refresh: boolean) =>
    guarded('models', async () => {
      const list = await api.pi.models(provider || undefined, refresh)
      setModels(list)
      setNotice(
        list.length
          ? `${list.length} model(s) available${provider ? ` for ${provider}` : ''}.`
          : `Pi reported no models${provider ? ` for ${provider}` : ''}. Enter a model ID manually below.`,
      )
    })

  const refreshCatalog = () =>
    guarded('catalog', async () => {
      const result = await api.pi.refreshModels()
      setNotice(result.message)
      if (result.ok) await loadModels(true)
    })

  const saveCredential = () =>
    guarded('credential', async () => {
      if (!apiKey.trim()) return
      const result = await api.pi.saveCredential(provider, apiKey.trim())
      setAuth(result)
      setApiKey('')
      setNotice(
        result.ready
          ? `Credential saved for ${provider}.`
          : `Credential saved, but Pi reports it is not ready (${result.reason ?? result.status}).`,
      )
      await loadStatus()
    })

  const removeCredential = () =>
    guarded('credential', async () => {
      const result = await api.pi.deleteCredential(provider)
      setAuth(result)
      setNotice(`Credential removed for ${provider}.`)
      await loadStatus()
    })

  const reuseOrchestratorKey = () =>
    guarded('credential', async () => {
      const result = await api.pi.credentialFromOrchestrator(provider)
      setAuth(result)
      setNotice(`Copied the Orchestrator's OpenRouter key into Pi for ${provider}.`)
      await loadStatus()
    })

  const runTest = (deep: boolean) =>
    guarded('test', async () => {
      const result = await api.pi.test(provider, { model: model || undefined, deep })
      setVerify(result)
      setNotice(null)
    })

  const saveSelection = () =>
    guarded('selection', async () => {
      await api.settings.update({
        pi_provider: provider,
        pi_model: model,
        pi_thinking_level: thinking,
      })
      await refreshSettings()
      await loadStatus()
      setNotice(`Coding tasks will use ${provider}${model ? ` / ${model}` : ''}.`)
    })

  const toggleTrust = (value: boolean) =>
    guarded('trust', async () => {
      await api.settings.update({ pi_approve_project: value })
      await refreshSettings()
      await loadStatus()
      setNotice(
        value
          ? 'Project-local Pi resources will be trusted.'
          : 'Project-local Pi resources will be ignored.',
      )
    })

  return (
    <div className="settings-pane">
      {/* ---------------- runtime ---------------- */}
      <section className="settings-section">
        <div className="settings-section__head">
          <h3 className="settings-section__title">Runtime</h3>
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => void loadStatus()}
            disabled={busy === 'status'}
          >
            Refresh
          </button>
        </div>

        <dl className="detail-grid">
          <dt>Backend</dt>
          <dd>
            <span className={`pill ${status?.backend === 'pi' ? 'pill--success' : 'pill--neutral'}`}>
              {status?.backend === 'pi' ? 'Pi Agent' : 'Simulator'}
            </span>
          </dd>
          <dt>Pi CLI</dt>
          <dd>
            {status?.runtime.available ? (
              <>
                {status.runtime.version ?? 'detected'}{' '}
                <span className="hint mono">{status.runtime.executable}</span>
              </>
            ) : (
              <span className="text-danger">{status?.runtime.detail ?? 'not detected'}</span>
            )}
          </dd>
          <dt>Agent dir</dt>
          <dd className="mono">{status?.agent_dir ?? '—'}</dd>
          <dt>Credentials</dt>
          <dd className="mono">{status?.auth_file ?? '—'}</dd>
          <dt>Sessions</dt>
          <dd>
            {status?.sessions.length
              ? status.sessions.map((item) => (
                  <div key={item.cwd} className="mono" style={{ fontSize: 11.5 }}>
                    {item.busy ? '● running' : '○ idle'} · {item.model ?? 'no model'} ·{' '}
                    {item.cwd}
                  </div>
                ))
              : 'none running'}
          </dd>
        </dl>

        {!status?.runtime.available && (
          <div className="alert alert--error" role="alert" style={{ marginTop: 10 }}>
            {status?.runtime.detail}
          </div>
        )}
      </section>

      {/* ---------------- provider + credential ---------------- */}
      <section className="settings-section">
        <div className="settings-section__head">
          <h3 className="settings-section__title">Provider and credentials</h3>
          <StateBadge state={verifyState} />
        </div>

        <div className="settings-grid">
          <div className="field">
            <label htmlFor="pi-provider">Provider</label>
            <select
              id="pi-provider"
              className="input"
              value={provider}
              onChange={(event) => setProvider(event.target.value)}
            >
              <option value="">— choose a provider —</option>
              {providers.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                  {item.configured ? ' ✓' : ''}
                  {item.model_count ? ` · ${item.model_count} models` : ''}
                </option>
              ))}
            </select>
            {selected && (
              <span className="hint">
                {selected.configured
                  ? `Credential source: ${selected.source}`
                  : 'No credential configured'}
                {selected.env_var ? ` · environment variable ${selected.env_var}` : ''}
              </span>
            )}
          </div>

          <div className="field">
            <label htmlFor="pi-key">
              API key{' '}
              <span className="hint">
                {auth?.ready ? '— stored by Pi' : '— write-only, stored via Pi'}
              </span>
            </label>
            <input
              id="pi-key"
              className="input"
              type="password"
              autoComplete="off"
              placeholder={auth?.ready ? 'Replace the stored key' : 'Paste the provider API key'}
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
            />
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn btn--primary btn--sm"
              disabled={!provider || !apiKey.trim() || busy === 'credential'}
              onClick={() => void saveCredential()}
            >
              {busy === 'credential' ? 'Saving…' : 'Save credential'}
            </button>
            {provider === 'openrouter' && (
              <button
                type="button"
                className="btn btn--sm"
                disabled={busy === 'credential'}
                onClick={() => void reuseOrchestratorKey()}
              >
                Use the Orchestrator key
              </button>
            )}
            <button
              type="button"
              className="btn btn--danger btn--sm"
              disabled={!provider || busy === 'credential'}
              onClick={() => void removeCredential()}
            >
              Remove
            </button>
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn btn--sm"
              disabled={!provider || busy === 'test'}
              onClick={() => void runTest(false)}
            >
              Check configuration
            </button>
            <button
              type="button"
              className="btn btn--sm"
              disabled={!provider || !model || busy === 'test'}
              title="Sends one minimal request so the provider actually accepts the credential"
              onClick={() => void runTest(true)}
            >
              Verify with a real request
            </button>
          </div>

          {verify && <TestResult result={verify} />}
          {!verify && auth && (
            <p className="hint">
              {auth.ready
                ? `Pi reports ${provider} is ready (${auth.auth_type ?? 'api_key'}). Run a real request to verify it.`
                : `Pi reports ${provider} is not ready: ${auth.reason ?? auth.status}`}
            </p>
          )}
        </div>
      </section>

      {/* ---------------- model ---------------- */}
      <section className="settings-section">
        <div className="settings-section__head">
          <h3 className="settings-section__title">Model</h3>
          <div className="form-actions">
            <button
              type="button"
              className="btn btn--sm"
              disabled={busy === 'models'}
              onClick={() => void loadModels(false)}
            >
              {busy === 'models' ? 'Loading…' : 'Discover models'}
            </button>
            <button
              type="button"
              className="btn btn--sm"
              disabled={busy === 'catalog'}
              onClick={() => void refreshCatalog()}
            >
              {busy === 'catalog' ? 'Refreshing…' : 'Refresh catalog'}
            </button>
          </div>
        </div>

        <div className="settings-grid">
          <div className="field">
            <label htmlFor="pi-model">Model ID</label>
            <input
              id="pi-model"
              className="input mono"
              placeholder="e.g. vendor/model-name"
              value={model}
              onChange={(event) => setModel(event.target.value)}
            />
            <span className="hint">
              Discovered models appear below. Providers without a discoverable
              catalog can be configured by typing the ID here.
            </span>
          </div>

          <div className="field">
            <label htmlFor="pi-thinking">Reasoning level</label>
            <select
              id="pi-thinking"
              className="input"
              value={thinking}
              onChange={(event) => setThinking(event.target.value)}
            >
              {THINKING_LEVELS.map((level) => (
                <option key={level || 'default'} value={level}>
                  {level || 'using Pi default'}
                </option>
              ))}
            </select>
          </div>

          {models.length > 0 && (
            <>
              <input
                className="input"
                placeholder="Filter models…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                aria-label="Filter models"
              />
              <ul className="model-list" role="listbox" aria-label="Available models">
                {filteredModels.slice(0, MAX_RENDERED_MODELS).map((item) => (
                  <li key={`${item.provider}/${item.id}`}>
                    <button
                      type="button"
                      role="option"
                      aria-selected={item.id === model}
                      className={`model-list__item ${item.id === model ? 'model-list__item--selected' : ''}`}
                      onClick={() => setModel(item.id)}
                    >
                      <span className="model-list__id mono">{item.id}</span>
                      <span className="model-list__meta">
                        {item.reasoning && <span className="pill pill--active">reasoning</span>}
                        {item.context_window && (
                          <span className="hint">
                            {Math.round(item.context_window / 1000)}K ctx
                          </span>
                        )}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              {filteredModels.length > MAX_RENDERED_MODELS && (
                <p className="hint">
                  Showing the first {MAX_RENDERED_MODELS} of {filteredModels.length}. Refine the
                  filter to narrow the list.
                </p>
              )}
            </>
          )}

          <div className="form-actions">
            <button
              type="button"
              className="btn btn--primary btn--sm"
              disabled={!provider || busy === 'selection'}
              onClick={() => void saveSelection()}
            >
              {busy === 'selection' ? 'Saving…' : 'Save selection'}
            </button>
          </div>
        </div>
      </section>

      {/* ---------------- safety ---------------- */}
      <section className="settings-section">
        <h3 className="settings-section__title">Execution safety</h3>
        <div className="settings-grid">
          <label className="checkbox">
            <input
              type="checkbox"
              checked={status?.approve_project ?? false}
              disabled={busy === 'trust'}
              onChange={(event) => void toggleTrust(event.target.checked)}
            />
            Trust project-local Pi resources (<span className="mono">.pi/</span> settings,
            extensions, skills)
          </label>
          <span className="hint">
            Off by default: Solo runs Pi non-interactively, so an explicit decision keeps
            behaviour predictable and stops a project silently loading executable code into
            the agent process. Built-in tools (<span className="mono">read</span>,{' '}
            <span className="mono">bash</span>, <span className="mono">edit</span>,{' '}
            <span className="mono">write</span>) are unaffected.
          </span>
        </div>
      </section>

      {error && <div className="alert alert--error">{error}</div>}
      {notice && !error && <div className="alert alert--info">{notice}</div>}
    </div>
  )
}

function StateBadge({ state }: { state: VerifyState }) {
  // aria-label so assistive technology (and tests) can address the state
  // unambiguously rather than guessing which "configured" text is meant.
  const label = state === 'not_configured' ? 'not configured' : state
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
      {label}
    </span>
  )
}

function TestResult({ result }: { result: ConnectionTestResult }) {
  return (
    <div
      className={`test-result alert ${result.ok ? 'alert--info' : 'alert--error'}`}
      role="status"
    >
      <strong>{result.state ?? (result.ok ? 'ok' : 'failed')}</strong> — {result.message}
      {result.latency_ms != null && <span className="hint"> ({result.latency_ms} ms)</span>}
      {result.detail && <div className="hint">{result.detail}</div>}
    </div>
  )
}
