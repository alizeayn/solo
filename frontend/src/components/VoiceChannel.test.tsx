/**
 * Voice channel tests — the session model.
 *
 * The panel opens a session that stays open until the user ends it, and there is
 * deliberately no hold-to-talk. The session hook and the playback hook are
 * mocked so these assert the wiring and the interaction contract: one control to
 * start, one to end, the state shown honestly, a turn dispatched down the real
 * task path, and barge-in by talking rather than by pressing anything.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  state: {} as Record<string, unknown>,
  voiceState: {} as Record<string, unknown>,
  transcribe: vi.fn(),
  sendMessage: vi.fn(),
  say: vi.fn(async (_text: string, _kind?: string) => ({ queued: true, id: 'g1', state: {} })),
  reportError: vi.fn(),
  start: vi.fn(),
  stop: vi.fn(),
  setPaused: vi.fn(),
  stopSpeaking: vi.fn(),
  setPlaybackEnabled: vi.fn(),
  session: {} as Record<string, unknown>,
  /** The handler the panel passes to the session hook. */
  lastOnUtterance: null as null | ((audio: Blob) => Promise<void>),
  playback: {} as Record<string, unknown>,
}))

vi.mock('../state/WorkspaceProvider', () => ({ useWorkspace: () => mocks.state }))
vi.mock('../api/client', () => ({
  api: {
    voice: {
      state: vi.fn(async () => mocks.voiceState),
      transcribe: (...a: unknown[]) => mocks.transcribe(...a),
      say: (text: string, kind?: string) => mocks.say(text, kind),
      audioUrl: (id: string) => `/api/voice/audio/${id}`,
    },
  },
}))
vi.mock('../hooks/useVoiceSession', () => ({
  useVoiceSession: (onUtterance: (audio: Blob) => Promise<void>) => {
    mocks.lastOnUtterance = onUtterance
    return mocks.session
  },
}))
vi.mock('../hooks/useSpeechPlayback', () => ({ useSpeechPlayback: () => mocks.playback }))

import VoiceChannel from './VoiceChannel'

const CONFIGURED = {
  transport: 'elevenlabs', audio_available: true, configured: true, needs_voice: false,
  listening: false, queued: 0, dropped: 1, spoken: 2, recent: [],
  model_id: 'eleven_flash_v2_5', voice_id: 'v1', phase: 'voice-active',
}
const UNCONFIGURED = {
  ...CONFIGURED, transport: 'recording', audio_available: false, configured: false,
  needs_voice: false, phase: 'narration-only',
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
      project: { id: 'p1', name: 'demo' },
      tasks: [],
    }
    mocks.session = {
      supported: true, active: false, state: 'idle', level: 0, error: null,
      start: mocks.start, stop: mocks.stop, setPaused: mocks.setPaused,
    }
    mocks.playback = {
      speaking: false, enabled: false, currentId: null,
      setEnabled: mocks.setPlaybackEnabled, stop: mocks.stopSpeaking,
    }
  })

  it('starts a session from one control and does not require holding it', async () => {
    render(<VoiceChannel />)
    await userEvent.click(await screen.findByRole('button', { name: /Start voice session/i }))
    expect(mocks.start).toHaveBeenCalledTimes(1)
    // Nothing about the interaction depends on a press being held.
    expect(screen.queryByText(/hold/i)).toBeNull()
  })

  it('shows an open session and offers an obvious way to end it', async () => {
    mocks.session = { ...mocks.session, active: true, state: 'listening' }
    render(<VoiceChannel />)
    expect(await screen.findByText('session open')).toBeInTheDocument()
    expect(screen.getByText(/speak normally/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /End voice session/i }))
    expect(mocks.stop).toHaveBeenCalledTimes(1)
    // While a session is open there is no second start button to confuse things.
    expect(screen.queryByRole('button', { name: /^Start voice session/i })).toBeNull()
  })

  it('reflects thinking and speaking states in the interface', async () => {
    mocks.session = { ...mocks.session, active: true, state: 'thinking' }
    const { rerender } = render(<VoiceChannel />)
    expect(await screen.findByText(/Working out what you said/i)).toBeInTheDocument()

    mocks.playback = { ...mocks.playback, speaking: true }
    rerender(<VoiceChannel />)
    expect(await screen.findByText('Solo is speaking')).toBeInTheDocument()
  })

  it('disables starting when speech is not configured, and says why', async () => {
    mocks.voiceState = UNCONFIGURED
    render(<VoiceChannel />)
    const button = await screen.findByRole('button', { name: /Start voice session/i })
    expect(button).toBeDisabled()
    expect(screen.getByText(/Speech is not configured/i)).toBeInTheDocument()
  })

  it('disables starting when the browser cannot record', async () => {
    mocks.session = { ...mocks.session, supported: false }
    render(<VoiceChannel />)
    const button = await screen.findByRole('button', { name: /Start voice session/i })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('title', expect.stringMatching(/cannot record/i))
  })

  it('sends a transcribed turn down the normal task path', async () => {
    mocks.transcribe.mockResolvedValue({ text: 'Write a calculator', empty: false })
    mocks.sendMessage.mockResolvedValue({ intent: 'START_CODING_TASK' })
    render(<VoiceChannel />)
    await screen.findByRole('button', { name: /Start voice session/i })

    // Drive a completed turn exactly as the session hook would.
    expect(mocks.lastOnUtterance).toBeTypeOf('function')
    await mocks.lastOnUtterance!(new Blob(['audio'], { type: 'audio/webm' }))

    expect(mocks.transcribe).toHaveBeenCalledTimes(1)
    expect(mocks.sendMessage).toHaveBeenCalledWith('Write a calculator')
    // The user can see what was understood.
    expect(await screen.findByText('Write a calculator')).toBeInTheDocument()
  })

  it('reports an empty turn instead of dispatching an empty task', async () => {
    mocks.transcribe.mockResolvedValue({ text: '', empty: true })
    render(<VoiceChannel />)
    await screen.findByRole('button', { name: /Start voice session/i })
    await mocks.lastOnUtterance!(new Blob(['audio'], { type: 'audio/webm' }))

    expect(mocks.sendMessage).not.toHaveBeenCalled()
    expect(await screen.findByText(/No speech was detected/i)).toBeInTheDocument()
  })

  it('reports a transcript failure without dispatching anything', async () => {
    mocks.transcribe.mockRejectedValue(new Error('ElevenLabs rejected the API key.'))
    render(<VoiceChannel />)
    await screen.findByRole('button', { name: /Start voice session/i })
    await mocks.lastOnUtterance!(new Blob(['audio'], { type: 'audio/webm' }))

    expect(mocks.sendMessage).not.toHaveBeenCalled()
    expect(mocks.reportError).toHaveBeenCalledWith('ElevenLabs rejected the API key.')
  })

  it('reports a needs-voice account rather than silently doing nothing', async () => {
    mocks.voiceState = { ...CONFIGURED, audio_available: false, needs_voice: true }
    render(<VoiceChannel />)
    expect(await screen.findByText(/voice id is required/i)).toBeInTheDocument()
  })

  it('says voice output is broken when a configured account still fails', async () => {
    // The account is fully configured, so nothing looks wrong -- but every
    // synthesis attempt failed. Saying nothing here is what made a dead
    // integration look healthy.
    mocks.voiceState = {
      ...CONFIGURED,
      audio_available: false,
      configured: true,
      voice_configured: true,
      phase: 'narration-only',
      speech_failures: 3,
      audio_error: { message: 'This request exceeds your quota of 10000.' },
    }
    render(<VoiceChannel />)

    expect(await screen.findByText(/voice output is not working/i)).toBeInTheDocument()
    expect(screen.getByText(/exceeds your quota of 10000/i)).toBeInTheDocument()
    // The user is told text still works, so the failure is not alarming.
    expect(screen.getByText(/still shown here as text/i)).toBeInTheDocument()
  })

  it('does not cry wolf when speech is working', async () => {
    mocks.voiceState = { ...CONFIGURED, audio_error: null, speech_failures: 0 }
    render(<VoiceChannel />)
    await screen.findByRole('button', { name: /Voice off/i })
    expect(screen.queryByText(/voice output is not working/i)).not.toBeInTheDocument()
  })

  it('shows the voice output toggle when audio is available', async () => {
    render(<VoiceChannel />)
    expect(await screen.findByRole('button', { name: /Voice off/i })).toBeInTheDocument()
  })

  it('hides the voice output toggle when audio is unavailable', async () => {
    // A separate mount, because the panel deliberately fetches voice state on
    // mount and on a slow interval rather than on every render.
    mocks.voiceState = UNCONFIGURED
    render(<VoiceChannel />)
    await screen.findByText(/Speech is not configured/i)
    expect(screen.queryByRole('button', { name: /Voice off/i })).toBeNull()
  })

  it('pauses capture while Solo is speaking, so it cannot hear itself', async () => {
    mocks.session = { ...mocks.session, active: true, state: 'listening' }
    mocks.playback = { ...mocks.playback, speaking: true }
    render(<VoiceChannel />)
    await waitFor(() => expect(mocks.setPaused).toHaveBeenCalledWith(true))
  })

  it('lets the user interrupt by talking, without pressing anything', async () => {
    mocks.session = { ...mocks.session, active: true, state: 'listening', level: 0.9 }
    mocks.playback = { ...mocks.playback, speaking: true }
    render(<VoiceChannel />)
    await waitFor(() => expect(mocks.stopSpeaking).toHaveBeenCalled())
  })

  it('renders narration lines with their kind', async () => {
    mocks.state = {
      ...mocks.state,
      narration: [
        { id: 'a', text: 'Understanding the request', kind: 'progress', priority: 2, task_id: 't', project_id: 'p', created_at: new Date().toISOString(), spoken_at: null },
        { id: 'b', text: 'Task complete', kind: 'outcome', priority: 1, task_id: 't', project_id: 'p', created_at: new Date().toISOString(), spoken_at: null },
      ],
    }
    render(<VoiceChannel />)
    expect(await screen.findByText('Understanding the request')).toBeInTheDocument()
    expect(screen.getByText('Result')).toBeInTheDocument()
  })

  it('shows an honest empty state', async () => {
    render(<VoiceChannel />)
    expect(await screen.findByText(/Nothing to say yet/i)).toBeInTheDocument()
  })
})

describe('VoiceChannel conversation start', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.voiceState = CONFIGURED
    mocks.state = {
      narration: [],
      connection: 'open',
      sendMessage: mocks.sendMessage,
      reportError: mocks.reportError,
      project: { id: 'p1', name: 'demo' },
      tasks: [],
    }
    mocks.session = {
      supported: true, active: false, state: 'idle', level: 0, error: null,
      start: mocks.start, stop: mocks.stop, setPaused: mocks.setPaused,
    }
    mocks.playback = {
      speaking: false, enabled: true, blocked: false, currentId: null,
      setEnabled: mocks.setPlaybackEnabled, stop: mocks.stopSpeaking,
    }
  })

  it('greets the user when the session opens, and names the project', async () => {
    // A session that opens in silence gives the user nothing to respond to.
    mocks.session = { ...mocks.session, active: true, state: 'listening' }
    render(<VoiceChannel />)

    await waitFor(() => expect(mocks.say).toHaveBeenCalled())
    const [text, kind] = mocks.say.mock.calls[0]
    expect(kind).toBe('greeting')
    expect(String(text)).toMatch(/what would you like/i)
    expect(String(text)).toContain('demo')
  })

  it('greets once per session, not on every re-render', async () => {
    mocks.session = { ...mocks.session, active: true, state: 'listening' }
    const { rerender } = render(<VoiceChannel />)
    await waitFor(() => expect(mocks.say).toHaveBeenCalledTimes(1))

    rerender(<VoiceChannel />)
    rerender(<VoiceChannel />)
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(mocks.say).toHaveBeenCalledTimes(1)
  })

  it('offers to change the current task when one is still running', async () => {
    mocks.state = {
      ...mocks.state,
      tasks: [{ id: 't1', status: 'running', instruction: 'build a page' }],
    }
    mocks.session = { ...mocks.session, active: true, state: 'listening' }
    render(<VoiceChannel />)

    await waitFor(() => expect(mocks.say).toHaveBeenCalled())
    expect(String(mocks.say.mock.calls[0][0])).toMatch(/still working/i)
  })
})
