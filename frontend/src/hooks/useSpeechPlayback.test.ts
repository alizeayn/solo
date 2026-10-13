/**
 * Tests for the speech *output* half of the voice loop.
 *
 * This hook had no test, and the defect it shipped with was exactly the kind a
 * test would have caught: playback defaulted to off, so Solo synthesised and paid
 * for audio that the browser never fetched. The server log showed thirteen
 * successful ElevenLabs calls and zero requests for the resulting audio.
 */

import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { NarrationLine } from '../types'
import { useSpeechPlayback } from './useSpeechPlayback'

vi.mock('../api/client', () => ({
  api: { voice: { audioUrl: (id: string) => `/api/voice/audio/${id}` } },
}))

/** Minimal stand-in for HTMLAudioElement, driven by the test. */
class FakeAudio {
  static instances: FakeAudio[] = []
  /** When true, play() rejects the way a browser refuses autoplay. */
  static failPlay = false
  src = ''
  paused = true
  preload = ''
  playCount = 0
  private listeners: Record<string, Array<() => void>> = {}

  constructor() {
    FakeAudio.instances.push(this)
  }

  play(): Promise<void> {
    this.playCount += 1
    if (FakeAudio.failPlay) {
      return Promise.reject(
        Object.assign(new Error('play() failed'), { name: 'NotAllowedError' }),
      )
    }
    this.paused = false
    return Promise.resolve()
  }

  pause(): void {
    this.paused = true
  }

  load(): void {}

  removeAttribute(): void {
    this.src = ''
  }

  addEventListener(type: string, fn: () => void): void {
    ;(this.listeners[type] ||= []).push(fn)
  }

  removeEventListener(type: string, fn: () => void): void {
    this.listeners[type] = (this.listeners[type] ?? []).filter((item) => item !== fn)
  }

  /** Simulate the audio finishing. */
  finish(): void {
    for (const fn of this.listeners.ended ?? []) fn()
  }
}

function line(id: string, spoken: boolean): NarrationLine {
  return { id, text: `line ${id}`, kind: 'milestone', spoken } as NarrationLine
}

describe('useSpeechPlayback', () => {
  beforeEach(() => {
    FakeAudio.instances = []
    FakeAudio.failPlay = false
    vi.stubGlobal('Audio', FakeAudio)
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('is on by default, because that is what configuring a voice means', () => {
    const { result } = renderHook(() => useSpeechPlayback([]))
    expect(result.current.enabled).toBe(true)
    expect(result.current.blocked).toBe(false)
  })

  it('fetches and plays the audio for a spoken line', async () => {
    const { result } = renderHook(() => useSpeechPlayback([line('l1', true)]))

    await waitFor(() => expect(FakeAudio.instances.length).toBe(1))
    const audio = FakeAudio.instances[0]
    await waitFor(() => expect(audio.src).toBe('/api/voice/audio/l1'))
    expect(result.current.currentId).toBe('l1')
    expect(result.current.speaking).toBe(true)
  })

  it('never fetches audio for a line that was not spoken', async () => {
    renderHook(() => useSpeechPlayback([line('l2', false)]))
    await new Promise((resolve) => setTimeout(resolve, 20))
    // Nothing to play means no audio element is even created, let alone fetched.
    expect(FakeAudio.instances).toHaveLength(0)
  })

  it('reports a blocked queue and resumes on the next interaction', async () => {
    // The browser refuses playback until the user has interacted at all.
    FakeAudio.failPlay = true
    const { result } = renderHook(() => useSpeechPlayback([line('l3', true)]))

    await waitFor(() => expect(result.current.blocked).toBe(true))

    // The line was NOT lost: after a gesture it is still available and plays.
    FakeAudio.failPlay = false
    await act(async () => {
      window.dispatchEvent(new Event('pointerdown'))
    })
    await waitFor(() => expect(result.current.currentId).toBe('l3'))
    expect(result.current.blocked).toBe(false)
  })

  it('persists the preference so a reload keeps the choice', async () => {
    const { result } = renderHook(() => useSpeechPlayback([]))
    act(() => result.current.setEnabled(false))
    expect(window.localStorage.getItem('solo.voice.playback')).toBe('false')
    expect(result.current.enabled).toBe(false)

    // A fresh mount reads it back.
    const second = renderHook(() => useSpeechPlayback([]))
    expect(second.result.current.enabled).toBe(false)
  })

  it('does not replay a line that already played', async () => {
    const spoken = [line('l4', true)]
    const { rerender } = renderHook(({ lines }) => useSpeechPlayback(lines), {
      initialProps: { lines: spoken },
    })
    await waitFor(() => expect(FakeAudio.instances.length).toBe(1))
    const audio = FakeAudio.instances[0]
    await act(async () => {
      audio.finish()
    })

    // Re-rendering with the same line must not start it again.
    rerender({ lines: [...spoken] })
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(audio.playCount).toBe(1)
  })
})
