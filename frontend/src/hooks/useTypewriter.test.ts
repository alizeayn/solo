import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useTypewriter } from './useTypewriter'

describe('useTypewriter', () => {
  it('shows text in full when disabled', () => {
    const { result } = renderHook(() => useTypewriter('complete text', { enabled: false }))
    expect(result.current.shown).toBe('complete text')
    expect(result.current.revealing).toBe(false)
  })

  it('returns nothing for empty input', () => {
    const { result } = renderHook(() => useTypewriter('', { enabled: true }))
    expect(result.current.shown).toBe('')
    expect(result.current.revealing).toBe(false)
  })

  it('reveals progressively and then reports completion', async () => {
    const text = 'a'.repeat(60)
    const { result } = renderHook(() => useTypewriter(text, { enabled: true }))

    // Starts shorter than the full text…
    expect(result.current.shown.length).toBeLessThan(text.length)

    // …and reaches it without the caller having to wait for anything else.
    await waitFor(() => expect(result.current.shown).toBe(text), { timeout: 3000 })
    expect(result.current.revealing).toBe(false)
  })

  it('handles null detail', () => {
    const { result } = renderHook(() => useTypewriter(null, { enabled: true }))
    expect(result.current.shown).toBe('')
  })
})
