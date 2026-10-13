/**
 * Tests for the workspace reducer logic that feeds the voice loop.
 *
 * The narration upsert is the reason this file exists. A narration line is
 * published twice under one id -- queued (`spoken: false`) and then delivered
 * (`spoken: true`). The provider appended blindly, so the second message was
 * discarded, every line stayed unspoken, the player skipped them all, and audio
 * that had already been generated and paid for was never fetched.
 *
 * It was invisible from every other angle: ElevenLabs returned HTTP 200, credits
 * were spent, the milestones appeared, and only the audio never came.
 */

import { describe, expect, it } from 'vitest'

import { upsertNarration } from './WorkspaceProvider'
import type { NarrationLine } from '../types'

function line(id: string, overrides: Partial<NarrationLine> = {}): NarrationLine {
  return {
    id,
    text: `line ${id}`,
    kind: 'milestone',
    priority: 2,
    task_id: 't1',
    project_id: 'p1',
    created_at: '2026-10-13T00:00:00Z',
    spoken_at: null,
    spoken: false,
    ...overrides,
  } as NarrationLine
}

describe('upsertNarration', () => {
  it('appends a line it has not seen', () => {
    const result = upsertNarration([], line('a'))
    expect(result.map((item) => item.id)).toEqual(['a'])
  })

  it('replaces a queued line when the same id is delivered', () => {
    // This is the regression: the delivered update must win.
    const queued = [line('a', { spoken: false })]
    const delivered = line('a', { spoken: true, spoken_at: '2026-10-13T00:00:01Z' })

    const result = upsertNarration(queued, delivered)

    expect(result).toHaveLength(1)
    expect(result[0].spoken).toBe(true)
    expect(result[0].spoken_at).toBe('2026-10-13T00:00:01Z')
  })

  it('keeps the original text when the update carries none', () => {
    const queued = [line('a', { text: 'I am making the changes now.' })]
    const update = line('a', { text: 'I am making the changes now.', spoken: true })
    const result = upsertNarration(queued, update)
    expect(result[0].text).toBe('I am making the changes now.')
    expect(result[0].spoken).toBe(true)
  })

  it('carries a synthesis failure through to the line', () => {
    const queued = [line('a')]
    const failed = { ...line('a'), spoken: false, error: 'quota exceeded' }
    const result = upsertNarration(queued, failed as NarrationLine)
    expect((result[0] as { error?: string }).error).toBe('quota exceeded')
    expect(result[0].spoken).toBe(false)
  })

  it('leaves other lines untouched and preserves order', () => {
    const lines = [line('a'), line('b'), line('c')]
    const result = upsertNarration(lines, line('b', { spoken: true }))
    expect(result.map((item) => item.id)).toEqual(['a', 'b', 'c'])
    expect(result[0].spoken).toBe(false)
    expect(result[1].spoken).toBe(true)
    expect(result[2].spoken).toBe(false)
  })

  it('bounds the list so a long task cannot grow it without limit', () => {
    const lines = Array.from({ length: 100 }, (_, i) => line(`l${i}`))
    const result = upsertNarration(lines, line('new'), 100)
    expect(result).toHaveLength(100)
    expect(result[result.length - 1].id).toBe('new')
    expect(result[0].id).toBe('l1')
  })
})
