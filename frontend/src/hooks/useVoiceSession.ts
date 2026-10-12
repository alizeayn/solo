/**
 * A continuous voice session: one click to open, one click to close.
 *
 * Not push-to-talk. Holding a button while talking is a poor way to hold a
 * conversation, and it makes the interface feel like a walkie-talkie rather than
 * an assistant. Instead the session opens, stays open, and listens in turns
 * until the user explicitly ends it.
 *
 * How a turn is detected: the microphone is analysed with the Web Audio API and
 * each utterance is segmented on silence (see `SILENCE_MS`). A segment is
 * transcribed, handed to the caller, and the next segment starts automatically —
 * so the user never touches the interface between sentences.
 *
 * Two honest limits, both deliberate:
 *
 * * **This is a lightweight voice-activity detector, not the ElevenLabs realtime
 *   socket.** It segments on loudness, so a very quiet speaker may need to talk
 *   a little louder, and a noisy room can hold a segment open. `scribe_v2_realtime`
 *   is the documented upgrade path and would remove the segmentation entirely.
 * * **The session pauses while Solo is speaking.** The microphone would
 *   otherwise hear the assistant's own voice and transcribe it as a new
 *   instruction, which is a feedback loop. The caller reports playback state so
 *   this can be gated.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

/** RMS above which a frame counts as speech. Tuned for a laptop microphone. */
const SPEECH_RMS = 0.02
/** Silence this long ends a turn. */
const SILENCE_MS = 1000
/** Ignore blips: a turn must contain at least this much speech. */
const MIN_SPEECH_MS = 300
/** Hard cap, so a noisy room still yields a turn. */
const MAX_TURN_MS = 20000

export type VoiceSessionState =
  | 'idle'
  | 'starting'
  | 'listening'
  | 'thinking'
  | 'error'

export interface VoiceSession {
  supported: boolean
  active: boolean
  state: VoiceSessionState
  /** 0..1 input loudness, for the animation. Updated every animation frame. */
  level: number
  error: string | null
  start: () => Promise<void>
  stop: () => void
  /** Pause capture while the assistant is speaking, to avoid hearing itself. */
  setPaused: (paused: boolean) => void
}

function describe(cause: unknown): string {
  const name = (cause as { name?: string } | null)?.name
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return 'Microphone access was blocked. Allow it for this site, then start again.'
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'No microphone was found. Connect one and start again.'
    case 'NotReadableError':
      return 'The microphone is in use by another application.'
    default:
      return cause instanceof Error ? cause.message : String(cause)
  }
}

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined
  for (const type of ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']) {
    if (MediaRecorder.isTypeSupported?.(type)) return type
  }
  return undefined
}

export function useVoiceSession(
  onUtterance: (audio: Blob) => Promise<void>,
): VoiceSession {
  const supported =
    typeof navigator !== 'undefined' &&
    typeof window !== 'undefined' &&
    typeof MediaRecorder !== 'undefined' &&
    typeof AudioContext !== 'undefined' &&
    Boolean(navigator.mediaDevices?.getUserMedia)

  const [active, setActive] = useState(false)
  const [state, setState] = useState<VoiceSessionState>('idle')
  const [level, setLevel] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const streamRef = useRef<MediaStream | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const rafRef = useRef<number | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const turnRef = useRef({ startedAt: 0, speechMs: 0, lastSpeechAt: 0, sawSpeech: false })
  const pausedRef = useRef(false)
  const activeRef = useRef(false)
  const mimeRef = useRef<string | undefined>(undefined)
  const onUtteranceRef = useRef(onUtterance)
  onUtteranceRef.current = onUtterance

  const release = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    if (recorderRef.current && recorderRef.current.state === 'recording') {
      try {
        recorderRef.current.stop()
      } catch {
        /* nothing useful to do */
      }
    }
    recorderRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    void ctxRef.current?.close().catch(() => undefined)
    ctxRef.current = null
    setLevel(0)
  }, [])

  const stop = useCallback(() => {
    activeRef.current = false
    release()
    setActive(false)
    setState('idle')
  }, [release])

  /** Finish the current turn and hand it over, then keep listening. */
  const closeTurn = useCallback(() => {
    const recorder = recorderRef.current
    if (!recorder || recorder.state !== 'recording') return
    try {
      recorder.stop()
    } catch {
      /* the onstop handler will not fire; start a fresh turn below */
    }
  }, [])

  const beginTurn = useCallback(() => {
    const stream = streamRef.current
    if (!stream || !activeRef.current || pausedRef.current) return
    if (recorderRef.current && recorderRef.current.state === 'recording') return

    chunksRef.current = []
    turnRef.current = { startedAt: Date.now(), speechMs: 0, lastSpeechAt: 0, sawSpeech: false }

    let recorder: MediaRecorder
    try {
      recorder = new MediaRecorder(
        stream,
        mimeRef.current ? { mimeType: mimeRef.current } : undefined,
      )
    } catch (cause) {
      setError(describe(cause))
      setState('error')
      return
    }
    recorderRef.current = recorder
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunksRef.current.push(event.data)
    }
    recorder.onstop = () => {
      const chunks = chunksRef.current
      chunksRef.current = []
      const { sawSpeech, speechMs } = turnRef.current
      recorderRef.current = null

      const worthSending = sawSpeech && speechMs >= MIN_SPEECH_MS && chunks.length > 0
      if (!worthSending) {
        if (activeRef.current && !pausedRef.current) beginTurn()
        return
      }

      const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' })
      setState('thinking')
      void onUtteranceRef
        .current(blob)
        .catch(() => undefined)
        .finally(() => {
          // The session is still open: listen again unless it was ended or Solo
          // is talking.
          if (activeRef.current) {
            setState(pausedRef.current ? 'listening' : 'listening')
            beginTurn()
          }
        })
    }
    try {
      recorder.start()
    } catch (cause) {
      setError(describe(cause))
      setState('error')
    }
  }, [])

  const analyse = useCallback(() => {
    const analyser = ctxRef.current
    if (!analyser) return
    const node = analyser.createAnalyser()
    node.fftSize = 1024
    const buffer = new Uint8Array(node.fftSize)

    const tick = () => {
      if (!activeRef.current) return
      node.getByteTimeDomainData(buffer)
      let sum = 0
      for (let i = 0; i < buffer.length; i += 1) {
        const v = (buffer[i] - 128) / 128
        sum += v * v
      }
      const rms = Math.sqrt(sum / buffer.length)
      setLevel(Math.min(1, rms * 6))

      const now = Date.now()
      const speaking = rms > SPEECH_RMS
      const turn = turnRef.current

      if (speaking && !pausedRef.current) {
        turn.sawSpeech = true
        turn.lastSpeechAt = now
        turn.speechMs += 16
      }

      // End the turn on silence, or on the hard cap so a noisy room still yields.
      if (!pausedRef.current) {
        const quietFor = turn.lastSpeechAt ? now - turn.lastSpeechAt : 0
        const turnAge = turn.startedAt ? now - turn.startedAt : 0
        const shouldClose =
          (turn.sawSpeech && quietFor > SILENCE_MS) ||
          (turn.sawSpeech && turnAge > MAX_TURN_MS)
        if (shouldClose && recorderRef.current?.state === 'recording') closeTurn()
      }

      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
  }, [closeTurn])

  const start = useCallback(async () => {
    if (!supported || activeRef.current) return
    setError(null)
    setState('starting')

    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      })
    } catch (cause) {
      setError(describe(cause))
      setState('error')
      return
    }

    try {
      const ctx = new AudioContext()
      const source = ctx.createMediaStreamSource(stream)
      // The analyser has to be part of the graph; nothing is played back.
      const sink = ctx.createGain()
      sink.gain.value = 0
      source.connect(sink)
      sink.connect(ctx.destination)
      ctxRef.current = ctx
    } catch (cause) {
      stream.getTracks().forEach((t) => t.stop())
      setError(describe(cause))
      setState('error')
      return
    }

    streamRef.current = stream
    mimeRef.current = pickMimeType()
    activeRef.current = true
    setActive(true)
    setState('listening')
    analyse()
    beginTurn()
  }, [analyse, beginTurn, supported])

  const setPaused = useCallback(
    (paused: boolean) => {
      pausedRef.current = paused
      if (!activeRef.current) return
      if (paused) {
        // Stop capturing: the microphone would otherwise hear the assistant.
        closeTurn()
      } else if (!recorderRef.current) {
        beginTurn()
      }
    },
    [beginTurn, closeTurn],
  )

  useEffect(
    () => () => {
      activeRef.current = false
      release()
    },
    [release],
  )

  return { supported, active, state, level, error, start, stop, setPaused }
}
