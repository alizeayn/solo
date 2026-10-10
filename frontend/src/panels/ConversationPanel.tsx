/**
 * Panel A — Conversation.
 *
 * Primary interaction surface: transcript plus a text composer. Voice is an
 * additional input channel and is wired in Phase 4; the control is rendered
 * disabled with an explicit note so the UI never implies untested capability.
 */

import { useEffect, useRef, useState, type KeyboardEvent } from 'react'

import { useWorkspace } from '../state/WorkspaceProvider'
import { clockTime, truncate } from '../utils/format'

export default function ConversationPanel() {
  const {
    project,
    messages,
    selectedTask,
    activeTask,
    sendMessage,
    busy,
    cancelTask,
  } = useWorkspace()

  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const transcriptRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const node = transcriptRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messages.length])

  const disabled = sending || busy || project === null

  async function submit() {
    const text = draft.trim()
    if (!text || project === null) return
    setDraft('')
    setSending(true)
    try {
      await sendMessage(text)
    } catch {
      // Restore the draft so a failed send never loses the user's words.
      setDraft(text)
    } finally {
      setSending(false)
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void submit()
    }
  }

  const target = selectedTask ?? activeTask

  return (
    <div className="panel">
      <div className="panel__bar">
        <span className="panel__bar-title">Conversation</span>
        <span className="header__spacer" />
        {activeTask && (
          <button
            type="button"
            className="btn btn--danger btn--sm"
            onClick={() => void cancelTask(activeTask.id)}
          >
            Cancel active task
          </button>
        )}
      </div>

      <div className="panel__body panel__body--flush" ref={transcriptRef}>
        {messages.length === 0 ? (
          <div className="empty">
            <div className="empty__glyph">✦</div>
            <div className="empty__title">Start the conversation</div>
            <div className="empty__text">
              Ask a question about the project, or describe a change you want
              made. Follow-up messages are associated with the running task.
            </div>
          </div>
        ) : (
          <div className="transcript">
            {messages.map((message) => (
              <article key={message.id} className={`bubble bubble--${message.role}`}>
                <div className="bubble__meta">
                  <span>{message.role === 'assistant' ? 'Assistant' : message.role}</span>
                  <span>·</span>
                  <span title={clockTime(message.created_at)}>
                    {clockTime(message.created_at)}
                  </span>
                </div>
                {message.content}
              </article>
            ))}
          </div>
        )}
      </div>

      <div className="panel__footer">
        <div className="composer">
          <div className="composer__row">
            <textarea
              className="composer__input"
              placeholder={
                project === null
                  ? 'Select a project to begin'
                  : 'Ask a question or describe a change…  (Enter to send, Shift+Enter for a new line)'
              }
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={onKeyDown}
              disabled={disabled}
              rows={2}
              aria-label="Message"
            />
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void submit()}
              disabled={disabled || draft.trim().length === 0}
            >
              {sending ? 'Sending…' : 'Send'}
            </button>
          </div>

          <div className="composer__hint">
            <span className="context-chip" title={target?.instruction}>
              {project ? `Project: ${project.name}` : 'No project'}
              {target ? ` · Task: ${truncate(target.instruction, 44)}` : ''}
            </span>
            <span className="header__group">
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                disabled
                title="Live voice conversations are implemented in Phase 4 (ElevenLabs)."
              >
                🎙 Voice — Phase 4
              </button>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                disabled
                title="File attachments are implemented in Phase 5."
              >
                📎 Attach — Phase 5
              </button>
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
