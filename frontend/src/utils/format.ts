/** Small presentation helpers shared by panels and the header. */

import type { TaskStatus } from '../types'

/** Human-readable label for a task status. */
export function statusLabel(status: TaskStatus): string {
  switch (status) {
    case 'QUEUED':
      return 'Queued'
    case 'RUNNING':
      return 'Running'
    case 'WAITING_FOR_INPUT':
      return 'Waiting for input'
    case 'PAUSE_REQUESTED':
      return 'Pausing'
    case 'PAUSED':
      return 'Paused'
    case 'CANCEL_REQUESTED':
      return 'Cancelling'
    case 'CANCELLED':
      return 'Cancelled'
    case 'COMPLETED':
      return 'Completed'
    case 'FAILED':
      return 'Failed'
    case 'RECOVERY_REQUIRED':
      return 'Needs review'
    default:
      return String(status)
  }
}

/** Tone used for status pills; maps to a CSS class suffix. */
export function statusTone(
  status: TaskStatus,
): 'neutral' | 'active' | 'success' | 'danger' | 'warning' {
  switch (status) {
    case 'QUEUED':
    case 'PAUSED':
      return 'neutral'
    case 'RUNNING':
    case 'CANCEL_REQUESTED':
    case 'PAUSE_REQUESTED':
    case 'WAITING_FOR_INPUT':
      return 'active'
    case 'COMPLETED':
      return 'success'
    case 'FAILED':
      return 'danger'
    case 'CANCELLED':
    case 'RECOVERY_REQUIRED':
      return 'warning'
    default:
      return 'neutral'
  }
}

/** Short, human label for a normalised event type. */
export function eventLabel(type: string): string {
  switch (type) {
    case 'run.started':
      return 'Started'
    case 'run.finished':
      return 'Finished'
    case 'tool.started':
      return 'Tool'
    case 'tool.finished':
      return 'Tool done'
    case 'tool.updated':
      return 'Tool update'
    case 'file.changed':
      return 'File changed'
    case 'test.result':
      return 'Tests'
    case 'progress.summary':
      return 'Progress'
    case 'task.created':
      return 'Task created'
    case 'task.status_changed':
      return 'Status'
    case 'message.received':
      return 'Message'
    case 'assistant.message':
      return 'Assistant'
    case 'error':
      return 'Error'
    default:
      return type
  }
}

/** Font-agnostic glyph for an event type (avoids an icon dependency). */
export function eventGlyph(type: string): string {
  switch (type) {
    case 'run.started':
      return '▶'
    case 'run.finished':
      return '✔'
    case 'tool.started':
    case 'tool.updated':
      return '⚙'
    case 'tool.finished':
      return '⚙'
    case 'file.changed':
      return '✎'
    case 'test.result':
      return '✓'
    case 'progress.summary':
      return '→'
    case 'task.status_changed':
      return '◆'
    case 'error':
      return '!'
    case 'message.received':
      return '↩'
    case 'assistant.message':
      return '✦'
    default:
      return '•'
  }
}

/** Compact relative time such as "just now" or "3m ago". */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const then = new Date(iso)
  const seconds = Math.max(0, Math.round((now.getTime() - then.getTime()) / 1000))
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return then.toLocaleDateString()
}

/** Absolute clock time for tooltips and precise reading. */
export function clockTime(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleTimeString()
}

/** Truncate a string on a word boundary where practical. */
export function truncate(text: string, max = 80): string {
  if (text.length <= max) return text
  return `${text.slice(0, max - 1).trimEnd()}…`
}
