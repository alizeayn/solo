/**
 * Plays the audio the narration pipeline produced.
 *
 * This is the *output* half of the voice loop. It subscribes to the same
 * `narration` stream the Voice panel already renders and, for each line the
 * backend actually synthesised, fetches the MP3 and plays it.
 *
 * Design constraints, each a deliberate choice:
 *
 * * **One at a time.** Lines play sequentially and never overlap. The backend
 *   already guarantees ordering; this must not undo it.
 * * **Speech is optional, never exclusive.** A line with no audio is still shown
 *   in the panel. Information is never audio-only.
 * * **Barge-in wins.** `stop()` cancels playback immediately.
 * * **No autoplay fight.** Browsers block audio until the user has interacted,
 *   so playback is opt-in via `enabled` and a blocked attempt stops quietly
 *   rather than retrying forever.
 *
 * It is deliberately not coupled to ElevenLabs: it fetches whatever the backend
 * serves at `/api/voice/audio/{lineId}`, so swapping the transport changes
 * nothing here.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '../api/client'
import type { NarrationLine } from '../types'

export interface SpeechPlayback {
  speaking: boolean
  /** Off by default: browsers block autoplay until the user interacts. */
  enabled: boolean
  setEnabled: (value: boolean) => void
  stop: () => boolean
  currentId: string | null
}

export function useSpeechPlayback(lines: NarrationLine[]): SpeechPlayback {
  const [enabled, setEnabled] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [currentId, setCurrentId] = useState<string | null>(null)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const queueRef = useRef<NarrationLine[]>([])
  const drainingRef = useRef(false)
  // Track what has been queued so a re-render cannot replay a line.
  const seenRef = useRef<Set<string>>(new Set())

  const stop = useCallback((): boolean => {
    const audio = audioRef.current
    queueRef.current = []
    if (!audio) {
      setSpeaking(false)
      setCurrentId(null)
      return false
    }
    const wasPlaying = !audio.paused
    audio.pause()
    audio.removeAttribute('src')
    audio.load()
    setSpeaking(false)
    setCurrentId(null)
    return wasPlaying
  }, [])

  const drain = useCallback(async () => {
    if (drainingRef.current) return
    drainingRef.current = true
    try {
      while (queueRef.current.length > 0) {
        const line = queueRef.current.shift()
        const audio = audioRef.current
        if (!line || !audio) break

        audio.src = api.voice.audioUrl(line.id)
        setCurrentId(line.id)
        try {
          await audio.play()
        } catch {
          // Autoplay blocked, or the audio is gone. Stop quietly: the line is
          // still visible in the panel, so nothing is lost.
          setSpeaking(false)
          setCurrentId(null)
          break
        }
        setSpeaking(true)
        await new Promise<void>((resolve) => {
          const done = () => {
            audio.removeEventListener('ended', done)
            audio.removeEventListener('error', done)
            resolve()
          }
          audio.addEventListener('ended', done)
          audio.addEventListener('error', done)
        })
      }
    } finally {
      drainingRef.current = false
      setSpeaking(false)
      setCurrentId(null)
    }
  }, [])

  // Queue newly-spoken lines. Only lines the transport actually spoke are
  // played; a line whose synthesis failed simply has no audio to fetch.
  useEffect(() => {
    if (!enabled) return
    for (const line of lines) {
      if (!line.spoken) continue
      if (seenRef.current.has(line.id)) continue
      seenRef.current.add(line.id)
      queueRef.current.push(line)
    }
    void drain()
  }, [lines, enabled, drain])

  useEffect(() => {
    if (!enabled) stop()
  }, [enabled, stop])

  useEffect(() => {
    const audio = new Audio()
    audio.preload = 'auto'
    audioRef.current = audio
    return () => {
      audio.pause()
      audioRef.current = null
    }
  }, [])

  return { speaking, enabled, setEnabled, stop, currentId }
}
