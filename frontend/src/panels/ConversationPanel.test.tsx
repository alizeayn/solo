/**
 * Tests for the unified conversation surface.
 *
 * This panel replaced three separate ones (`Conversation`, `Voice`, `Write`).
 * The behaviours worth guarding are the ones the split got wrong:
 *
 * * a spoken turn and a typed turn are one conversation, in one transcript;
 * * an interim transcript is visible but **never** dispatched;
 * * a failure anywhere else leaves the microphone usable, and the turn is not
 *   silently dropped.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  workspace: {} as Record<string, unknown>,
  realtime: {} as Record<string, unknown>,
  batch: {} as Record<string, unknown>,
  playback: {} as Record<string, unknown>,
  transcribe: vi.fn(),
  upload: vi.fn(),
  realtimeStart: vi.fn(),
  realtimeStop: vi.fn(),
  batchStart: vi.fn(),
  batchStop: vi.fn(),
  lastBatchUtterance: null as null | ((audio: Blob) => Promise<void>),
}))

vi.mock('../state/WorkspaceProvider', () => ({
  useWorkspace: () => mocks.workspace,
}))
vi.mock('../hooks/useRealtimeVoice', () => ({
  BARGE_IN_LEVEL: 0.3,
  useRealtimeVoice: () => mocks.realtime,
}))
vi.mock('../hooks/useVoiceSession', () => ({
  useVoiceSession: (onUtterance: (audio: Blob) => Promise<void>) => {
    mocks.lastBatchUtterance = onUtterance
    return mocks.batch
  },
}))
vi.mock('../hooks/useSpeechPlayback', () => ({ useSpeechPlayback: () => mocks.playback }))
vi.mock('../api/client', () => ({
  api: {
    voice: { transcribe: (...a: unknown[]) => mocks.transcribe(...a) },
    files: { upload: (...a: unknown[]) => mocks.upload(...a) },
  },
}))

import ConversationPanel from './ConversationPanel'

function message(id: string, role: string, content: string, at: string) {
  return { id, role, content, created_at: at }
}
function narration(id: string, text: string, at: string, kind = 'milestone', spoken = true) {
  return {
    id, text, kind, spoken, created_at: at, priority: 2,
    task_id: null, project_id: null, spoken_at: spoken ? at : null,
  }
}

describe('ConversationPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.workspace = {
      project: { id: 'p1', name: 'demo' },
      messages: [],
      narration: [],
      selectedTask: null,
      activeTask: null,
      sendMessage: vi.fn(),
      busy: false,
      cancelTask: vi.fn(),
      reportError: vi.fn(),
    }
    mocks.realtime = {
      supported: true, active: false, state: 'idle', partial: '', level: 0,
      error: null, reason: null, start: mocks.realtimeStart, stop: mocks.realtimeStop,
      setPaused: vi.fn(),
    }
    mocks.batch = {
      supported: true, active: false, state: 'idle', level: 0, error: null,
      start: mocks.batchStart, stop: mocks.batchStop, setPaused: vi.fn(),
    }
    mocks.playback = {
      speaking: false, enabled: true, blocked: false, currentId: null,
      setEnabled: vi.fn(), stop: vi.fn(),
    }
  })

  // --- one conversation ----------------------------------------------------

  it('interleaves spoken narration and typed messages into one transcript', async () => {
    mocks.workspace = {
      ...mocks.workspace,
      messages: [
        message('m1', 'user', 'create a login page', '2026-10-13T10:00:00Z'),
        message('m2', 'assistant', 'Got it.', '2026-10-13T10:00:02Z'),
      ],
      narration: [narration('n1', "I've created login.html.", '2026-10-13T10:00:01Z')],
    }
    render(<ConversationPanel />)

    const bubbles = document.querySelectorAll('.bubble')
    // Chronological across both sources, not two separate lists.
    expect([...bubbles].map((b) => b.textContent)).toEqual([
      expect.stringContaining('create a login page'),
      expect.stringContaining("I've created login.html."),
      expect.stringContaining('Got it.'),
    ])
  })

  it('shows a typed correction in the same thread as the spoken turn', async () => {
    mocks.workspace = {
      ...mocks.workspace,
      messages: [message('m1', 'user', 'make a login page', '2026-10-13T10:00:00Z')],
    }
    render(<ConversationPanel />)

    await userEvent.type(screen.getByLabelText('Message'), 'no, blue button')
    await userEvent.click(screen.getByRole('button', { name: /send/i }))

    // One path, one conversation: the correction is dispatched as a message.
    await waitFor(() =>
      expect(mocks.workspace.sendMessage).toHaveBeenCalledWith('no, blue button'),
    )
  })

  // --- voice ---------------------------------------------------------------

  it('starts a voice session from one control, with nothing held down', async () => {
    render(<ConversationPanel />)
    await userEvent.click(screen.getByRole('button', { name: /start voice session/i }))
    await waitFor(() => expect(mocks.realtimeStart).toHaveBeenCalled())
  })

  it('offers an obvious way to end the session', async () => {
    mocks.realtime = { ...mocks.realtime, active: true, state: 'listening' }
    render(<ConversationPanel />)
    await userEvent.click(screen.getByRole('button', { name: /end voice session/i }))
    expect(mocks.realtimeStop).toHaveBeenCalled()
  })

  it('renders the interim transcript without dispatching it', async () => {
    mocks.realtime = { ...mocks.realtime, active: true, partial: 'create a log' }
    render(<ConversationPanel />)

    // Visible, so the user can see they are being heard...
    expect(screen.getByText('create a log')).toBeInTheDocument()
    // ...and never dispatched: partials change, so acting on one creates tasks
    // from half-sentences.
    expect(mocks.workspace.sendMessage).not.toHaveBeenCalled()
  })

  it('falls back to segmented recording when realtime is unavailable', async () => {
    mocks.realtime = {
      ...mocks.realtime, supported: true, active: false,
      reason: 'No ElevenLabs key is configured.',
    }
    render(<ConversationPanel />)

    expect(await screen.findByText(/realtime voice is unavailable/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /start voice session/i }))
    // The button is not dead: it uses the batch path instead.
    await waitFor(() => expect(mocks.batchStart).toHaveBeenCalled())
  })

  // --- isolation -----------------------------------------------------------

  it('keeps the microphone usable when dispatch fails, and keeps the words', async () => {
    const sendMessage = vi.fn().mockRejectedValue(new Error('Orchestrator rate limited'))
    mocks.workspace = { ...mocks.workspace, sendMessage }

    render(<ConversationPanel />)
    await userEvent.type(screen.getByLabelText('Message'), 'add a signup form')
    await userEvent.click(screen.getByRole('button', { name: /send/i }))

    // The failure is reported against dispatch...
    expect(await screen.findByText(/could not dispatch it/i)).toBeInTheDocument()
    expect(screen.getByText(/Orchestrator rate limited/)).toBeInTheDocument()
    // ...and the user's words come back rather than vanishing.
    await waitFor(() =>
      expect(screen.getByLabelText('Message')).toHaveValue('add a signup form'),
    )
  })

  it('reports a transcription failure without dispatching anything', async () => {
    mocks.transcribe.mockRejectedValue(new Error('ElevenLabs rejected the API key.'))
    render(<ConversationPanel />)

    await waitFor(() => expect(mocks.lastBatchUtterance).not.toBeNull())
    await mocks.lastBatchUtterance?.(new Blob(['x']))

    expect(await screen.findByText(/could not transcribe that turn/i)).toBeInTheDocument()
    expect(mocks.workspace.sendMessage).not.toHaveBeenCalled()
  })

  it('does not dispatch an empty turn', async () => {
    mocks.transcribe.mockResolvedValue({ text: '', empty: true })
    render(<ConversationPanel />)

    await waitFor(() => expect(mocks.lastBatchUtterance).not.toBeNull())
    await mocks.lastBatchUtterance?.(new Blob(['x']))

    expect(await screen.findByText(/no speech was detected/i)).toBeInTheDocument()
    expect(mocks.workspace.sendMessage).not.toHaveBeenCalled()
  })

  it('surfaces a realtime voice error in the panel', async () => {
    mocks.realtime = {
      ...mocks.realtime, error: 'Microphone access was blocked. Allow it for this site.',
    }
    render(<ConversationPanel />)
    expect(await screen.findByText(/microphone access was blocked/i)).toBeInTheDocument()
  })

  // --- attachments ---------------------------------------------------------

  it('attaches a file from the composer rather than a separate panel', async () => {
    mocks.upload.mockResolvedValue({})
    render(<ConversationPanel />)

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['hello'], 'notes.md', { type: 'text/markdown' })
    await userEvent.upload(input, file)

    await waitFor(() => expect(mocks.upload).toHaveBeenCalledWith('p1', file))
    expect(await screen.findByText(/attached notes.md/i)).toBeInTheDocument()
  })

  // --- speech output -------------------------------------------------------

  it('offers a speech toggle and starts on', async () => {
    render(<ConversationPanel />)
    expect(screen.getByRole('button', { name: /speech on/i })).toBeInTheDocument()
  })

  it('says when the browser blocked playback', async () => {
    mocks.playback = { ...mocks.playback, blocked: true, enabled: true }
    render(<ConversationPanel />)
    expect(screen.getByText(/tap to enable sound/i)).toBeInTheDocument()
  })
})
