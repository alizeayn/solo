/**
 * Tests for real-time voice input.
 *
 * The protocol assertions here are not guesses: they encode what the live
 * service actually accepts, which differs from how the API reference names its
 * frames. Sending `type` instead of `message_type` produces
 *
 *   {"message_type":"input_error","error":"Message must be a valid protocol message"}
 *
 * and the session then does nothing at all — the microphone is open, the socket
 * is connected, and no text ever arrives. That is worth a test.
 */

import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  sttToken: vi.fn(),
}))

vi.mock('../api/client', () => ({
  api: { voice: { sttToken: (...a: unknown[]) => mocks.sttToken(...a) } },
}))

import { useRealtimeVoice } from './useRealtimeVoice'

/** A WebSocket that records what was sent and can be driven by the test. */
class FakeSocket {
  static instances: FakeSocket[] = []
  static OPEN = 1
  url: string
  readyState = 0
  sent: string[] = []
  private listeners: Record<string, Array<(event: unknown) => void>> = {}
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: ((event: { reason: string }) => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeSocket.instances.push(this)
  }

  addEventListener(type: string, fn: (event: unknown) => void): void {
    ;(this.listeners[type] ||= []).push(fn)
  }

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.readyState = 3
  }

  /** Simulate the handshake completing. */
  open(): void {
    this.readyState = FakeSocket.OPEN
    for (const fn of this.listeners.open ?? []) fn({})
  }

  receive(frame: Record<string, unknown>): void {
    this.onmessage?.({ data: JSON.stringify(frame) })
  }
}

class FakeWorkletNode {
  static instances: FakeWorkletNode[] = []
  port = { onmessage: null as ((event: { data: ArrayBuffer }) => void) | null }
  constructor() {
    FakeWorkletNode.instances.push(this)
  }
  connect(): void {}
  disconnect(): void {}
}

class FakeAudioContext {
  audioWorklet = { addModule: vi.fn(async () => undefined) }
  destination = {}
  createGain() {
    return { gain: { value: 0 }, connect: vi.fn(), disconnect: vi.fn() }
  }
  createMediaStreamSource() {
    return { connect: vi.fn() }
  }
  close = vi.fn(async () => undefined)
}

const TOKEN_TICKET = {
  available: true,
  reason: null,
  token: 'sutkn_test',
  model_id: 'scribe_v2_realtime',
  url: 'wss://api.elevenlabs.io/v1/speech-to-text/realtime',
}


/** Start a session and complete the handshake.
 *
 * `start()` resolves only once the socket opens, and the socket is created after
 * the token fetch, the microphone grant and the worklet load — so the test has
 * to let those settle before it can drive the open event.
 */
async function startSession(result: { current: { start: () => Promise<void> } }) {
  const started = result.current.start()
  await waitFor(() => expect(FakeSocket.instances.length).toBeGreaterThan(0))
  FakeSocket.instances[0].open()
  await started
}

describe('useRealtimeVoice', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    FakeSocket.instances = []
    FakeWorkletNode.instances = []
    mocks.sttToken.mockResolvedValue(TOKEN_TICKET)
    vi.stubGlobal('WebSocket', Object.assign(FakeSocket, { OPEN: 1 }))
    vi.stubGlobal('AudioContext', FakeAudioContext)
    vi.stubGlobal('AudioWorkletNode', FakeWorkletNode)
    // Keep the real constructor: the test parses the socket URL with it.
    vi.stubGlobal('URL', Object.assign(URL, {
      createObjectURL: () => 'blob:worklet',
      revokeObjectURL: () => undefined,
    }))
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn(async () => ({
          getTracks: () => [{ stop: vi.fn() }],
        })),
      },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('does nothing until started', () => {
    const { result } = renderHook(() => useRealtimeVoice(vi.fn()))
    expect(result.current.active).toBe(false)
    expect(FakeSocket.instances).toHaveLength(0)
  })

  it('connects with the documented query parameters and the token, not the key', async () => {
    const { result } = renderHook(() => useRealtimeVoice(vi.fn()))
    await act(async () => {
      await startSession(result)
    })

    const socket = FakeSocket.instances[0]
    expect(socket).toBeDefined()
    const query = new URL(socket.url).searchParams
    expect(query.get('model_id')).toBe('scribe_v2_realtime')
    expect(query.get('audio_format')).toBe('pcm_16000')
    expect(query.get('commit_strategy')).toBe('vad')
    expect(query.get('token')).toBe('sutkn_test')
    // The API key must never appear in a browser-visible URL.
    expect(socket.url).not.toContain('xi-api-key')
  })

  it('shows an interim transcript without dispatching it', async () => {
    const onCommit = vi.fn()
    const { result } = renderHook(() => useRealtimeVoice(onCommit))
    await act(async () => {
      await startSession(result)
    })

    act(() => FakeSocket.instances[0].receive({ message_type: 'partial_transcript', text: 'create a log' }))

    expect(result.current.partial).toBe('create a log')
    // Partial text changes; dispatching it would build tasks from half-sentences.
    expect(onCommit).not.toHaveBeenCalled()
  })

  it('dispatches on the committed transcript, which is the stable one', async () => {
    const onCommit = vi.fn()
    const { result } = renderHook(() => useRealtimeVoice(onCommit))
    await act(async () => {
      await startSession(result)
    })

    act(() =>
      FakeSocket.instances[0].receive({
        message_type: 'committed_transcript',
        text: 'create a login page',
      }),
    )

    expect(onCommit).toHaveBeenCalledWith('create a login page')
    expect(result.current.partial).toBe('')
  })

  it('sends audio as input_audio_chunk with base64, the shape the service accepts', async () => {
    const { result } = renderHook(() => useRealtimeVoice(vi.fn()))
    await act(async () => {
      await startSession(result)
    })

    // Feed one frame of audio through the worklet port, then let the flush run.
    act(() => {
      FakeWorkletNode.instances[0].port.onmessage?.({
        data: new Int16Array([1000, -1000, 2000]).buffer,
      })
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 150))
    })

    const frames = FakeSocket.instances[0].sent
    expect(frames.length).toBeGreaterThan(0)
    const frame = JSON.parse(frames[0])
    // The exact shape the live service accepts. `type` would be rejected with
    // "Message must be a valid protocol message" and the session would go quiet.
    expect(frame.message_type).toBe('input_audio_chunk')
    expect(typeof frame.audio_base_64).toBe('string')
    expect(frame.audio_base_64.length).toBeGreaterThan(0)
  })

  it('reports a service error frame instead of failing silently', async () => {
    const { result } = renderHook(() => useRealtimeVoice(vi.fn()))
    await act(async () => {
      await startSession(result)
    })

    act(() =>
      FakeSocket.instances[0].receive({
        message_type: 'quota_exceeded',
        error: 'You have exceeded your quota.',
      }),
    )

    expect(result.current.error).toMatch(/exceeded your quota/i)
    expect(result.current.state).toBe('error')
  })

  it('reports why realtime is unavailable and does not open a socket', async () => {
    mocks.sttToken.mockResolvedValue({
      available: false,
      reason: 'No ElevenLabs key is configured.',
      token: null,
    })
    const { result } = renderHook(() => useRealtimeVoice(vi.fn()))
    await act(async () => {
      await result.current.start()
    })

    // Not an error the user caused: the panel stays usable and the batch
    // transcriber remains available.
    expect(result.current.reason).toMatch(/no elevenlabs key/i)
    expect(result.current.error).toBeNull()
    expect(FakeSocket.instances).toHaveLength(0)
  })

  it('surfaces a blocked microphone so the user knows what to fix', async () => {
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn(async () => {
          throw Object.assign(new Error('denied'), { name: 'NotAllowedError' })
        }),
      },
    })
    const { result } = renderHook(() => useRealtimeVoice(vi.fn()))
    await act(async () => {
      await result.current.start()
    })

    expect(result.current.error).toMatch(/microphone access was blocked/i)
    // Worth stating in the message: a browser only offers the microphone on a
    // secure origin, which is what makes LAN-over-http fail.
    expect(result.current.error).toMatch(/secure origin/i)
  })

  it('releases the session when stopped', async () => {
    const { result } = renderHook(() => useRealtimeVoice(vi.fn()))
    await act(async () => {
      await startSession(result)
    })
    await waitFor(() => expect(result.current.active).toBe(true))

    act(() => result.current.stop())
    expect(result.current.active).toBe(false)
    expect(result.current.state).toBe('idle')
  })
})
