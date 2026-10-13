/** Stacked tab layout used on narrow screens instead of tiled panels. */

import { useState } from 'react'

import ActivityPanel from '../panels/ActivityPanel'
import ConversationPanel from '../panels/ConversationPanel'
import InspectorPanel from '../panels/InspectorPanel'
import MilestonePanel from '../panels/MilestonePanel'
import WritePanel from '../panels/WritePanel'

type TabId = 'conversation' | 'activity' | 'milestones' | 'write' | 'inspector'

const TABS: { id: TabId; label: string }[] = [
  { id: 'conversation', label: 'Conversation' },
  { id: 'activity', label: 'Activity' },
  { id: 'milestones', label: 'Milestones' },
  { id: 'write', label: 'Write' },
  { id: 'inspector', label: 'Inspector' },
]

export default function StackedLayout() {
  const [tab, setTab] = useState<TabId>('conversation')

  return (
    <div className="stacked">
      <div className="stacked__tabs" role="tablist">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={`stacked__tab ${tab === item.id ? 'stacked__tab--active' : ''}`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="stacked__content">
        {tab === 'conversation' && <ConversationPanel />}
        {tab === 'activity' && <ActivityPanel />}
        {tab === 'milestones' && <MilestonePanel />}
        {tab === 'write' && <WritePanel />}
        {tab === 'inspector' && <InspectorPanel />}
      </div>
    </div>
  )
}
