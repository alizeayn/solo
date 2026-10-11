/**
 * Voice channel tests.
 *
 * The hooks are mocked so these assert the *wiring*: that a transcript goes to
 * the real message path, that an empty transcript is reported rather than sent,
 * and that the panel tells the truth about whether audio is available. The
 * recording mechanics are covered separately in `useVoiceInput.test.ts`.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  state: {} as Record<string, unknown>,
  voiceState: {} as Record<string, unknown>,
  transcribe: vi.fn(),
  interrupt: vi.fn(),
  sendMessage: vi.fn(),
  reportError: vi.fn(),
  input: {} as Record<string, unknown>,
  playback: {} as Record<string, unknown>,
}))

vi.mock('../state/WorkspaceProvider', () => ({
  useWorkspace: () => mocks.state,
}))

vi.mock('../api/client', () => ({
  api: {
    voice: {
      state: vi.fn(async () => mocks.voiceState),
      transcribe: (...args: unknown[]) => mocks.transcribe(...args),
      interrupt: (...args: unknown[]) => mocks.interrupt(...args),
      audioUrl: (id: string) => `/api/voice/audio/${id}`,
    },
  },
}))

vi.mock('../hooks/useVoiceInput', () => ({
  useVoiceInput: () => mocks.input,
}))

vi.mock('../hooks/useSpeechPlayback', () => ({
  useSpeechPlayback: () => mocks.playback,
}))

import VoiceChannel from './VoiceChannel'

const CONFIGURED = {
  transport: 'elevenlabs',
  audio_available: true,
  configured: true,
  listening: false,
  queued: 0,
  dropped: 0,
  spoken: 2,
  recent: [],
  model_id: 'eleven_flash_v2_5',
  phase: 'voice-active',
}

const UNCONFIGURED = {
  ...CONFIGURED,
  transport: 'recording',
  audio_available: false,
  configured: false,
  phase: 'narration-only',
}

function line(partial: Record<string, unknown> = {}) {
  return {
    id: 'l1',
    text: 'Making the changes',
    kind: 'progress',
    priority: 2,
    task_id: 't1',
    project_id: 'p1',
    created_at: new Date().toISOString(),
    spoken_at: new Date().toISOString(),
    spoken: true,
    ...partial,
  }
}

describe('VoiceChannel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.voiceState = CONFIGURED
    mocks.state = {
      narration: [],
      connection: 'open',
      sendMessage: mocks.sendMessage,
      reportError: mocks.reportError,
    }
    mocks.input = {
      supported: true,
      recording: false,
      error: null,
      permission: 'granted',
      start: vi.fn(async () => true),
      stop: vi.fn(async () => new Blob(['audio'], { type: 'audio/webm' })),
      cancel: vi.fn(),
    }
    mocks.playback = {
      speaking: false,
      enabled: false,
      setEnabled: vi.fn(),
      stop: vi.fn(() => false),
      currentId: null,
    }
  })

  it('says narration is not spoken when no key is configured', async () => {
    mocks.voiceState = UNCONFIGURED
    render(<VoiceChannel />)
    expect(await screen.findByText('text only')).toBeInTheDocument()
    expect(screen.getByText(/not spoken/i)).toBeInTheDocument()
  })

  it('offers the speech toggle only when audio is actually available', async () => {
    render(<VoiceChannel />)
    expect(await screen.findByRole('button', { name: /Muted/ })).toBeInTheDocument()
  })

  it('hides the speech toggle when audio is unavailable', async () => {
    mocks.voiceState = UNCONFIGURED
    render(<VoiceChannel />)
    await screen.findByText('text only')
    expect(screen.queryByRole('button', { name: /Muted|Speaking/ })).toBeNull()
  })

  it('disables the microphone when the browser cannot record', async () => {
    mocks.input = { ...mocks.input, supported: false }
    render(<VoiceChannel />)
    const button = await screen.findByRole('button', { name: /Microphone unavailable/ })
    expect(button).toBeDisabled()
  })

  it('transcribes speech and sends it down the normal task path', async () => {
    mocks.transcribe.mockResolvedValue({ text: 'Write a calculator', empty: false })
    mocks.input = {
      ...mocks.input,
      recording: true,
      stop: vi.fn(async () => new Blob(['audio'], { type: 'audio/webm' })),
    }
    mocks.sendMessage.mockResolvedValue({ intent: 'START_CODING_TASK' })

    render(<VoiceChannel />)
    await userEvent.click(await screen.findByRole('button', { name: /Stop and send/ }))

    await waitFor(() => expect(mocks.sendMessage).toHaveBeenCalledWith('Write a calculator'))
    expect(mocks.transcribe).toHaveBeenCalledTimes(1)
    // The transcript is shown, so the user can see what was understood.
    expect(await screen.findByText(/Write a calculator/)).toBeInTheDocument()
  })

  it('reports an empty transcript instead of dispatching an empty task', async () => {
    mocks.transcribe.mockResolvedValue({ text: '', empty: true })
    mocks.input = {
      ...mocks.input,
      recording: true,
      stop: vi.fn(async () => new Blob(['audio'], { type: 'audio/webm' })),
    }

    render(<VoiceChannel />)
    await userEvent.click(await screen.findByRole('button', { name: /Stop and send/ }))

    await waitFor(() =>
      expect(mocks.reportError).toHaveBeenCalledWith(
        expect.stringMatching(/no speech was detected/i),
      ),
    )
    expect(mocks.sendMessage).not.toHaveBeenCalled()
  })

  it('reports a recording that captured nothing rather than sending silence', async () => {
    mocks.input = {
      ...mocks.input,
      recording: true,
      stop: vi.fn(async () => null),
    }
    render(<VoiceChannel />)
    await userEvent.click(await screen.findByRole('button', { name: /Stop and send/ }))

    await waitFor(() =>
      expect(mocks.reportError).toHaveBeenCalledWith(
        expect.stringMatching(/nothing was recorded/i),
      ),
    )
    expect(mocks.transcribe).not.toHaveBeenCalled()
    expect(mocks.sendMessage).not.toHaveBeenCalled()
  })

  it('stops speaking before opening the microphone, so it never talks over the user', async () => {
    mocks.playback = { ...mocks.playback, speaking: true, stop: vi.fn(() => true) }
    mocks.interrupt.mockResolvedValue(CONFIGURED)
    const start = vi.fn(async () => true)
    mocks.input = { ...mocks.input, start }

    render(<VoiceChannel />)
    await userEvent.click(await screen.findByRole('button', { name: /Hold a thought/ }))

    await waitFor(() => expect(start).toHaveBeenCalled())
    expect(mocks.playback.stop).toHaveBeenCalled()
    expect(mocks.interrupt).toHaveBeenCalledWith('user')
  })

  it('renders the narration lines with their kind', async () => {
    mocks.state = {
      ...mocks.state,
      narration: [
        line({ id: 'a', text: 'Understanding the request', kind: 'progress' }),
        line({ id: 'b', text: 'Task complete', kind: 'outcome' }),
      ],
    }
    render(<VoiceChannel />)
    expect(await screen.findByText('Understanding the request')).toBeInTheDocument()
    expect(screen.getByText('Task complete')).toBeInTheDocument()
    expect(screen.getByText('Result')).toBeInTheDocument()
  })

  it('shows an honest empty state', async () => {
    render(<VoiceChannel />)
    expect(await screen.findByText(/Nothing to say yet/i)).toBeInTheDocument()
  })
})
