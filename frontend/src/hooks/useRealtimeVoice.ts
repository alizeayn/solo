/**
 * Real-time voice input, the way ElevenLabs documents it.
 *
 * The browser opens a Realtime Speech-to-Text WebSocket using a **single-use
 * token** minted by Solo, so the API key never leaves the server. Audio is
 * captured with `getUserMedia`, resampled to 16 kHz PCM in an `AudioWorklet`,
 * and streamed as `input_audio_chunk` frames.
 *
 * The wire protocol below was verified against the live service rather than
 * taken from the documentation alone, which matters: the API reference names
 * frames in camelCase (`inputAudioChunk`) while the actual protocol — in both
 * directions — uses a `message_type` field with snake_case values. Sending
 * `type` instead yields `{"message_type":"input_error","error":"Message must be
 * a valid protocol message"}` and the session quietly does nothing.
 *
 * Verified live:
 *   ->  {"message_type":"input_audio_chunk","audio_base_64":"..."}
 *   <-  {"message_type":"session_started","session_id":"...","config":{...}}
 *   <-  {"message_type":"partial_transcript","text":"..."}     interim
 *   <-  {"message_type":"committed_transcript","text":"..."}   final, stable
 *
 * Design rules, each deliberate:
 *
 * * **Only a committed transcript is dispatched.** Partials are interim and
 *   change; acting on them would create tasks from half-sentences.
 * * **Partials are still shown.** Rendering them as live ghost text is what
 *   makes the interaction feel like speech rather than a recording.
 * * **Capture pauses while Solo speaks.** Otherwise the microphone hears the
 *   assistant and transcribes it back as a new instruction.
 * * **Failure is reported, never fatal.** Any error leaves the panel usable and
 *   the batch transcriber available as a fallback.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '../api/client'

/** Level above which the user is considered to be interrupting playback. */
export const BARGE_IN_LEVEL = 0.3

/** Audio is flushed in ~100 ms frames: frequent enough to feel live, far fewer
 * WebSocket frames than one per render quantum (128 samples ≈ 3 ms). */
const FLUSH_MS = 100

const TARGET_SAMPLE_RATE = 16000

/** How long to wait for the socket handshake before giving up on it. Without
 * this, a connection that neither opens nor errors leaves the panel stuck on
 * "connecting" forever with no way back. */
const CONNECT_TIMEOUT_MS = 10000

/**
 * Runs on the audio thread. Down-samples the capture rate to 16 kHz and emits
 * signed 16-bit PCM, which is what `audio_format=pcm_16000` expects.
 */
const CAPTURE_WORKLET = `
class SoloCapture extends AudioWorkletProcessor {
  constructor() {
    super()
    this.ratio = sampleRate / ${TARGET_SAMPLE_RATE}
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0]
    if (!channel) return true
    const length = Math.floor(channel.length / this.ratio)
    if (length <= 0) return true
    const out = new Int16Array(length)
    for (let i = 0; i < length; i += 1) {
      const start = Math.floor(i * this.ratio)
      const end = Math.min(channel.length, Math.floor((i + 1) * this.ratio))
      let sum = 0
      for (let j = start; j < end; j += 1) sum += channel[j]
      const mean = sum / Math.max(1, end - start)
      const clamped = Math.max(-1, Math.min(1, mean))
      out[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff
    }
    this.port.postMessage(out.buffer, [out.buffer])
    return true
  }
}
registerProcessor('solo-capture', SoloCapture)
`

export type RealtimeState = 'idle' | 'connecting' | 'listening' | 'error'

export interface RealtimeVoice {
  /** True when the browser can do this at all (mic + worklet + WebSocket). */
  supported: boolean
  active: boolean
  state: RealtimeState
  /** Live interim text, shown but never dispatched. */
  partial: string
  /** 0..1 input loudness, for the meter and barge-in. */
  level: number
  error: string | null
  /** Why realtime is unavailable, when it is; the batch path still works. */
  reason: string | null
  start: () => Promise<void>
  stop: () => void
  /** Pause capture while Solo speaks, so it cannot hear itself. */
  setPaused: (paused: boolean) => void
}

function base64From(bytes: Uint8Array): string {
  let binary = ''
  const step = 0x8000
  for (let i = 0; i < bytes.length; i += step) {
    binary += String.fromCharCode(...bytes.subarray(i, i + step))
  }
  return btoa(binary)
}

function describe(cause: unknown): string {
  const name = (cause as { name?: string } | null)?.name
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return (
      'Microphone access was blocked. Allow it for this site and try again. ' +
      'A browser only offers the microphone on a secure origin (HTTPS or localhost).'
    )
  }
  if (name === 'NotFoundError') return 'No microphone was found on this device.'
  return cause instanceof Error ? cause.message : String(cause)
}

export function useRealtimeVoice(
  onCommit: (text: string) => void,
): RealtimeVoice {
  const supported =
    typeof window !== 'undefined' &&
    typeof AudioContext !== 'undefined' &&
    typeof AudioWorkletNode !== 'undefined' &&
    typeof WebSocket !== 'undefined' &&
    Boolean(navigator.mediaDevices?.getUserMedia)

  const [active, setActive] = useState(false)
  const [state, setState] = useState<RealtimeState>('idle')
  const [partial, setPartial] = useState('')
  const [level, setLevel] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [reason, setReason] = useState<string | null>(null)

  const socketRef = useRef<WebSocket | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const nodeRef = useRef<AudioWorkletNode | null>(null)
  const sinkRef = useRef<GainNode | null>(null)
  const framesRef = useRef<Int16Array[]>([])
  const timerRef = useRef<number | null>(null)
  const pausedRef = useRef(false)
  const activeRef = useRef(false)
  const onCommitRef = useRef(onCommit)
  onCommitRef.current = onCommit

  const teardown = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current)
      timerRef.current = null
    }
    framesRef.current = []
    try {
      nodeRef.current?.disconnect()
    } catch {
      /* already detached */
    }
    nodeRef.current = null
    try {
      sinkRef.current?.disconnect()
    } catch {
      /* already detached */
    }
    sinkRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    void ctxRef.current?.close().catch(() => undefined)
    ctxRef.current = null
    const socket = socketRef.current
    socketRef.current = null
    if (socket && socket.readyState <= WebSocket.OPEN) {
      try {
        socket.close(1000, 'session ended')
      } catch {
        /* already closing */
      }
    }
    setLevel(0)
    setPartial('')
  }, [])

  const stop = useCallback(() => {
    activeRef.current = false
    setActive(false)
    setState('idle')
    teardown()
  }, [teardown])

  const setPaused = useCallback((paused: boolean) => {
    pausedRef.current = paused
  }, [])

  /** One frame of audio, or nothing while paused (Solo is speaking). */
  const flush = useCallback(() => {
    const socket = socketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) return
    const frames = framesRef.current
    framesRef.current = []
    if (frames.length === 0 || pausedRef.current) return

    let total = 0
    for (const frame of frames) total += frame.length
    const merged = new Int16Array(total)
    let offset = 0
    for (const frame of frames) {
      merged.set(frame, offset)
      offset += frame.length
    }
    // Level for the meter and barge-in, measured on the same audio sent.
    let peak = 0
    for (let i = 0; i < merged.length; i += 8) {
      const value = Math.abs(merged[i]) / 0x7fff
      if (value > peak) peak = value
    }
    setLevel(peak)

    try {
      socket.send(
        JSON.stringify({
          message_type: 'input_audio_chunk',
          audio_base_64: base64From(new Uint8Array(merged.buffer)),
        }),
      )
    } catch (cause) {
      setError(describe(cause))
      setState('error')
    }
  }, [])

  const start = useCallback(async () => {
    if (activeRef.current) return
    setError(null)
    setReason(null)
    setState('connecting')

    // 1. Ask Solo for a scoped token. The API key stays on the server.
    let ticket: Awaited<ReturnType<typeof api.voice.sttToken>>
    try {
      ticket = await api.voice.sttToken()
    } catch (cause) {
      setError(describe(cause))
      setState('error')
      return
    }
    if (!ticket.available || !ticket.token) {
      // Not an error the user caused or can fix here: say what is missing and
      // leave the panel usable. The batch transcriber remains available.
      setReason(ticket.reason ?? 'Realtime voice is unavailable.')
      setState('idle')
      return
    }

    // 2. Capture.
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
    streamRef.current = stream

    try {
      const ctx = new AudioContext()
      ctxRef.current = ctx
      const url = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: 'text/javascript' }))
      try {
        await ctx.audioWorklet.addModule(url)
      } finally {
        URL.revokeObjectURL(url)
      }
      const node = new AudioWorkletNode(ctx, 'solo-capture')
      nodeRef.current = node
      node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        framesRef.current.push(new Int16Array(event.data))
      }
      // A worklet only runs while it is connected to the destination; a silent
      // gain node keeps it pulled without sending the microphone to the speakers.
      const sink = ctx.createGain()
      sink.gain.value = 0
      sinkRef.current = sink
      ctx.createMediaStreamSource(stream).connect(node)
      node.connect(sink)
      sink.connect(ctx.destination)

      // 3. Connect. The query parameters are the documented contract; the token
      //    authenticates the socket without exposing the key.
      const params = new URLSearchParams({
        model_id: ticket.model_id ?? 'scribe_v2_realtime',
        audio_format: 'pcm_16000',
        commit_strategy: 'vad',
        no_verbatim: 'true',
        token: ticket.token,
      })
      const socket = new WebSocket(`${ticket.url}?${params.toString()}`)
      socketRef.current = socket

      socket.onmessage = (event) => {
        let frame: { message_type?: string; text?: string; error?: string }
        try {
          frame = JSON.parse(String(event.data))
        } catch {
          return
        }
        switch (frame.message_type) {
          case 'partial_transcript':
            // Interim only: shown, never dispatched.
            setPartial(frame.text ?? '')
            break
          case 'committed_transcript': {
            const text = (frame.text ?? '').trim()
            setPartial('')
            if (text) onCommitRef.current(text)
            break
          }
          case 'session_started':
            setState('listening')
            break
          default:
            // Every error variant arrives as its own message_type; surfacing the
            // service's own text is more use than a generic failure.
            if (frame.message_type && /error|exceeded|throttled|limited|insufficient/.test(frame.message_type)) {
              setError(frame.error || `Voice input stopped: ${frame.message_type}.`)
              setState('error')
            }
        }
      }
      socket.onerror = () => {
        setError('The realtime voice connection failed.')
        setState('error')
      }
      socket.onclose = (event) => {
        if (!activeRef.current) return
        // A close we did not ask for, with the service's reason where it gave one.
        const detail = event.reason ? ` (${event.reason})` : ''
        setError(`The realtime voice connection closed${detail}.`)
        setState('error')
        activeRef.current = false
        setActive(false)
        teardown()
      }

      const opened = await new Promise<boolean>((resolve) => {
        let settled = false
        const settle = (value: boolean) => {
          if (settled) return
          settled = true
          window.clearTimeout(timer)
          resolve(value)
        }
        const timer = window.setTimeout(() => settle(false), CONNECT_TIMEOUT_MS)
        socket.addEventListener('open', () => settle(true), { once: true })
        socket.addEventListener('error', () => settle(false), { once: true })
        socket.addEventListener('close', () => settle(false), { once: true })
      })

      if (!opened || socket.readyState !== WebSocket.OPEN) {
        setError((current) => current ?? 'The realtime voice connection did not open.')
        setState((current) => (current === 'idle' ? 'error' : current))
        teardown()
        return
      }

      activeRef.current = true
      setActive(true)
      timerRef.current = window.setInterval(flush, FLUSH_MS)
    } catch (cause) {
      setError(describe(cause))
      setState('error')
      teardown()
    }
  }, [flush, teardown])

  // Release the microphone and the socket on unmount: a live session that
  // survives navigation keeps the microphone indicator on and costs credits.
  useEffect(() => {
    return () => {
      activeRef.current = false
      teardown()
    }
  }, [teardown])

  return { supported, active, state, partial, level, error, reason, start, stop, setPaused }
}
