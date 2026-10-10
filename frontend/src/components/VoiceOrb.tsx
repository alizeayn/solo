/**
 * Voice indicator.
 *
 * A visual placeholder for the live voice interface. It is animated so the
 * workspace communicates the intended interaction, and it is **explicitly
 * labelled as a preview**: Solo does not process audio yet (Phase 4), and the
 * UI must never imply otherwise.
 *
 * The animation is CSS-only (no timers, no requestAnimationFrame), so it costs
 * nothing when idle and keeps running smoothly while a task streams.
 */

import { useEffect, useState } from 'react'

export type VoiceState = 'preview' | 'ready' | 'listening' | 'speaking' | 'connecting'

const LABELS: Record<VoiceState, string> = {
  preview: 'Voice preview',
  ready: 'Voice ready',
  listening: 'Listening',
  speaking: 'Speaking',
  connecting: 'Connecting',
}

const HINTS: Record<VoiceState, string> = {
  preview: 'Live voice conversations are implemented in Phase 4 — this is the placeholder.',
  ready: 'Press to start a voice conversation.',
  listening: 'Listening… press again to stop.',
  speaking: 'The assistant is speaking.',
  connecting: 'Connecting to the voice service…',
}

export default function VoiceOrb({
  state = 'preview',
  onToggle,
  disabled = false,
}: {
  state?: VoiceState
  onToggle?: () => void
  disabled?: boolean
}) {
  const [live, setLive] = useState(false)
  const active = state === 'listening' || state === 'speaking'

  // Once mounted, allow the CSS animation to begin so the first paint is cheap.
  useEffect(() => {
    const timer = window.setTimeout(() => setLive(true), 40)
    return () => window.clearTimeout(timer)
  }, [])

  return (
    <div className={`voice ${active ? 'voice--active' : ''}`}>
      <button
        type="button"
        className={`voice__orb voice__orb--${state} ${live ? 'voice__orb--live' : ''}`}
        onClick={onToggle}
        disabled={disabled || !onToggle}
        aria-label={`${LABELS[state]}. ${HINTS[state]}`}
        title={HINTS[state]}
      >
        <span className="voice__ring voice__ring--1" aria-hidden="true" />
        <span className="voice__ring voice__ring--2" aria-hidden="true" />
        <span className="voice__ring voice__ring--3" aria-hidden="true" />
        <span className="voice__core" aria-hidden="true">
          {/* A simple waveform communicates "audio", without pretending to be live. */}
          <span className="voice__bar" />
          <span className="voice__bar" />
          <span className="voice__bar" />
          <span className="voice__bar" />
        </span>
      </button>
      <div className="voice__meta">
        <span className={`pill pill--${state === 'preview' ? 'neutral' : 'active'}`}>
          {LABELS[state]}
        </span>
        <span className="hint">
          {state === 'preview'
            ? 'not enabled yet'
            : state === 'ready'
              ? 'ready'
              : 'live'}
        </span>
      </div>
    </div>
  )
}
