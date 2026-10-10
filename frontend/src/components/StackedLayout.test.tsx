import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../panels/ConversationPanel', () => ({
  default: () => <div>conversation-panel</div>,
}))
vi.mock('../panels/ActivityPanel', () => ({
  default: () => <div>activity-panel</div>,
}))
vi.mock('../panels/InspectorPanel', () => ({
  default: () => <div>inspector-panel</div>,
}))

import StackedLayout from './StackedLayout'

describe('StackedLayout', () => {
  it('starts on the conversation tab', () => {
    render(<StackedLayout />)
    expect(screen.getByText('conversation-panel')).toBeInTheDocument()
  })

  it('switches between panels via tabs', async () => {
    render(<StackedLayout />)

    await userEvent.click(screen.getByRole('tab', { name: 'Activity' }))
    expect(screen.getByText('activity-panel')).toBeInTheDocument()
    expect(screen.queryByText('conversation-panel')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('tab', { name: 'Inspector' }))
    expect(screen.getByText('inspector-panel')).toBeInTheDocument()
  })
})
