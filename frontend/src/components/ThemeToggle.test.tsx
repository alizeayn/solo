import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api/client', () => ({
  api: { settings: { update: vi.fn().mockResolvedValue({}) } },
}))

import { api } from '../api/client'
import { applyTheme, resolveTheme } from '../hooks/useTheme'
import { ThemeProvider, useThemeContext } from '../state/ThemeProvider'
import ThemeToggle from '../components/ThemeToggle'

function Probe() {
  const { preference, resolved } = useThemeContext()
  return (
    <div>
      <span data-testid="preference">{preference}</span>
      <span data-testid="resolved">{resolved}</span>
    </div>
  )
}

describe('theme resolution', () => {
  it('maps an explicit preference directly', () => {
    expect(resolveTheme('dark')).toBe('dark')
    expect(resolveTheme('light')).toBe('light')
  })

  it('applies the theme to the document element', () => {
    applyTheme('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    applyTheme('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })
})

describe('ThemeToggle', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.mocked(api.settings.update).mockClear()
  })

  afterEach(() => {
    window.localStorage.clear()
  })

  it('offers three explicit choices', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    )
    const options = screen.getAllByRole('radio')
    expect(options).toHaveLength(3)
    expect(screen.getByRole('radio', { name: 'Light' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Dark' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Auto' })).toBeInTheDocument()
  })

  it('switches to light, applies it and persists the choice', async () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
        <Probe />
      </ThemeProvider>,
    )

    await userEvent.click(screen.getByRole('radio', { name: 'Light' }))

    expect(screen.getByTestId('preference')).toHaveTextContent('light')
    expect(screen.getByTestId('resolved')).toHaveTextContent('light')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(window.localStorage.getItem('solo.theme')).toBe('light')
  })

  it('saves the preference to the account, not only to the browser', async () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    )
    await userEvent.click(screen.getByRole('radio', { name: 'Dark' }))
    expect(api.settings.update).toHaveBeenCalledWith({ theme: 'dark' })
  })

  it('applies the theme even when saving it fails', async () => {
    vi.mocked(api.settings.update).mockRejectedValueOnce(new Error('offline'))
    render(
      <ThemeProvider>
        <ThemeToggle />
        <Probe />
      </ThemeProvider>,
    )
    await userEvent.click(screen.getByRole('radio', { name: 'Light' }))
    // The visual change must not depend on the network round trip.
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(screen.getByTestId('resolved')).toHaveTextContent('light')
  })

  it('restores a stored preference on mount', () => {
    window.localStorage.setItem('solo.theme', 'light')
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId('preference')).toHaveTextContent('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })

  it('ignores a corrupt stored value', () => {
    window.localStorage.setItem('solo.theme', 'chartreuse')
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId('preference')).toHaveTextContent('dark')
  })
})
