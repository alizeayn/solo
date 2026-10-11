/**
 * Recording-hook tests.
 *
 * `MediaRecorder` and `getUserMedia` are stubbed, so these cover the decisions
 * the hook makes rather than the browser's behaviour: which failures are named
 * specifically, when a recording is too short to send, and that the microphone
 * track is always released.
 */

import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useVoiceInput } from './useVoiceInput'

class FakeTrack {
  stopped = false
  stop() {
    this.stopped = true
  }
}

class FakeStream {
  tracks = [new FakeTrack()]
  getTracks() {
    return this.tracks
  }
}

class FakeRecorder {
  static instances: FakeRecorder[] = []
  static isTypeSupported = () => true
  state: 'inactive' | 'recording' = 'inactive'
  mimeType = 'audio/webm'
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  onerror: ((event: unknown) => void) | null = null

  constructor(_stream: unknown, _options?: unknown) {
    FakeRecorder.instances.push(this)
  }

  start() {
    this.state = 'recording'
    // A real recorder emits at least one chunk before stopping.
    queueMicrotask(() => this.ondataavailable?.({ data: new Blob(['chunk']) }))
  }

  stop() {
    this.state = 'inactive'
    this.onstop?.()
  }
}

const getUserMedia = vi.fn()

function installStubs() {
  FakeRecorder.instances = []
  ;(globalThis as Record<string, unknown>).MediaRecorder = FakeRecorder
  Object.defineProperty(globalThis.navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  })
}

describe('useVoiceInput', () => {
  beforeEach(() => {
    vi.useRealTimers()
    getUserMedia.mockReset()
    installStubs()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('reports a blocked microphone specifically', async () => {
    const denied = new Error('denied')
    denied.name = 'NotAllowedError'
    getUserMedia.mockRejectedValue(denied)

    const { result } = renderHook(() => useVoiceInput())
    await act(async () => {
      expect(await result.current.start()).toBe(false)
    })

    expect(result.current.error).toMatch(/microphone access was blocked/i)
    expect(result.current.permission).toBe('denied')
    expect(result.current.recording).toBe(false)
  })

  it('distinguishes a missing microphone from a blocked one', async () => {
    const missing = new Error('none')
    missing.name = 'NotFoundError'
    getUserMedia.mockRejectedValue(missing)

    const { result } = renderHook(() => useVoiceInput())
    await act(async () => {
      await result.current.start()
    })
    expect(result.current.error).toMatch(/no microphone was found/i)
  })

  it('returns a blob and releases the microphone on stop', async () => {
    const stream = new FakeStream()
    getUserMedia.mockResolvedValue(stream)

    const { result } = renderHook(() => useVoiceInput())
    await act(async () => {
      expect(await result.current.start()).toBe(true)
    })
    expect(result.current.recording).toBe(true)

    // Long enough to count as speech.
    await new Promise((resolve) => setTimeout(resolve, 400))
    let blob: Blob | null = null
    await act(async () => {
      blob = await result.current.stop()
    })

    expect(blob).toBeInstanceOf(Blob)
    expect(result.current.recording).toBe(false)
    expect(stream.tracks[0].stopped).toBe(true)
  })

  it('treats a too-short tap as nothing recorded, not as silence to send', async () => {
    getUserMedia.mockResolvedValue(new FakeStream())
    const { result } = renderHook(() => useVoiceInput())

    await act(async () => {
      await result.current.start()
    })
    let blob: Blob | null = 'unset' as unknown as Blob
    await act(async () => {
      blob = await result.current.stop()
    })

    expect(blob).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it('surfaces an explicit error when recording is unsupported', () => {
    ;(globalThis as Record<string, unknown>).MediaRecorder = undefined
    const { result } = renderHook(() => useVoiceInput())
    expect(result.current.supported).toBe(false)
  })

  it('clears a previous error on the next attempt', async () => {
    const denied = new Error('denied')
    denied.name = 'NotAllowedError'
    getUserMedia.mockRejectedValueOnce(denied)
    getUserMedia.mockResolvedValueOnce(new FakeStream())

    const { result } = renderHook(() => useVoiceInput())
    await act(async () => {
      await result.current.start()
    })
    expect(result.current.error).toBeTruthy()

    await act(async () => {
      await result.current.start()
    })
    await waitFor(() => expect(result.current.error).toBeNull())
    expect(result.current.permission).toBe('granted')
  })
})
