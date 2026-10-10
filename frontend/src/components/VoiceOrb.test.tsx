import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import VoiceOrb from './VoiceOrb'

describe('VoiceOrb', () => {
  it('animates but is explicitly labelled as a preview, not as working voice', () => {
    render(<VoiceOrb state="preview" />)
    expect(screen.getByText('Voice preview')).toBeInTheDocument()
    expect(screen.getByText('not enabled yet')).toBeInTheDocument()
    const orb = screen.getByRole('button')
    // The accessible name must not claim the feature works.
    expect(orb).toHaveAttribute(
      'aria-label',
      expect.stringContaining('Phase 4'),
    )
  })

  it('uses the animated orb class so the indicator is visible', async () => {
    const { container } = render(<VoiceOrb state="preview" />)
    // The animation class is applied after first paint, so wait for it.
    await waitFor(() =>
      expect(container.querySelector('.voice__orb--live')).toBeTruthy(),
    )
    expect(container.querySelectorAll('.voice__ring').length).toBeGreaterThan(0)
    expect(container.querySelectorAll('.voice__bar').length).toBeGreaterThan(0)
  })

  it('shows a live state when voice is actually available', () => {
    const onToggle = vi.fn()
    render(<VoiceOrb state="listening" onToggle={onToggle} />)
    expect(screen.getByText('Listening')).toBeInTheDocument()
    expect(screen.getByText('live')).toBeInTheDocument()
  })

  it('is not clickable when no handler is provided', () => {
    render(<VoiceOrb state="preview" />)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('invokes the toggle when interactive', async () => {
    const onToggle = vi.fn()
    render(<VoiceOrb state="ready" onToggle={onToggle} />)
    await userEvent.click(screen.getByRole('button'))
    expect(onToggle).toHaveBeenCalledTimes(1)
  })
})
