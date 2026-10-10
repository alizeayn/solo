/** Small connection indicator used in the header status strip. */

import type { ConnectionState } from '../types'

export default function StatusBadge({
  label,
  tone,
}: {
  label: string
  tone: 'on' | 'warn' | 'off'
}) {
  const title =
    tone === 'on' ? `${label}: connected` : tone === 'warn' ? `${label}: warning` : `${label}: not configured`

  return (
    <span className="status-strip__item" title={title}>
      <span className={`dot dot--${tone}`} aria-hidden="true" />
      {label}
    </span>
  )
}

/** Maps a WebSocket connection state to a StatusBadge tone. */
export function realtimeTone(state: ConnectionState): 'on' | 'warn' | 'off' {
  if (state === 'open') return 'on'
  if (state === 'connecting') return 'warn'
  return 'off'
}
