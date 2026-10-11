/**
 * Progressive text reveal for milestone detail.
 *
 * The reveal is *presentation only*: the milestone's text arrives complete from
 * the backend and the hook decides how much of it to show yet. Nothing is
 * delayed waiting for the animation — the surrounding state (stage, status,
 * evidence) updates immediately, and a milestone that is no longer current shows
 * its full text at once.
 *
 * Disabled entirely when the user prefers reduced motion.
 */

import { useEffect, useRef, useState } from 'react'

/** Roughly 120 characters per second, in small chunks to stay smooth. */
const CHUNK = 3
const TICK_MS = 24

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function useTypewriter(
  text: string | null | undefined,
  { enabled = true }: { enabled?: boolean } = {},
): { shown: string; revealing: boolean } {
  const full = text ?? ''
  const active = enabled && !prefersReducedMotion() && full.length > 0

  const [shown, setShown] = useState(active ? '' : full)
  const frame = useRef<number | null>(null)
  const previous = useRef(full)

  useEffect(() => {
    // A different text starts a fresh reveal; the same text is left alone.
    if (previous.current !== full) {
      previous.current = full
      setShown(active ? '' : full)
    }
    if (!active) {
      setShown(full)
      return
    }

    let cancelled = false
    let cursor = 0

    const step = () => {
      if (cancelled) return
      cursor = Math.min(cursor + CHUNK, full.length)
      setShown(full.slice(0, cursor))
      if (cursor < full.length) {
        frame.current = window.setTimeout(step, TICK_MS)
      }
    }

    frame.current = window.setTimeout(step, TICK_MS)
    return () => {
      cancelled = true
      if (frame.current !== null) window.clearTimeout(frame.current)
    }
  }, [full, active])

  return { shown, revealing: active && shown.length < full.length }
}

export { prefersReducedMotion }
