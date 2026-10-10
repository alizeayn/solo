import { describe, expect, it } from 'vitest'

import {
  clockTime,
  eventGlyph,
  eventLabel,
  relativeTime,
  statusLabel,
  statusTone,
  truncate,
} from './format'

describe('statusLabel', () => {
  it('maps every task status to a readable label', () => {
    expect(statusLabel('RUNNING')).toBe('Running')
    expect(statusLabel('RECOVERY_REQUIRED')).toBe('Needs review')
    expect(statusLabel('COMPLETED')).toBe('Completed')
  })
})

describe('statusTone', () => {
  it('classifies statuses into visual tones', () => {
    expect(statusTone('COMPLETED')).toBe('success')
    expect(statusTone('FAILED')).toBe('danger')
    expect(statusTone('RUNNING')).toBe('active')
    expect(statusTone('CANCELLED')).toBe('warning')
    expect(statusTone('PAUSED')).toBe('neutral')
  })
})

describe('eventLabel', () => {
  it('provides friendly names for normalised event types', () => {
    expect(eventLabel('file.changed')).toBe('File changed')
    expect(eventLabel('progress.summary')).toBe('Progress')
    expect(eventLabel('unknown.type')).toBe('unknown.type')
  })
})

describe('eventGlyph', () => {
  it('always returns a non-empty glyph', () => {
    expect(eventGlyph('error')).toBe('!')
    expect(eventGlyph('nope')).toBe('•')
  })
})

describe('relativeTime', () => {
  const now = new Date('2026-10-10T12:00:00Z')

  it('describes recent timestamps', () => {
    expect(relativeTime('2026-10-10T11:59:58Z', now)).toBe('just now')
    expect(relativeTime('2026-10-10T11:59:30Z', now)).toBe('30s ago')
    expect(relativeTime('2026-10-10T11:55:00Z', now)).toBe('5m ago')
    expect(relativeTime('2026-10-10T09:00:00Z', now)).toBe('3h ago')
    expect(relativeTime('2026-10-08T12:00:00Z', now)).toBe('2d ago')
  })

  it('never returns a negative age for future timestamps', () => {
    expect(relativeTime('2026-10-10T12:05:00Z', now)).toBe('just now')
  })
})

describe('clockTime', () => {
  it('returns the input unchanged when it is not a valid date', () => {
    expect(clockTime('not-a-date')).toBe('not-a-date')
  })
})

describe('truncate', () => {
  it('leaves short strings alone and ellipsises long ones', () => {
    expect(truncate('short', 20)).toBe('short')
    expect(truncate('a'.repeat(30), 10)).toHaveLength(10)
    expect(truncate('a'.repeat(30), 10).endsWith('…')).toBe(true)
  })
})
