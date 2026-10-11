/**
 * Workspace Settings.
 *
 * Organised around the two models Solo actually uses, so each has one obvious
 * home:
 *
 *   **Orchestrator** — OpenRouter: intent detection, prioritisation, state
 *   management, summaries.
 *   **Pi Agent** — provider, credentials, model discovery and the coding agent
 *   that executes tasks in the open project.
 *   **Voice** — ElevenLabs (Phase 4).
 *   **Preferences** — feature toggles.
 *
 * Every secret is write-only: the UI sends values and only ever reads back a
 * masked status. No screen reports a connection as working unless the
 * corresponding check actually succeeded.
 */

import { useState } from 'react'

import { api } from '../api/client'
import { useWorkspace } from '../state/WorkspaceProvider'
import type { ConnectionTestResult, SettingsPatch } from '../types'
import AccountSettings from './AccountSettings'
import OrchestratorSettings from './OrchestratorSettings'
import PiAgentSettings from './PiAgentSettings'
import ThemeToggle from './ThemeToggle'

type Tab = 'account' | 'orchestrator' | 'pi' | 'voice' | 'preferences'

const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: 'orchestrator', label: 'Orchestrator', hint: 'OpenRouter · intent, planning, summaries' },
  { id: 'pi', label: 'Pi Agent', hint: 'Provider, credentials, model' },
  { id: 'voice', label: 'Voice', hint: 'Voice-native conversation' },
  { id: 'preferences', label: 'Appearance & behaviour', hint: 'Theme, checks, speech' },
  { id: 'account', label: 'Account', hint: 'Username, password, sessions' },
]

export default function SettingsView({ onClose }: { onClose: () => void }) {
  const [tab, setTab] = useState<Tab>('orchestrator')

  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label="Settings">
      <div className="card card--wide settings-shell">
        <header className="settings-shell__head">
          <div>
            <h1 className="card__title">Settings</h1>
            <p className="card__subtitle" style={{ marginBottom: 0 }}>
              Credentials are stored server-side, encrypted at rest, and never sent back to the
              browser.
            </p>
          </div>
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            Close
          </button>
        </header>

        <nav className="settings-shell__tabs" role="tablist" aria-label="Settings sections">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              className={`settings-tab ${tab === item.id ? 'settings-tab--active' : ''}`}
              onClick={() => setTab(item.id)}
            >
              <span className="settings-tab__label">{item.label}</span>
              <span className="settings-tab__hint">{item.hint}</span>
            </button>
          ))}
        </nav>

        <div className="settings-shell__body">
          {tab === 'orchestrator' && <OrchestratorSettings />}
          {tab === 'pi' && <PiAgentSettings />}
          {tab === 'voice' && <VoiceSettings />}
          {tab === 'preferences' && <PreferencesSettings />}
          {tab === 'account' && <AccountSettings />}
        </div>

        <footer className="settings-shell__foot">
          <button type="button" className="btn" onClick={onClose}>
            Done
          </button>
        </footer>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Voice (Phase 4 placeholders, stored now so configuration is ready)  */
/* ------------------------------------------------------------------ */
function VoiceSettings() {
  const { settings, refreshSettings } = useWorkspace()
  const [apiKey, setApiKey] = useState('')
  const [agentId, setAgentId] = useState(settings?.elevenlabs_agent_id ?? '')
  const [voiceId, setVoiceId] = useState(settings?.elevenlabs_tts_voice_id ?? '')
  const [result, setResult] = useState<ConnectionTestResult | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function guarded(key: string, action: () => Promise<void>) {
    setBusy(key)
    setError(null)
    setNotice(null)
    try {
      await action()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(null)
    }
  }

  const save = () =>
    guarded('save', async () => {
      const patch: SettingsPatch = {
        elevenlabs_agent_id: agentId,
        elevenlabs_tts_voice_id: voiceId,
      }
      if (apiKey.trim()) patch.elevenlabs_api_key = apiKey.trim()
      await api.settings.update(patch)
      setApiKey('')
      await refreshSettings()
      setNotice('Voice settings saved.')
    })

  return (
    <div className="settings-pane">
      <div className="alert alert--info">
        Live voice conversations and spoken progress arrive in Phases 4 and 5. Credentials can be
        configured and tested now so the integration has somewhere to read from.
      </div>

      <section className="settings-section">
        <div className="settings-section__head">
          <h3 className="settings-section__title">ElevenLabs</h3>
          <button
            type="button"
            className="btn btn--sm"
            disabled={busy === 'test'}
            onClick={() =>
              void guarded('test', async () => {
                setResult(await api.settings.test('elevenlabs'))
              })
            }
          >
            Test connection
          </button>
        </div>

        <div className="settings-grid">
          <div className="field">
            <label htmlFor="el-key">
              API key{' '}
              <span className="hint">
                {settings?.elevenlabs_api_key.configured
                  ? `— saved (${settings.elevenlabs_api_key.masked})`
                  : '— not saved'}
              </span>
            </label>
            <input
              id="el-key"
              className="input"
              type="password"
              autoComplete="off"
              placeholder={settings?.elevenlabs_api_key.configured ? 'Replace the saved key' : 'sk_…'}
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="el-agent">Conversational Agent ID (required for voice)</label>
            <input
              id="el-agent"
              className="input"
              placeholder="agent_…"
              value={agentId}
              onChange={(event) => setAgentId(event.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="el-voice">TTS voice ID (progress announcements)</label>
            <input
              id="el-voice"
              className="input"
              placeholder="voice ID"
              value={voiceId}
              onChange={(event) => setVoiceId(event.target.value)}
            />
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn btn--primary btn--sm"
              disabled={busy === 'save'}
              onClick={() => void save()}
            >
              {busy === 'save' ? 'Saving…' : 'Save'}
            </button>
          </div>

          {result && (
            <div
              className={`test-result alert ${result.ok ? 'alert--info' : 'alert--error'}`}
              role="status"
            >
              {result.message}
              {result.detail && <div className="hint">{result.detail}</div>}
            </div>
          )}
        </div>
      </section>

      {error && <div className="alert alert--error">{error}</div>}
      {notice && !error && <div className="alert alert--info">{notice}</div>}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Preferences                                                         */
/* ------------------------------------------------------------------ */
function PreferencesSettings() {
  const { settings, refreshSettings } = useWorkspace()
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [checksStatus, setChecksStatus] = useState<{
    available: boolean
    detail: string | null
  } | null>(null)

  async function toggle(key: keyof SettingsPatch, value: boolean) {
    setBusy(String(key))
    setError(null)
    try {
      await api.settings.update({ [key]: value } as SettingsPatch)
      await refreshSettings()
      setNotice('Preference saved.')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(null)
    }
  }

  async function loadChecks() {
    try {
      setChecksStatus(await api.checks.status())
    } catch {
      setChecksStatus(null)
    }
  }

  return (
    <div className="settings-pane">
      <section className="settings-section">
        <h3 className="settings-section__title">Appearance</h3>
        <div className="settings-grid">
          <div className="field">
            <label>Theme</label>
            <ThemeToggle />
            <span className="hint">
              Solo ships a dark and a light theme. "Auto" follows your operating
              system, and the choice is saved to your account so it follows you to
              another browser.
            </span>
          </div>
        </div>
      </section>

      <section className="settings-section">
        <h3 className="settings-section__title">Behaviour</h3>
        <div className="settings-grid">
          <label className="checkbox">
            <input
              type="checkbox"
              checked={settings?.voice_enabled ?? true}
              disabled={busy === 'voice_enabled'}
              onChange={(event) => void toggle('voice_enabled', event.target.checked)}
            />
            Enable the voice channel (narration is recorded and shown; audio
            arrives in Phase 4)
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={settings?.progress_speech_enabled ?? true}
              disabled={busy === 'progress_speech_enabled'}
              onChange={(event) => void toggle('progress_speech_enabled', event.target.checked)}
            />
            Allow spoken progress announcements once audio is available
          </label>
          <span className="hint">
            Progress is always shown visually, so voice can be disabled without losing
            information.
          </span>
        </div>
      </section>

      <section className="settings-section">
        <div className="settings-section__head">
          <h3 className="settings-section__title">Static checks (Pyright)</h3>
          <button type="button" className="btn btn--sm" onClick={() => void loadChecks()}>
            Check availability
          </button>
        </div>
        <div className="settings-grid">
          <label className="checkbox">
            <input
              type="checkbox"
              checked={settings?.checks_enabled ?? true}
              disabled={busy === 'checks_enabled'}
              onChange={(event) => void toggle('checks_enabled', event.target.checked)}
            />
            Run Pyright over the files a coding task changed
          </label>
          <span className="hint">
            Solo uses Pi to make changes and Pyright to verify them. Checks never block a task;
            results appear in the Coding Agent Activity panel.
          </span>
          {checksStatus && (
            <div className={`alert ${checksStatus.available ? 'alert--info' : 'alert--error'}`}>
              {checksStatus.detail}
            </div>
          )}
        </div>
      </section>

      {error && <div className="alert alert--error">{error}</div>}
      {notice && !error && <div className="alert alert--info">{notice}</div>}
    </div>
  )
}
