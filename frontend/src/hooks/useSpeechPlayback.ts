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
 * * **On by default, because that is what "voice" means.** The previous default
 *   of *off* was justified as avoiding an autoplay fight, but the effect was that
 *   Solo synthesised and paid for audio nobody ever requested: the server log
 *   showed thirteen successful ElevenLabs calls and zero fetches of the audio.
 *   A user who configures a voice expects to hear it. Browsers still refuse
 *   autoplay before any interaction, so the blocked case is *reported and
 *   recovered* instead of being silently swallowed.
 * * **A blocked line is never lost.** If the browser refuses to play, the line
 *   goes back to the front of the queue and is retried on the next user gesture.
 *   Marking it seen would mean the very lines that explain a task could never be
 *   heard, even after the user clicked something.
 *
 * It is deliberately not coupled to ElevenLabs: it fetches whatever the backend
 * serves at `/api/voice/audio/{lineId}`, so swapping the transport changes
 * nothing here.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '../api/client'
import type { NarrationLine } from '../types'

const PREFERENCE_KEY = 'solo.voice.playback'

export interface SpeechPlayback {
  speaking: boolean
  /** User preference. On by default; persisted so a reload keeps it. */
  enabled: boolean
  setEnabled: (value: boolean) => void
  /** True when the browser refused playback until the user interacts. */
  blocked: boolean
  /** Id of the line currently being spoken, if any. */
  currentId: string | null
  stop: () => boolean
}

function readPreference(): boolean {
  if (typeof window === 'undefined') return true
  try {
    const stored = window.localStorage.getItem(PREFERENCE_KEY)
    // Absent means "never chosen": default to on.
    return stored === null ? true : stored === 'true'
  } catch {
    return true
  }
}

function isAutoplayRefusal(error: unknown): boolean {
  const name = (error as { name?: string } | null)?.name
  // Chrome/Safari use NotAllowedError; Firefox has used NotAllowedError too,
  // and some builds surface the audio element's own "play() failed" message.
  if (name === 'NotAllowedError') return true
  return /play\(\) (request was interrupted|failed)|not allowed/i.test(String(error))
}

export function useSpeechPlayback(lines: NarrationLine[]): SpeechPlayback {
  const [enabled, setEnabledState] = useState<boolean>(readPreference)
  const [speaking, setSpeaking] = useState(false)
  const [blocked, setBlocked] = useState(false)
  const [currentId, setCurrentId] = useState<string | null>(null)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const queueRef = useRef<NarrationLine[]>([])
  const drainingRef = useRef(false)
  // Lines that have genuinely finished (played, or failed for a reason other
  // than an autoplay refusal), so a re-render cannot replay them.
  const seenRef = useRef<Set<string>>(new Set())

  // Created on first use rather than in a mount effect. The queueing effect is
  // declared before it, so an eager element was still null on the very first
  // drain and the line was silently skipped. That was invisible while playback
  // defaulted to off and only surfaced once it defaulted to on.
  const ensureAudio = useCallback((): HTMLAudioElement => {
    if (!audioRef.current) {
      const audio = new Audio()
      audio.preload = 'auto'
      audioRef.current = audio
    }
    return audioRef.current
  }, [])

  const setEnabled = useCallback((value: boolean) => {
    setEnabledState(value)
    try {
      window.localStorage.setItem(PREFERENCE_KEY, String(value))
    } catch {
      /* storage unavailable (private mode); the session still works */
    }
  }, [])

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
        const line = queueRef.current[0]
        const audio = ensureAudio()
        if (!line) break

        audio.src = api.voice.audioUrl(line.id)
        setCurrentId(line.id)
        try {
          await audio.play()
        } catch (error) {
          if (isAutoplayRefusal(error)) {
            // Leave the line queued and tell the user what to do. The next
            // user gesture resumes from exactly here.
            setBlocked(true)
            setSpeaking(false)
            setCurrentId(null)
            break
          }
          // The audio is genuinely unavailable; do not block the queue on it.
          queueRef.current.shift()
          seenRef.current.add(line.id)
          setCurrentId(null)
          continue
        }

        // Playback started, so the gesture requirement is satisfied.
        setBlocked(false)
        queueRef.current.shift()
        seenRef.current.add(line.id)
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
  }, [ensureAudio])

  // Queue newly-spoken lines. Only lines the transport actually spoke are
  // played; a line whose synthesis failed simply has no audio to fetch.
  useEffect(() => {
    if (!enabled) return
    for (const line of lines) {
      if (!line.spoken) continue
      if (seenRef.current.has(line.id)) continue
      if (queueRef.current.some((queued) => queued.id === line.id)) continue
      queueRef.current.push(line)
    }
    void drain()
  }, [lines, enabled, drain])

  useEffect(() => {
    if (!enabled) stop()
  }, [enabled, stop])

  useEffect(() => {
    return () => {
      audioRef.current?.pause()
      audioRef.current = null
    }
  }, [])

  // A blocked queue resumes on the first interaction, whatever it is: the user
  // does not have to find a particular button to hear what Solo is doing.
  useEffect(() => {
    if (!blocked || !enabled) return
    const resume = () => {
      setBlocked(false)
      void drain()
    }
    const options = { once: true } as AddEventListenerOptions
    window.addEventListener('pointerdown', resume, options)
    window.addEventListener('keydown', resume, options)
    window.addEventListener('touchstart', resume, options)
    return () => {
      window.removeEventListener('pointerdown', resume)
      window.removeEventListener('keydown', resume)
      window.removeEventListener('touchstart', resume)
    }
  }, [blocked, enabled, drain])

  return { speaking, enabled, setEnabled, blocked, currentId, stop }
}
