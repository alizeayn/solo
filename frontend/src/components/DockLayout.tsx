/**
 * Tiled workspace, built with Dockview.
 *
 * Two things this file has to get right:
 *
 * 1. **A saved layout must not hide new tiles.** The stored layout is keyed by a
 *    version, and after restoring one the workspace checks that every registered
 *    panel is present, adding any that are missing. Without that, a user who had
 *    ever opened the app kept their original arrangement forever and tiles added
 *    later never appeared — which is exactly what happened before this was fixed.
 * 2. **A corrupt layout must never trap the user.** Invalid JSON, or JSON from an
 *    incompatible version, is discarded and the default layout is rebuilt.
 *
 * Panel visibility is independent of task lifecycle: rearranging tiles cannot
 * affect the work in progress.
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
import PanelErrorBoundary from './PanelErrorBoundary'
import MilestonePanel from '../panels/MilestonePanel'
import WritePanel from '../panels/WritePanel'

/**
 * Bump when the set of panels changes. `v1` held only Conversation, Activity and
 * Inspector; restoring it would silently omit every later tile.
 */
const LAYOUT_STORAGE_KEY = 'solo.layout.v4'

/**
 * Wrap every tile in an error boundary.
 *
 * Dockview renders all panels into one React tree, so an error thrown by a
 * single tile would otherwise unmount the entire workspace — the shell would
 * stay on screen and every panel would go blank at once, which is impossible to
 * diagnose from the UI. The boundary keeps a failure to its own tile and names
 * it.
 */
function bounded(
  name: string,
  Component: React.FunctionComponent<IDockviewPanelProps>,
): React.FunctionComponent<IDockviewPanelProps> {
  function Bounded(props: IDockviewPanelProps) {
    return (
      <PanelErrorBoundary name={name}>
        <Component {...props} />
      </PanelErrorBoundary>
    )
  }
  Bounded.displayName = `Bounded(${name})`
  return Bounded
}

const components: Record<string, React.FunctionComponent<IDockviewPanelProps>> = {
  conversation: bounded('Conversation', ConversationPanel),
  activity: bounded('Pi Agent Activity', ActivityPanel),
  milestones: bounded('Orchestrator Milestones', MilestonePanel),
  write: bounded('Write', WritePanel),
  inspector: bounded('Inspector', InspectorPanel),
}

interface PanelSpec {
  id: string
  component: string
  title: string
  position?: { referencePanel: string; direction: 'right' | 'below' | 'within' }
}

/**
 * The workspace tiles, in the order they should be introduced.
 *
 * `milestones` is deliberately adjacent to `activity`: one shows what the agent
 * is doing, the other what it means. They answer different questions and are
 * meant to be read together.
 */
const PANEL_SPECS: PanelSpec[] = [
  { id: 'conversation', component: 'conversation', title: 'Conversation' },
  {
    id: 'activity',
    component: 'activity',
    title: 'Pi Agent Activity',
    position: { referencePanel: 'conversation', direction: 'right' },
  },
  {
    id: 'milestones',
    component: 'milestones',
    title: 'Orchestrator Milestones',
    position: { referencePanel: 'activity', direction: 'below' },
  },
  {
    id: 'write',
    component: 'write',
    title: 'Write',
    position: { referencePanel: 'conversation', direction: 'below' },
  },
  {
    id: 'inspector',
    component: 'inspector',
    title: 'Inspector',
    position: { referencePanel: 'write', direction: 'within' },
  },
]

const DEFAULT_PANELS = PANEL_SPECS

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
    /* storage may be unavailable (private mode); persistence is optional */
  }
}

function clearLayout() {
  try {
    window.localStorage.removeItem(LAYOUT_STORAGE_KEY)
  } catch {
    /* ignore */
  }
  // Drop earlier versions too, so they cannot be picked up again.
  for (const stale of ['solo.layout.v1', 'solo.layout.v2', 'solo.layout.v3']) {
    try {
      window.localStorage.removeItem(stale)
    } catch {
      /* ignore */
    }
  }
}

function addDefaultLayout(api: DockviewApi) {
  for (const spec of DEFAULT_PANELS) {
    api.addPanel({
      id: spec.id,
      component: spec.component,
      title: spec.title,
      position: spec.position,
    })
  }
}

/**
 * Add any registered panel that a restored layout does not contain.
 *
 * Returns the ids that had to be added, so the caller can log or inform the user.
 * The user's existing arrangement is untouched: new tiles are introduced without
 * rearranging anything they have already positioned.
 */
function ensureAllPanels(api: DockviewApi): string[] {
  const added: string[] = []
  for (const spec of PANEL_SPECS) {
    if (api.getPanel(spec.id)) continue
    const reference = spec.position?.referencePanel
    const anchor =
      reference && api.getPanel(reference) ? reference : api.panels[0]?.id ?? null
    api.addPanel({
      id: spec.id,
      component: spec.component,
      title: spec.title,
      position:
        anchor && anchor !== spec.id
          ? { referencePanel: anchor, direction: spec.position?.direction ?? 'within' }
          : undefined,
    })
    added.push(spec.id)
  }
  return added
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

    if (!restored) {
      addDefaultLayout(api)
    } else {
      // Never let a saved layout hide a tile that this version provides.
      ensureAllPanels(api)
    }

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

export { PANEL_SPECS, ensureAllPanels, LAYOUT_STORAGE_KEY }
