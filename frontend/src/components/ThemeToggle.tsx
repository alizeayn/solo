/**
 * Appearance control.
 *
 * A three-way segmented control rather than a two-state toggle, because "follow
 * the system" is a distinct, useful choice — and it is the one most people want
 * on a laptop that switches appearance at dusk.
 */

import { useThemeContext } from '../state/ThemeProvider'
import type { ThemePreference } from '../types'

const OPTIONS: { id: ThemePreference; label: string; glyph: string; hint: string }[] = [
  { id: 'light', label: 'Light', glyph: '☀', hint: 'Always light' },
  { id: 'dark', label: 'Dark', glyph: '☾', hint: 'Always dark' },
  { id: 'system', label: 'Auto', glyph: '◐', hint: 'Follow the operating system' },
]

export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { preference, resolved, choose } = useThemeContext()

  return (
    <div
      className={`theme-toggle ${compact ? 'theme-toggle--compact' : ''}`}
      role="radiogroup"
      aria-label={`Appearance (currently ${resolved})`}
    >
      {OPTIONS.map((option) => (
        <button
          key={option.id}
          type="button"
          role="radio"
          aria-checked={preference === option.id}
          aria-label={option.label}
          title={`${option.label} — ${option.hint}`}
          className={`theme-toggle__option ${
            preference === option.id ? 'theme-toggle__option--active' : ''
          }`}
          onClick={() => choose(option.id)}
        >
          <span aria-hidden="true">{option.glyph}</span>
          {!compact && <span>{option.label}</span>}
        </button>
      ))}
    </div>
  )
}
