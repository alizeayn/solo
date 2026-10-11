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
 *   **Voice** — ElevenLabs: speech in and speech out.
 *   **Preferences** — feature toggles.
 *
 * Every secret is write-only: the UI sends values and only ever reads back a
 * masked status. No screen reports a connection as working unless the
 * corresponding check actually succeeded.
 */

import { useEffect, useState } from 'react'

import { api } from '../api/client'
import { useWorkspace } from '../state/WorkspaceProvider'
import type {
  ConnectionTestResult,
  SettingsPatch,
  Voice,
  VoiceModel,
} from '../types'
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
/* Voice — ElevenLabs speech in and speech out                         */
/* ------------------------------------------------------------------ */

/**
 * Voice configuration.
 *
 * Three things this deliberately does **not** do:
 *
 * * It does not ask for a Conversational Agent ID. Solo does not use the
 *   ElevenLabs Agents Platform — that would put an ElevenLabs agent in front of
 *   the Orchestrator and let it answer from its own context instead of from real
 *   task state.
 * * It does not ask for a voice ID to be pasted. Voices are listed from the
 *   account and chosen, the same way OpenRouter models and Pi providers are.
 * * It does not hardcode a model catalog. Models come from `GET /v1/models`,
 *   which reflects what *this account* can use — a static list would offer ids
 *   that do not exist and hide ones that do.
 *
 * The selection is saved through the API the runtime reads, so choosing a model
 * here changes what Solo actually speaks with, not merely what is displayed.
 */
function VoiceSettings() {
  const { settings, refreshSettings } = useWorkspace()
  const [apiKey, setApiKey] = useState('')
  const [result, setResult] = useState<ConnectionTestResult | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [models, setModels] = useState<VoiceModel[] | null>(null)
  const [voices, setVoices] = useState<Voice[] | null>(null)
  const [modelId, setModelId] = useState('')
  const [sttModelId, setSttModelId] = useState('')
  const [voiceId, setVoiceId] = useState('')

  // Follow the saved settings, so a change made elsewhere is reflected here.
  useEffect(() => {
    setModelId(settings?.elevenlabs_model_id ?? '')
    setSttModelId(settings?.elevenlabs_stt_model_id ?? '')
    setVoiceId(settings?.elevenlabs_tts_voice_id ?? '')
  }, [
    settings?.elevenlabs_model_id,
    settings?.elevenlabs_stt_model_id,
    settings?.elevenlabs_tts_voice_id,
  ])

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

  const saveKey = () =>
    guarded('key', async () => {
      if (!apiKey.trim()) throw new Error('Enter an API key first.')
      await api.settings.update({ elevenlabs_api_key: apiKey.trim() })
      setApiKey('')
      await refreshSettings()
      setNotice('Key saved. Retrieve the models to choose one.')
    })

  const test = () =>
    guarded('test', async () => {
      setResult(await api.settings.test('elevenlabs'))
    })

  const discover = () =>
    guarded('discover', async () => {
      // One round trip each: a failure in either is reported as itself rather
      // than as "discovery failed".
      const [fetchedModels, fetchedVoices] = await Promise.all([
        api.voice.models(),
        api.voice.voices(),
      ])
      setModels(fetchedModels)
      setVoices(fetchedVoices)
      const speech = fetchedModels.filter((model) => model.can_tts).length
      setNotice(
        `Found ${speech} speech model${speech === 1 ? '' : 's'} and ` +
          `${fetchedVoices.length} voice${fetchedVoices.length === 1 ? '' : 's'}.`,
      )
    })

  const saveSelection = () =>
    guarded('save', async () => {
      await api.voice.settings({
        model_id: modelId,
        stt_model_id: sttModelId,
        voice_id: voiceId,
      })
      await refreshSettings()
      setNotice('Voice selection saved. The next thing Solo says will use it.')
    })

  const speechModels = (models ?? []).filter((model) => model.can_tts)
  const listenModels = (models ?? []).filter((model) => !model.can_tts)
  const configured = settings?.elevenlabs_api_key.configured ?? false
  const selectedModel = (models ?? []).find((model) => model.id === modelId)
  const selectedVoice = (voices ?? []).find((voice) => voice.id === voiceId)

  return (
    <div className="settings-pane">
      <div className={`alert ${configured ? 'alert--info' : 'alert--warn'}`}>
        {configured
          ? 'Speech in and speech out are active. Solo speaks milestones through the ' +
            'narration pipeline, and speech input is transcribed into the same task ' +
            'path as typing.'
          : 'Add an ElevenLabs API key to activate speech. Solo uses only text to ' +
            'speech and speech to text — the Agents Platform is deliberately not used, ' +
            'so the Orchestrator stays in charge of what is worth saying.'}
      </div>

      <section className="settings-section">
        <div className="settings-section__head">
          <h3 className="settings-section__title">ElevenLabs</h3>
          <div className="form-actions">
            <button
              type="button"
              className="btn btn--sm"
              disabled={busy !== null || !configured}
              title={configured ? undefined : 'Save a key first'}
              onClick={() => void discover()}
            >
              {busy === 'discover' ? 'Retrieving…' : 'Retrieve models and voices'}
            </button>
            <button
              type="button"
              className="btn btn--sm"
              disabled={busy !== null}
              onClick={() => void test()}
            >
              {busy === 'test' ? 'Testing…' : 'Test connection'}
            </button>
          </div>
        </div>

        <div className="settings-grid">
          <div className="field">
            <label htmlFor="el-key">
              API key{' '}
              <span className="hint">
                {configured
                  ? `— saved (${settings?.elevenlabs_api_key.masked})`
                  : '— not saved'}
              </span>
            </label>
            <div className="form-row">
              <input
                id="el-key"
                className="input"
                type="password"
                autoComplete="off"
                placeholder={configured ? 'Replace the saved key' : 'sk_…'}
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
              />
              <button
                type="button"
                className="btn btn--primary btn--sm"
                disabled={busy !== null || !apiKey.trim()}
                onClick={() => void saveKey()}
              >
                {busy === 'key' ? 'Saving…' : 'Save key'}
              </button>
            </div>
            <span className="hint">
              Sent to ElevenLabs as the <code>xi-api-key</code> header. Stored
              encrypted and never returned by the API.
            </span>
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

      {configured && (
        <section className="settings-section">
          <div className="settings-section__head">
            <h3 className="settings-section__title">Speech output</h3>
            <span className="hint">
              {speechModels.length
                ? `${speechModels.length} available`
                : 'not retrieved yet'}
            </span>
          </div>

          <div className="settings-grid">
            <div className="field">
              <label htmlFor="el-model">Voice model</label>
              <select
                id="el-model"
                className="input"
                value={modelId}
                onChange={(event) => setModelId(event.target.value)}
                disabled={speechModels.length === 0}
              >
                {speechModels.length === 0 && (
                  <option value={modelId}>{modelId || 'Retrieve models first'}</option>
                )}
                {speechModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name} — {model.id}
                  </option>
                ))}
              </select>
              {selectedModel && (
                <span className="hint">
                  {selectedModel.max_text_length
                    ? `up to ${selectedModel.max_text_length.toLocaleString()} characters per request`
                    : 'character limit not reported'}
                  {selectedModel.cost_multiplier !== null &&
                    ` · ${selectedModel.cost_multiplier}× character cost`}
                  {selectedModel.requires_alpha && ' · requires alpha access'}
                </span>
              )}
            </div>

            <div className="field">
              <label htmlFor="el-voice">Voice</label>
              <select
                id="el-voice"
                className="input"
                value={voiceId}
                onChange={(event) => setVoiceId(event.target.value)}
                disabled={(voices ?? []).length === 0}
              >
                <option value="">
                  {settings?.elevenlabs_voice_name
                    ? `Current: ${settings.elevenlabs_voice_name}`
                    : 'First voice on the account'}
                </option>
                {(voices ?? []).map((voice) => (
                  <option key={voice.id} value={voice.id}>
                    {voice.name}
                    {voice.category ? ` — ${voice.category}` : ''}
                  </option>
                ))}
              </select>
              {selectedVoice?.preview_url && (
                <audio controls preload="none" src={selectedVoice.preview_url} />
              )}
              <span className="hint">
                Listing voices means choosing one, rather than pasting an identifier
                that may not exist for this account.
              </span>
            </div>
          </div>
        </section>
      )}

      {configured && (
        <section className="settings-section">
          <div className="settings-section__head">
            <h3 className="settings-section__title">Speech input</h3>
          </div>
          <div className="settings-grid">
            <div className="field">
              <label htmlFor="el-stt">Recognition model</label>
              <select
                id="el-stt"
                className="input"
                value={sttModelId}
                onChange={(event) => setSttModelId(event.target.value)}
                disabled={listenModels.length === 0}
              >
                {listenModels.length === 0 && (
                  <option value={sttModelId}>
                    {sttModelId || 'Retrieve models first'}
                  </option>
                )}
                {listenModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name} — {model.id}
                  </option>
                ))}
              </select>
              <span className="hint">
                Speech is recorded in the browser and transcribed by the backend,
                then posted to the same endpoint a typed message uses — so intent
                classification, task creation and Pi Agent execution are unchanged.
              </span>
            </div>
          </div>
        </section>
      )}

      {configured && (
        <div className="form-actions">
          <button
            type="button"
            className="btn btn--primary btn--sm"
            disabled={busy !== null}
            onClick={() => void saveSelection()}
          >
            {busy === 'save' ? 'Saving…' : 'Save voice selection'}
          </button>
        </div>
      )}

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
