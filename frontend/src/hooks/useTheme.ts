/**
 * Theme handling.
 *
 * Three preferences — dark, light and "follow the system" — resolved to one
 * effective theme that is applied as a `data-theme` attribute on `<html>`.
 * Every colour in the stylesheet is a CSS custom property defined per theme, so
 * nothing else in the app needs to know which theme is active.
 *
 * The preference is stored in two places on purpose:
 *
 *   * `localStorage` so the correct theme is applied before first paint (see the
 *     inline script in `index.html`) and there is no flash of the wrong theme;
 *   * Solo's settings, so it follows the account to another browser.
 *
 * `localStorage` is a cache of the server value, never the source of truth.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '../api/client'
import type { ThemePreference } from '../types'

const STORAGE_KEY = 'solo.theme'

/** The stored preference, or `dark` when nothing has been chosen. */
export function readStoredPreference(): ThemePreference {
  if (typeof window === 'undefined') return 'dark'
  const raw = window.localStorage.getItem(STORAGE_KEY)
  return raw === 'light' || raw === 'system' || raw === 'dark' ? raw : 'dark'
}

function systemPrefersLight(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false
  return window.matchMedia('(prefers-color-scheme: light)').matches
}

/** Resolve a preference to the theme that should actually be shown. */
export function resolveTheme(preference: ThemePreference): 'dark' | 'light' {
  if (preference === 'system') return systemPrefersLight() ? 'light' : 'dark'
  return preference
}

/** Apply a theme to the document. Exported so tests can drive it directly. */
export function applyTheme(theme: 'dark' | 'light'): void {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.theme = theme
}

export function useTheme() {
  const [preference, setPreference] = useState<ThemePreference>(readStoredPreference)
  const [systemLight, setSystemLight] = useState(systemPrefersLight)

  const resolved = useMemo<'dark' | 'light'>(
    () => (preference === 'system' ? (systemLight ? 'light' : 'dark') : preference),
    [preference, systemLight],
  )

  // Follow the operating system while "system" is selected.
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const query = window.matchMedia('(prefers-color-scheme: light)')
    const update = () => setSystemLight(query.matches)
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])

  useEffect(() => {
    applyTheme(resolved)
  }, [resolved])

  const choose = useCallback(
    async (next: ThemePreference) => {
      setPreference(next)
      try {
        window.localStorage.setItem(STORAGE_KEY, next)
      } catch {
        /* private mode: the preference simply will not persist locally */
      }
      // Persisting server-side is best effort: the theme has already changed.
      try {
        await api.settings.update({ theme: next })
      } catch {
        /* not signed in yet, or offline — the local choice still applies */
      }
    },
    [],
  )

  return { preference, resolved, choose }
}
