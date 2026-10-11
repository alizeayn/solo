/**
 * Theme context.
 *
 * One provider owns the appearance preference so that the header control, the
 * settings pane and the Dockview chrome all read the same value. Mounted above
 * the auth views too, so the sign-in and setup screens are themed as well.
 */

import { createContext, useContext, type ReactNode } from 'react'

import { useTheme } from '../hooks/useTheme'
import type { ThemePreference } from '../types'

interface ThemeContextValue {
  preference: ThemePreference
  resolved: 'dark' | 'light'
  choose: (next: ThemePreference) => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { preference, resolved, choose } = useTheme()
  return (
    <ThemeContext.Provider value={{ preference, resolved, choose: (n) => void choose(n) }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useThemeContext(): ThemeContextValue {
  const value = useContext(ThemeContext)
  if (value === null) {
    throw new Error('useThemeContext must be used inside <ThemeProvider>')
  }
  return value
}
