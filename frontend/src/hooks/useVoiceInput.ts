/**
 * Push-to-talk voice input.
 *
 * Deliberately the simplest reliable thing that works: the browser records one
 * utterance with `MediaRecorder`, and the blob is sent to the backend for
 * transcription. That is coarser than streaming recognition (ElevenLabs'
 * `scribe_v2_realtime`, ~150ms), but it needs no socket lifecycle, no
 * voice-activity detection tuning and no partial-transcript UI — and the text it
 * produces goes to the *existing* message endpoint, so the whole agent pipeline
 * is unchanged.
 *
 * The hook is honest about its limits rather than pretending:
 *
 * * `supported` is false when the browser cannot record, and the UI says so
 *   instead of showing a dead button.
 * * Permission failures are surfaced specifically, because "blocked" and "no
 *   microphone" need different fixes.
 * * `stop()` resolves with a blob or null; a recording that captured nothing is
 *   reported, never sent as silence.
 *
 * Turn-taking is push-to-talk, not full duplex. That limitation is recorded in
 * `elevenlabs-docs/06-solo-integration.md` rather than glossed over here.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

/** Below this, the user almost certainly tapped rather than spoke. */
const MIN_UTTERANCE_MS = 350

/** Formats every current browser can produce and ElevenLabs can read. */
const PREFERRED_MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/mp4',
]

export type MicrophoneState = 'unknown' | 'prompt' | 'granted' | 'denied'

export interface VoiceInput {
  supported: boolean
  recording: boolean
  error: string | null
  permission: MicrophoneState
  start: () => Promise<boolean>
  stop: () => Promise<Blob | null>
  cancel: () => void
}

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined
  for (const candidate of PREFERRED_MIME_TYPES) {
    if (MediaRecorder.isTypeSupported?.(candidate)) return candidate
  }
  return undefined
}

function describeError(cause: unknown): string {
  const name = (cause as { name?: string } | null)?.name
  switch (name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return 'Microphone access was blocked. Allow it in the browser, then try again.'
    case 'NotFoundError':
    case 'OverconstrainedError':
      return 'No microphone was found. Connect one and try again.'
    case 'NotReadableError':
      return 'The microphone is already in use by another application.'
    default:
      return cause instanceof Error ? cause.message : String(cause)
  }
}

export function useVoiceInput(): VoiceInput {
  const supported =
    typeof navigator !== 'undefined' &&
    typeof window !== 'undefined' &&
    typeof MediaRecorder !== 'undefined' &&
    Boolean(navigator.mediaDevices?.getUserMedia)

  const [recording, setRecording] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [permission, setPermission] = useState<MicrophoneState>('unknown')

  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const startedAtRef = useRef(0)
  const resolveRef = useRef<((blob: Blob | null) => void) | null>(null)

  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
  }, [])

  const finish = useCallback((blob: Blob | null) => {
    resolveRef.current?.(blob)
    resolveRef.current = null
  }, [])

  // A recording in flight must not outlive the component.
  useEffect(
    () => () => {
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop()
      releaseStream()
    },
    [releaseStream],
  )

  const start = useCallback(async (): Promise<boolean> => {
    if (!supported || recording) return false
    setError(null)

    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (cause) {
      setPermission('denied')
      setError(describeError(cause))
      return false
    }
    setPermission('granted')

    const mimeType = pickMimeType()
    let recorder: MediaRecorder
    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    } catch (cause) {
      releaseStream()
      setError(describeError(cause))
      return false
    }

    chunksRef.current = []
    startedAtRef.current = Date.now()
    streamRef.current = stream
    recorderRef.current = recorder

    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunksRef.current.push(event.data)
    }
    recorder.onerror = (event) => {
      const cause = (event as unknown as { error?: unknown }).error
      setError(describeError(cause))
      setRecording(false)
      releaseStream()
      finish(null)
    }
    recorder.onstop = () => {
      const elapsed = Date.now() - startedAtRef.current
      const type = recorder.mimeType || mimeType || 'audio/webm'
      const chunks = chunksRef.current
      chunksRef.current = []
      setRecording(false)
      releaseStream()

      // Too short, or nothing captured: a normal outcome, not something to send
      // to the transcriber as silence.
      if (elapsed < MIN_UTTERANCE_MS || chunks.length === 0) {
        finish(null)
        return
      }
      finish(new Blob(chunks, { type }))
    }

    try {
      recorder.start()
    } catch (cause) {
      releaseStream()
      setError(describeError(cause))
      return false
    }
    setRecording(true)
    return true
  }, [finish, recording, releaseStream, supported])

  const stop = useCallback(async (): Promise<Blob | null> => {
    const recorder = recorderRef.current
    if (!recorder || recorder.state === 'inactive') return null

    return new Promise<Blob | null>((resolve) => {
      resolveRef.current = resolve
      try {
        recorder.stop()
      } catch {
        finish(null)
      }
    })
  }, [finish])

  const cancel = useCallback(() => {
    const recorder = recorderRef.current
    chunksRef.current = []
    if (recorder && recorder.state === 'recording') {
      try {
        recorder.stop()
      } catch {
        /* nothing useful to do */
      }
    }
    releaseStream()
    setRecording(false)
    finish(null)
  }, [finish, releaseStream])

  return { supported, recording, error, permission, start, stop, cancel }
}
