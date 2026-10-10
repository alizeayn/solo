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
      runtime: vi.fn(),
      installRuntime: vi.fn(),
      verifyRuntime: vi.fn(),
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
    installed: true,
    verified: true,
    source: 'managed',
    isolated: true,
    version: '1.1.0',
    executable: '/solo/data/pi-runtime/node_modules/.bin/pi',
    agent_dir: '/solo/data/pi/agent',
    node: '/usr/bin/node',
    runtime_dir: '/solo/data/pi-runtime',
    installed_at: '2026-10-10T12:00:00Z',
    last_error: null,
    detail: "Solo's isolated Pi Agent is installed",
  },
  backend: 'pi',
  provider: null,
  model: null,
  thinking_level: null,
  approve_project: false,
  minimal_harness: true,
  agent_dir: '/solo/data/pi/agent',
  auth_file: '/solo/data/pi/agent/auth.json',
  runtime_dir: '/solo/data/pi-runtime',
  node: '/usr/bin/node',
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

  it('shows the detected runtime and states that it is isolated', async () => {
    render(<PiAgentSettings />)
    expect(
      await screen.findByText(/installed and verified/i),
    ).toBeInTheDocument()
    expect(screen.getByText('Pi Agent')).toBeInTheDocument()
    // The provenance line is the point of the card: Solo's own copy.
    expect(screen.getByText(/Solo’s own copy, independent/i)).toBeInTheDocument()
    expect(screen.getByText('/solo/data/pi/agent')).toBeInTheDocument()
  })

  it('offers to install the runtime when it is missing', async () => {
    vi.mocked(pi.status).mockResolvedValue({
      ...STATUS,
      backend: 'mock',
      runtime: {
        ...STATUS.runtime,
        available: false,
        installed: false,
        verified: false,
        source: 'none',
        isolated: false,
        version: null,
        executable: null,
        detail: "Solo's isolated Pi Agent is not installed yet.",
      },
    } as never)
    vi.mocked(pi.installRuntime).mockResolvedValue({
      ok: true,
      message: 'Pi Agent 1.1.0 installed into Solo\'s runtime.',
      detail: null,
      version: '1.1.0',
      duration_ms: 1200,
      output: null,
      runtime: STATUS.runtime,
    } as never)

    render(<PiAgentSettings />)
    const button = await screen.findByRole('button', { name: /install pi agent/i })
    await userEvent.click(button)
    await waitFor(() => expect(pi.installRuntime).toHaveBeenCalledWith(true))
  })

  it('states plainly when the runtime is not installed', async () => {
    vi.mocked(pi.status).mockResolvedValue({
      ...STATUS,
      backend: 'mock',
      runtime: {
        ...STATUS.runtime,
        available: false,
        installed: false,
        verified: false,
        source: 'none',
        isolated: false,
        version: null,
        detail: "Solo's isolated Pi Agent is not installed yet.",
      },
    } as never)
    render(<PiAgentSettings />)
    expect(await screen.findByText(/Solo's Pi Agent is not installed/)).toBeInTheDocument()
    expect(screen.getByText('Simulator')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: /install pi agent/i }),
    ).toBeInTheDocument()
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
