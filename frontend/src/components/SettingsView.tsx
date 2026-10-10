/**
 * Settings screen.
 *
 * Secrets are write-only from the UI's perspective: existing keys are shown as
 * a masked status, never as a value. Every provider has an explicit
 * "Test connection" action that validates against the real service.
 */

import { useState, type FormEvent } from 'react'

import { api } from '../api/client'
import { useWorkspace } from '../state/WorkspaceProvider'
import type { ConnectionTestResult, SettingsPatch } from '../types'

type ProviderKey = 'openrouter' | 'elevenlabs' | 'pi'

export default function SettingsView({ onClose }: { onClose: () => void }) {
  const { settings, refreshSettings } = useWorkspace()

  const [openrouterKey, setOpenrouterKey] = useState('')
  const [openrouterModel, setOpenrouterModel] = useState(settings?.openrouter_model ?? '')
  const [elevenKey, setElevenKey] = useState('')
  const [agentId, setAgentId] = useState(settings?.elevenlabs_agent_id ?? '')
  const [voiceId, setVoiceId] = useState(settings?.elevenlabs_tts_voice_id ?? '')
  const [piProvider, setPiProvider] = useState(settings?.pi_provider ?? '')
  const [piModel, setPiModel] = useState(settings?.pi_model ?? '')
  const [piBaseUrl, setPiBaseUrl] = useState(settings?.pi_base_url ?? '')
  const [reuseOpenRouterKey, setReuseOpenRouterKey] = useState(
    settings?.pi_reuse_openrouter_key ?? false,
  )
  const [voiceEnabled, setVoiceEnabled] = useState(settings?.voice_enabled ?? true)
  const [speechEnabled, setSpeechEnabled] = useState(
    settings?.progress_speech_enabled ?? true,
  )

  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tests, setTests] = useState<Partial<Record<ProviderKey, ConnectionTestResult>>>({})

  async function save(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setStatus(null)

    const patch: SettingsPatch = {
      openrouter_model: openrouterModel,
      elevenlabs_agent_id: agentId,
      elevenlabs_tts_voice_id: voiceId,
      pi_provider: piProvider,
      pi_model: piModel,
      pi_base_url: piBaseUrl,
      pi_reuse_openrouter_key: reuseOpenRouterKey,
      voice_enabled: voiceEnabled,
      progress_speech_enabled: speechEnabled,
    }
    // Only send secret fields when the user actually typed a new value.
    if (openrouterKey) patch.openrouter_api_key = openrouterKey
    if (elevenKey) patch.elevenlabs_api_key = elevenKey

    try {
      await api.settings.update(patch)
      setOpenrouterKey('')
      setElevenKey('')
      await refreshSettings()
      setStatus('Settings saved.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  async function removeSecret(key: 'openrouter_api_key' | 'elevenlabs_api_key') {
    try {
      await api.settings.removeSecret(key)
      await refreshSettings()
      setStatus('Key removed.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }

  async function runTest(provider: ProviderKey) {
    setTests((previous) => ({ ...previous, [provider]: undefined }))
    try {
      const result = await api.settings.test(provider)
      setTests((previous) => ({ ...previous, [provider]: result }))
    } catch (cause) {
      setTests((previous) => ({
        ...previous,
        [provider]: {
          ok: false,
          message: cause instanceof Error ? cause.message : String(cause),
          detail: null,
        },
      }))
    }
  }

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Settings">
      <form className="card card--wide" onSubmit={save}>
        <div className="settings-section__head">
          <div>
            <h1 className="card__title">Settings</h1>
            <p className="card__subtitle" style={{ marginBottom: 0 }}>
              Credentials are stored server-side, encrypted at rest, and never
              returned to the browser.
            </p>
          </div>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Close
          </button>
        </div>

        {error && (
          <div className="alert alert--error" role="alert" style={{ margin: '14px 0' }}>
            {error}
          </div>
        )}
        {status && !error && (
          <div className="alert alert--info" style={{ margin: '14px 0' }}>
            {status}
          </div>
        )}

        {/* ---------------- OpenRouter ---------------- */}
        <section className="settings-section">
          <div className="settings-section__head">
            <h2 className="settings-section__title">OpenRouter</h2>
            <button
              type="button"
              className="btn btn--sm"
              onClick={() => void runTest('openrouter')}
            >
              Test connection
            </button>
          </div>

          <div className="settings-grid">
            <div className="field">
              <label htmlFor="openrouter-key">
                API key{' '}
                <span className="hint">
                  {settings?.openrouter_api_key.configured
                    ? `— configured (${settings.openrouter_api_key.masked})`
                    : '— not configured'}
                </span>
              </label>
              <input
                id="openrouter-key"
                className="input"
                type="password"
                autoComplete="off"
                placeholder={
                  settings?.openrouter_api_key.configured
                    ? 'Leave blank to keep the current key'
                    : 'sk-or-v1-…'
                }
                value={openrouterKey}
                onChange={(event) => setOpenrouterKey(event.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="openrouter-model">Model ID</label>
              <input
                id="openrouter-model"
                className="input"
                placeholder="e.g. anthropic/claude-3.5-sonnet"
                value={openrouterModel}
                onChange={(event) => setOpenrouterModel(event.target.value)}
              />
              <span className="hint">
                Used for intent routing, progress summaries and project Q&amp;A.
              </span>
            </div>

            {settings?.openrouter_api_key.configured && (
              <button
                type="button"
                className="btn btn--danger btn--sm"
                onClick={() => void removeSecret('openrouter_api_key')}
              >
                Remove stored key
              </button>
            )}
          </div>

          <TestResult result={tests.openrouter} />
        </section>

        {/* ---------------- ElevenLabs ---------------- */}
        <section className="settings-section">
          <div className="settings-section__head">
            <h2 className="settings-section__title">ElevenLabs</h2>
            <button
              type="button"
              className="btn btn--sm"
              onClick={() => void runTest('elevenlabs')}
            >
              Test connection
            </button>
          </div>

          <div className="settings-grid">
            <div className="field">
              <label htmlFor="eleven-key">
                API key{' '}
                <span className="hint">
                  {settings?.elevenlabs_api_key.configured
                    ? `— configured (${settings.elevenlabs_api_key.masked})`
                    : '— not configured'}
                </span>
              </label>
              <input
                id="eleven-key"
                className="input"
                type="password"
                autoComplete="off"
                placeholder={
                  settings?.elevenlabs_api_key.configured
                    ? 'Leave blank to keep the current key'
                    : 'sk_…'
                }
                value={elevenKey}
                onChange={(event) => setElevenKey(event.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="agent-id">Conversational Agent ID (required)</label>
              <input
                id="agent-id"
                className="input"
                placeholder="agent_…"
                value={agentId}
                onChange={(event) => setAgentId(event.target.value)}
              />
              <span className="hint">
                Without an Agent ID, live voice conversations cannot start.
              </span>
            </div>

            <div className="field">
              <label htmlFor="voice-id">TTS voice ID (progress announcements)</label>
              <input
                id="voice-id"
                className="input"
                placeholder="voice ID for short progress speech"
                value={voiceId}
                onChange={(event) => setVoiceId(event.target.value)}
              />
            </div>

            {settings?.elevenlabs_api_key.configured && (
              <button
                type="button"
                className="btn btn--danger btn--sm"
                onClick={() => void removeSecret('elevenlabs_api_key')}
              >
                Remove stored key
              </button>
            )}
          </div>

          <TestResult result={tests.elevenlabs} />
        </section>

        {/* ---------------- Coding agent ---------------- */}
        <section className="settings-section">
          <div className="settings-section__head">
            <h2 className="settings-section__title">Coding agent (Pi)</h2>
            <button type="button" className="btn btn--sm" onClick={() => void runTest('pi')}>
              Test runtime
            </button>
          </div>

          <div className="settings-grid">
            <div className="detail-grid">
              <dt>Pi version</dt>
              <dd>{settings?.pi_version ?? 'not detected'}</dd>
              <dt>RPC session</dt>
              <dd>
                {settings?.pi_rpc_available
                  ? 'available'
                  : 'managed RPC sessions arrive in Phase 2'}
              </dd>
              <dt>Active backend</dt>
              <dd>simulated agent (Phase 1) — no files are modified</dd>
            </div>

            <div className="field">
              <label htmlFor="pi-provider">Provider</label>
              <input
                id="pi-provider"
                className="input"
                placeholder="e.g. openrouter, anthropic, openai"
                value={piProvider}
                onChange={(event) => setPiProvider(event.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="pi-model">Model ID</label>
              <input
                id="pi-model"
                className="input"
                placeholder="provider model identifier"
                value={piModel}
                onChange={(event) => setPiModel(event.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="pi-base-url">Base URL (optional)</label>
              <input
                id="pi-base-url"
                className="input"
                placeholder="only if the provider requires it"
                value={piBaseUrl}
                onChange={(event) => setPiBaseUrl(event.target.value)}
              />
            </div>

            <label className="checkbox">
              <input
                type="checkbox"
                checked={reuseOpenRouterKey}
                onChange={(event) => setReuseOpenRouterKey(event.target.checked)}
              />
              Reuse the OpenRouter API key for Pi (avoid entering it twice)
            </label>

            <span className="hint">
              Provider and model changes apply to new agent sessions.
            </span>
          </div>

          <TestResult result={tests.pi} />
        </section>

        {/* ---------------- Preferences ---------------- */}
        <section className="settings-section">
          <h2 className="settings-section__title">Preferences</h2>
          <div className="settings-grid">
            <label className="checkbox">
              <input
                type="checkbox"
                checked={voiceEnabled}
                onChange={(event) => setVoiceEnabled(event.target.checked)}
              />
              Enable live voice conversation (Phase 4)
            </label>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={speechEnabled}
                onChange={(event) => setSpeechEnabled(event.target.checked)}
              />
              Speak short progress announcements (Phase 5)
            </label>
            <span className="hint">
              Progress is always shown visually, so voice can be disabled without
              losing information.
            </span>
          </div>
        </section>

        <div className="header__group" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn--primary" type="submit" disabled={busy}>
            {busy ? 'Saving…' : 'Save settings'}
          </button>
        </div>
      </form>
    </div>
  )
}

function TestResult({ result }: { result?: ConnectionTestResult }) {
  if (!result) return null
  return (
    <div
      className={`test-result alert ${result.ok ? 'alert--info' : 'alert--error'}`}
      role="status"
    >
      {result.ok ? '✓' : '✕'} {result.message}
      {result.detail && (
        <div className="hint" style={{ marginTop: 4 }}>
          {result.detail}
        </div>
      )}
    </div>
  )
}
