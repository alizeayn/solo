import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  refreshSettings: vi.fn(),
  reportError: vi.fn(),
  settings: { openrouter_api_key: { configured: false, masked: null } },
}))

vi.mock('../state/WorkspaceProvider', () => ({
  useWorkspace: () => ({
    settings: mocks.settings,
    refreshSettings: mocks.refreshSettings,
    reportError: mocks.reportError,
  }),
}))

vi.mock('../api/client', () => ({
  api: {
    pi: {
      status: vi.fn(),
      providers: vi.fn(),
      models: vi.fn(),
      refreshModels: vi.fn(),
      auth: vi.fn(),
      saveCredential: vi.fn(),
      deleteCredential: vi.fn(),
      credentialFromOrchestrator: vi.fn(),
      test: vi.fn(),
    },
    settings: { update: vi.fn() },
  },
}))

import { api } from '../api/client'
import PiAgentSettings from './PiAgentSettings'

const pi = api.pi

const STATUS = {
  runtime: {
    available: true,
    version: '1.1.0',
    executable: '/usr/bin/pi',
    agent_dir: '/home/u/.pi/agent',
    detail: 'Pi CLI 1.1.0 detected',
  },
  backend: 'pi',
  provider: null,
  model: null,
  thinking_level: null,
  approve_project: false,
  minimal_harness: true,
  agent_dir: '/home/u/.pi/agent',
  auth_file: '/home/u/.pi/agent/auth.json',
  configured_providers: [],
  sessions: [],
}

const PROVIDERS = [
  {
    id: 'openrouter',
    label: 'OpenRouter',
    env_var: 'OPENROUTER_API_KEY',
    configured: false,
    auth_type: null,
    source: 'none',
    model_count: 405,
    model_count_known: true,
    in_catalog: true,
  },
  {
    id: 'anthropic',
    label: 'Anthropic',
    env_var: 'ANTHROPIC_API_KEY',
    configured: false,
    auth_type: null,
    source: 'none',
    model_count: 0,
    model_count_known: true,
    in_catalog: false,
  },
]

const MODELS = [
  {
    id: 'vendor/alpha',
    name: 'Alpha',
    provider: 'openrouter',
    reasoning: true,
    context_window: 200000,
    max_tokens: 8192,
    input_modalities: ['text'],
    cost: null,
  },
  {
    id: 'vendor/beta',
    name: 'Beta',
    provider: 'openrouter',
    reasoning: false,
    context_window: 32000,
    max_tokens: 4096,
    input_modalities: ['text'],
    cost: null,
  },
]

describe('PiAgentSettings', () => {
  beforeEach(() => {
    vi.mocked(pi.status).mockReset().mockResolvedValue(STATUS as never)
    vi.mocked(pi.providers).mockReset().mockResolvedValue(PROVIDERS as never)
    vi.mocked(pi.models).mockReset().mockResolvedValue(MODELS as never)
    vi.mocked(pi.refreshModels)
      .mockReset()
      .mockResolvedValue({ ok: true, message: 'Model catalog refreshed.', output: null } as never)
    vi.mocked(pi.auth)
      .mockReset()
      .mockResolvedValue({
        provider: 'openrouter',
        status: 'not_ready',
        ready: false,
        auth_type: null,
        reason: 'credentials_not_configured',
        detail: null,
      } as never)
    vi.mocked(api.settings.update).mockReset().mockResolvedValue({} as never)
    mocks.refreshSettings.mockReset().mockResolvedValue(undefined)
  })

  it('shows the detected Pi runtime', async () => {
    render(<PiAgentSettings />)
    expect(await screen.findByText('1.1.0')).toBeInTheDocument()
    expect(screen.getByText('Pi Agent')).toBeInTheDocument()
    expect(screen.getByText('/home/u/.pi/agent')).toBeInTheDocument()
  })

  it('warns when Pi is not installed', async () => {
    vi.mocked(pi.status).mockResolvedValue({
      ...STATUS,
      backend: 'mock',
      runtime: { ...STATUS.runtime, available: false, version: null, detail: 'not found on PATH' },
    } as never)
    render(<PiAgentSettings />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/not found on PATH/)
    expect(screen.getByText('Simulator')).toBeInTheDocument()
  })

  it('lists providers and marks unconfigured state', async () => {
    render(<PiAgentSettings />)
    await userEvent.selectOptions(await screen.findByLabelText('Provider'), 'anthropic')
    expect(await screen.findByText(/No credential configured/i)).toBeInTheDocument()
    expect(screen.getByLabelText('configuration state')).toHaveTextContent('not configured')
  })

  it('saves a credential and reports that Pi accepted it', async () => {
    vi.mocked(pi.saveCredential).mockResolvedValue({
      provider: 'anthropic',
      status: 'ready',
      ready: true,
      auth_type: 'api_key',
      reason: null,
      detail: null,
    } as never)

    render(<PiAgentSettings />)
    await userEvent.selectOptions(await screen.findByLabelText('Provider'), 'anthropic')
    await userEvent.type(screen.getByLabelText(/API key/i), 'sk-ant-secret')
    await userEvent.click(screen.getByRole('button', { name: /save credential/i }))

    await waitFor(() =>
      expect(pi.saveCredential).toHaveBeenCalledWith('anthropic', 'sk-ant-secret'),
    )
    expect(await screen.findByText(/Credential saved for anthropic/i)).toBeInTheDocument()
  })

  it('offers the reuse option only for OpenRouter', async () => {
    render(<PiAgentSettings />)
    await userEvent.selectOptions(await screen.findByLabelText('Provider'), 'anthropic')
    expect(screen.queryByRole('button', { name: /orchestrator key/i })).not.toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Provider'), 'openrouter')
    expect(
      await screen.findByRole('button', { name: /orchestrator key/i }),
    ).toBeInTheDocument()
  })

  it('never labels a provider verified after only a presence check', async () => {
    vi.mocked(pi.test).mockResolvedValue({
      ok: true,
      state: 'configured',
      message: 'anthropic has a usable credential. Run a real request to confirm.',
      detail: null,
      provider: 'anthropic',
      model: null,
      latency_ms: 12,
    } as never)

    render(<PiAgentSettings />)
    await userEvent.selectOptions(await screen.findByLabelText('Provider'), 'anthropic')
    await userEvent.click(screen.getByRole('button', { name: /check configuration/i }))

    expect(await screen.findByText(/usable credential/i)).toBeInTheDocument()
    expect(screen.getByLabelText('configuration state')).toHaveTextContent('configured')
    expect(screen.getByLabelText('configuration state')).not.toHaveTextContent('verified')
  })

  it('shows verified only after a real request succeeds', async () => {
    vi.mocked(pi.test).mockResolvedValue({
      ok: true,
      state: 'verified',
      message: 'anthropic / claude answered a real request successfully.',
      detail: null,
      provider: 'anthropic',
      model: 'claude',
      latency_ms: 900,
    } as never)

    render(<PiAgentSettings />)
    await userEvent.selectOptions(await screen.findByLabelText('Provider'), 'anthropic')
    await userEvent.type(screen.getByLabelText('Model ID'), 'claude')
    await userEvent.click(screen.getByRole('button', { name: /verify with a real request/i }))

    expect(await screen.findByLabelText('configuration state')).toHaveTextContent('verified')
    expect(screen.getByText(/answered a real request/i)).toBeInTheDocument()
  })

  it('surfaces a failed verification honestly', async () => {
    vi.mocked(pi.test).mockResolvedValue({
      ok: false,
      state: 'failed',
      message: 'Insufficient credits',
      detail: 'code 402',
      provider: 'openrouter',
      model: 'vendor/alpha',
      latency_ms: 500,
    } as never)

    render(<PiAgentSettings />)
    await userEvent.selectOptions(await screen.findByLabelText('Provider'), 'openrouter')
    await userEvent.type(screen.getByLabelText('Model ID'), 'vendor/alpha')
    await userEvent.click(screen.getByRole('button', { name: /verify with a real request/i }))

    expect(await screen.findByLabelText('configuration state')).toHaveTextContent('failed')
    expect(screen.getByText(/Insufficient credits/)).toBeInTheDocument()
  })

  it('discovers models and saves the selection', async () => {
    render(<PiAgentSettings />)
    await userEvent.selectOptions(await screen.findByLabelText('Provider'), 'openrouter')
    await userEvent.click(screen.getByRole('button', { name: /discover models/i }))

    expect(await screen.findByText('vendor/alpha')).toBeInTheDocument()
    await userEvent.click(screen.getByText('vendor/alpha'))
    await userEvent.click(screen.getByRole('button', { name: /save selection/i }))

    await waitFor(() =>
      expect(api.settings.update).toHaveBeenCalledWith(
        expect.objectContaining({ pi_provider: 'openrouter', pi_model: 'vendor/alpha' }),
      ),
    )
  })

  it('allows a manual model id when discovery finds nothing', async () => {
    vi.mocked(pi.models).mockResolvedValue([] as never)
    render(<PiAgentSettings />)
    await userEvent.selectOptions(await screen.findByLabelText('Provider'), 'anthropic')
    await userEvent.click(screen.getByRole('button', { name: /discover models/i }))

    expect(await screen.findByText(/Enter a model ID manually/i)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Model ID'), 'claude-opus')
    await userEvent.click(screen.getByRole('button', { name: /save selection/i }))
    await waitFor(() =>
      expect(api.settings.update).toHaveBeenCalledWith(
        expect.objectContaining({ pi_model: 'claude-opus' }),
      ),
    )
  })

  it('refreshes the catalog through Pi', async () => {
    render(<PiAgentSettings />)
    await userEvent.selectOptions(await screen.findByLabelText('Provider'), 'openrouter')
    await userEvent.click(screen.getByRole('button', { name: /refresh catalog/i }))
    await waitFor(() => expect(pi.refreshModels).toHaveBeenCalled())
  })

  it('shows project trust as opt-in', async () => {
    render(<PiAgentSettings />)
    const trust = await screen.findByRole('checkbox', {
      name: /trust project-local pi resources/i,
    })
    expect(trust).not.toBeChecked()
    expect(screen.getByText(/Off by default/i)).toBeInTheDocument()
  })
})
