/**
 * Tiled workspace built with Dockview.
 *
 * Layout is persisted per browser in local storage. Invalid or stale layout
 * JSON is discarded and the default three-panel layout is restored, so a bad
 * stored layout can never leave the user with an unusable screen.
 */

import { useCallback, useRef } from 'react'
import {
  DockviewReact,
  themeAbyss,
  themeLight,
  type DockviewApi,
  type DockviewReadyEvent,
  type IDockviewPanelProps,
  type SerializedDockview,
} from 'dockview-react'

import { useThemeContext } from '../state/ThemeProvider'
import ActivityPanel from '../panels/ActivityPanel'
import ConversationPanel from '../panels/ConversationPanel'
import InspectorPanel from '../panels/InspectorPanel'
import VoiceChannel from './VoiceChannel'
import WritePanel from '../panels/WritePanel'

const LAYOUT_STORAGE_KEY = 'solo.layout.v1'

const components: Record<string, React.FunctionComponent<IDockviewPanelProps>> = {
  conversation: ConversationPanel,
  activity: ActivityPanel,
  voice: VoiceChannel,
  write: WritePanel,
  inspector: InspectorPanel,
}

function loadLayout(): SerializedDockview | null {
  try {
    const raw = window.localStorage.getItem(LAYOUT_STORAGE_KEY)
    return raw ? (JSON.parse(raw) as SerializedDockview) : null
  } catch {
    return null
  }
}

function saveLayout(api: DockviewApi) {
  try {
    window.localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(api.toJSON()))
  } catch {
    /* storage may be unavailable (private mode); layout persistence is optional */
  }
}

function clearLayout() {
  try {
    window.localStorage.removeItem(LAYOUT_STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

function addDefaultLayout(api: DockviewApi) {
  const conversation = api.addPanel({
    id: 'conversation',
    component: 'conversation',
    title: 'Conversation',
  })
  api.addPanel({
    id: 'activity',
    component: 'activity',
    title: 'Coding Agent Activity',
    position: { referencePanel: conversation.id, direction: 'right' },
  })
  api.addPanel({
    id: 'write',
    component: 'write',
    title: 'Write',
    position: { referencePanel: conversation.id, direction: 'below' },
  })
  api.addPanel({
    id: 'voice',
    component: 'voice',
    title: 'Voice',
    position: { referencePanel: 'activity', direction: 'below' },
  })
  api.addPanel({
    id: 'inspector',
    component: 'inspector',
    title: 'Inspector',
    position: { referencePanel: 'voice', direction: 'within' },
  })
}

export default function DockLayout() {
  const apiRef = useRef<DockviewApi | null>(null)
  const { resolved } = useThemeContext()

  const onReady = useCallback((event: DockviewReadyEvent) => {
    const api = event.api
    apiRef.current = api

    const stored = loadLayout()
    let restored = false
    if (stored) {
      try {
        api.fromJSON(stored)
        restored = true
      } catch {
        // Incompatible or corrupt layout: fall back to the default.
        clearLayout()
      }
    }
    if (!restored) addDefaultLayout(api)
    api.onDidLayoutChange(() => saveLayout(api))
  }, [])

  return (
    <DockviewReact
      // Theming is explicit rather than inferred, so the tiling chrome always
      // matches the rest of the workspace.
      theme={resolved === 'light' ? themeLight : themeAbyss}
      components={components}
      onReady={onReady}
    />
  )
}
