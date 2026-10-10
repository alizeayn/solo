import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  refreshSettings: vi.fn(),
  reportError: vi.fn(),
  settings: { openrouter_api_key: { configured: false, masked: null as string | null } },
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
    orchestrator: {
      status: vi.fn(),
      config: vi.fn(),
      models: vi.fn(),
      test: vi.fn(),
    },
    settings: { update: vi.fn(), removeSecret: vi.fn() },
  },
}))

import { api } from '../api/client'
import OrchestratorSettings from './OrchestratorSettings'

const orchestrator = api.orchestrator

const STATUS = {
  enabled: true,
  configured: false,
  has_key: false,
  model: null,
  key_masked: null,
  call_count: 0,
  failure_count: 0,
  last_error: null,
  last_latency_ms: null,
  last_model: null,
}

describe('OrchestratorSettings', () => {
  beforeEach(() => {
    mocks.settings = { openrouter_api_key: { configured: false, masked: null } }
    vi.mocked(orchestrator.status).mockReset().mockResolvedValue(STATUS as never)
    vi.mocked(orchestrator.config).mockReset().mockResolvedValue(STATUS as never)
    vi.mocked(orchestrator.models).mockReset().mockResolvedValue([] as never)
    vi.mocked(api.settings.update).mockReset().mockResolvedValue({} as never)
    vi.mocked(api.settings.removeSecret).mockReset().mockResolvedValue({} as never)
    mocks.refreshSettings.mockReset().mockResolvedValue(undefined)
  })

  it('starts unconfigured and explains what the model is for', async () => {
    render(<OrchestratorSettings />)
    expect(await screen.findByLabelText('configuration state')).toHaveTextContent('not configured')
    expect(screen.getByText(/intent detection, task prioritisation/i)).toBeInTheDocument()
  })

  it('saves an API key and never echoes it back', async () => {
    render(<OrchestratorSettings />)
    await userEvent.type(await screen.findByLabelText(/API key/i), 'sk-or-v1-secret')
    await userEvent.click(screen.getByRole('button', { name: /save key/i }))

    await waitFor(() =>
      expect(api.settings.update).toHaveBeenCalledWith({
        openrouter_api_key: 'sk-or-v1-secret',
      }),
    )
    expect(document.body.textContent).not.toContain('sk-or-v1-secret')
  })

  it('shows the masked key when one is saved', async () => {
    mocks.settings = { openrouter_api_key: { configured: true, masked: '**********cdef' } }
    vi.mocked(orchestrator.status).mockResolvedValue({
      ...STATUS,
      has_key: true,
      key_masked: '**********cdef',
    } as never)

    render(<OrchestratorSettings />)
    expect(await screen.findByText(/saved \(\*+cdef\)/)).toBeInTheDocument()
  })

  it('reports a key that is valid but not model-verified as configured', async () => {
    mocks.settings = { openrouter_api_key: { configured: true, masked: '***' } }
    vi.mocked(orchestrator.status).mockResolvedValue({ ...STATUS, has_key: true } as never)
    vi.mocked(orchestrator.test).mockResolvedValue({
      ok: true,
      state: 'configured',
      message: 'The OpenRouter key is valid.',
      detail: 'label=personal',
      model: null,
      latency_ms: 90,
    } as never)

    render(<OrchestratorSettings />)
    await userEvent.click(await screen.findByRole('button', { name: /test key/i }))

    expect(await screen.findByText(/key is valid/i)).toBeInTheDocument()
    expect(screen.getByLabelText('configuration state')).toHaveTextContent('configured')
    expect(screen.queryByText('verified')).not.toBeInTheDocument()
  })

  it('reports a verified model after a real completion', async () => {
    mocks.settings = { openrouter_api_key: { configured: true, masked: '***' } }
    vi.mocked(orchestrator.status).mockResolvedValue({ ...STATUS, has_key: true } as never)
    vi.mocked(orchestrator.test).mockResolvedValue({
      ok: true,
      state: 'verified',
      message: "The Orchestrator model 'vendor/alpha' answered a real request.",
      detail: null,
      model: 'vendor/alpha',
      latency_ms: 420,
    } as never)

    render(<OrchestratorSettings />)
    await userEvent.type(await screen.findByLabelText('Model ID'), 'vendor/alpha')
    await userEvent.click(screen.getByRole('button', { name: /verify model/i }))

    expect(await screen.findByLabelText('configuration state')).toHaveTextContent('verified')
  })

  it('surfaces a failed verification with the provider message', async () => {
    mocks.settings = { openrouter_api_key: { configured: true, masked: '***' } }
    vi.mocked(orchestrator.status).mockResolvedValue({ ...STATUS, has_key: true } as never)
    vi.mocked(orchestrator.test).mockResolvedValue({
      ok: false,
      state: 'failed',
      message: 'Insufficient credits',
      detail: 'code 402',
      model: 'vendor/alpha',
      latency_ms: 300,
    } as never)

    render(<OrchestratorSettings />)
    await userEvent.type(await screen.findByLabelText('Model ID'), 'vendor/alpha')
    await userEvent.click(screen.getByRole('button', { name: /verify model/i }))

    expect(await screen.findByLabelText('configuration state')).toHaveTextContent('failed')
    expect(screen.getByText(/Insufficient credits/)).toBeInTheDocument()
  })

  it('retrieves models and saves the chosen one', async () => {
    mocks.settings = { openrouter_api_key: { configured: true, masked: '***' } }
    vi.mocked(orchestrator.status).mockResolvedValue({ ...STATUS, has_key: true } as never)
    vi.mocked(orchestrator.models).mockResolvedValue([
      {
        id: 'vendor/alpha',
        name: 'Alpha',
        context_length: 200000,
        supports_structured_output: true,
        pricing: {},
      },
      {
        id: 'vendor/beta',
        name: 'Beta',
        context_length: 32000,
        supports_structured_output: false,
        pricing: {},
      },
    ] as never)

    render(<OrchestratorSettings />)
    await userEvent.click(await screen.findByRole('button', { name: /retrieve models/i }))
    expect(await screen.findByText('vendor/alpha')).toBeInTheDocument()

    await userEvent.click(screen.getByText('vendor/beta'))
    await userEvent.click(screen.getByRole('button', { name: /save model/i }))

    await waitFor(() =>
      expect(orchestrator.config).toHaveBeenCalledWith({ model: 'vendor/beta' }),
    )
  })

  it('filters a large model list', async () => {
    mocks.settings = { openrouter_api_key: { configured: true, masked: '***' } }
    vi.mocked(orchestrator.status).mockResolvedValue({ ...STATUS, has_key: true } as never)
    vi.mocked(orchestrator.models).mockResolvedValue(
      Array.from({ length: 120 }, (_, index) => ({
        id: `vendor/model-${index}`,
        name: `Model ${index}`,
        context_length: 1000,
        supports_structured_output: false,
        pricing: {},
      })) as never,
    )

    render(<OrchestratorSettings />)
    await userEvent.click(await screen.findByRole('button', { name: /retrieve models/i }))
    await screen.findByText('vendor/model-0')

    await userEvent.type(screen.getByLabelText('Filter models'), 'model-119')
    expect(await screen.findByText('vendor/model-119')).toBeInTheDocument()
    expect(screen.queryByText('vendor/model-0')).not.toBeInTheDocument()
  })

  it('can disable the orchestrator model', async () => {
    render(<OrchestratorSettings />)
    const toggle = await screen.findByRole('checkbox', {
      name: /use the orchestrator model/i,
    })
    expect(toggle).toBeChecked()
    await userEvent.click(toggle)
    await waitFor(() => expect(orchestrator.config).toHaveBeenCalledWith({ enabled: false }))
  })

  it('removes the stored key', async () => {
    mocks.settings = { openrouter_api_key: { configured: true, masked: '***' } }
    vi.mocked(orchestrator.status).mockResolvedValue({ ...STATUS, has_key: true } as never)

    render(<OrchestratorSettings />)
    await userEvent.click(await screen.findByRole('button', { name: /remove key/i }))
    await waitFor(() =>
      expect(api.settings.removeSecret).toHaveBeenCalledWith('openrouter_api_key'),
    )
  })
})
