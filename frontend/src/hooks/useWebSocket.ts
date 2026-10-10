/**
 * WebSocket hook for the application event stream.
 *
 * Reconnects with exponential backoff and reports connection state so the UI
 * can show a truthful indicator. The backend re-authenticates via the session
 * cookie; a rejected connection triggers a normal close + retry.
 */

import { useEffect, useRef, useState } from 'react'

import type { ConnectionState, WsEnvelope } from '../types'

const MAX_BACKOFF_MS = 10_000
const BASE_BACKOFF_MS = 500

export function useWebSocket(
  onMessage: (envelope: WsEnvelope) => void,
  enabled: boolean,
): ConnectionState {
  const [state, setState] = useState<ConnectionState>('closed')
  const handlerRef = useRef(onMessage)
  handlerRef.current = onMessage

  useEffect(() => {
    if (!enabled) {
      setState('closed')
      return
    }

    let socket: WebSocket | null = null
    let disposed = false
    let attempt = 0
    let retryTimer: number | undefined

    const connect = () => {
      if (disposed) return
      setState('connecting')
      const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
      socket = new WebSocket(`${scheme}://${window.location.host}/api/ws`)

      socket.onopen = () => {
        attempt = 0
        setState('open')
      }

      socket.onmessage = (event) => {
        try {
          handlerRef.current(JSON.parse(event.data as string) as WsEnvelope)
        } catch {
          /* ignore malformed frames */
        }
      }

      socket.onclose = () => {
        if (disposed) return
        setState('closed')
        attempt += 1
        const delay = Math.min(
          BASE_BACKOFF_MS * 2 ** Math.min(attempt, 5),
          MAX_BACKOFF_MS,
        )
        retryTimer = window.setTimeout(connect, delay)
      }

      socket.onerror = () => {
        socket?.close()
      }
    }

    connect()

    return () => {
      disposed = true
      if (retryTimer !== undefined) window.clearTimeout(retryTimer)
      socket?.close()
    }
  }, [enabled])

  return state
}
