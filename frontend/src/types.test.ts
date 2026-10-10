import { describe, expect, it } from 'vitest'

import { isActive, isTerminal, type Task } from './types'

function task(status: Task['status']): Task {
  return {
    id: 't1',
    project_id: 'p1',
    conversation_id: null,
    parent_task_id: null,
    task_type: 'CODING',
    status,
    instruction: 'do something',
    progress_summary: null,
    result_summary: null,
    error: null,
    created_at: '2026-10-10T12:00:00Z',
    updated_at: '2026-10-10T12:00:00Z',
    completed_at: null,
  }
}

describe('task predicates', () => {
  it('treats in-flight statuses as active', () => {
    expect(isActive(task('RUNNING'))).toBe(true)
    expect(isActive(task('QUEUED'))).toBe(true)
    expect(isActive(task('CANCEL_REQUESTED'))).toBe(true)
  })

  it('treats finished statuses as terminal, not active', () => {
    for (const status of ['COMPLETED', 'FAILED', 'CANCELLED'] as const) {
      expect(isTerminal(task(status))).toBe(true)
      expect(isActive(task(status))).toBe(false)
    }
  })

  it('requires review after a restart', () => {
    expect(isActive(task('RECOVERY_REQUIRED'))).toBe(false)
    expect(isTerminal(task('RECOVERY_REQUIRED'))).toBe(false)
  })
})
