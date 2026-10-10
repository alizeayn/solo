# 04 — Frontend Implementation

**Stage:** Implementation
**Date:** 2026-10-10
**Location:** `frontend/`

---

## 1. Statistics

| Metric | Value |
|---|---|
| Source files | 20 TypeScript/TSX modules |
| Test files | 5 |
| Tests | 22 passing |
| TypeScript errors | 0 (`tsc --noEmit`, `strict: true`) |
| Production build | 644.84 kB JS (166.92 kB gzip), 139.47 kB CSS (13.10 kB gzip) |
| Runtime dependencies | 4 (`react`, `react-dom`, `dockview`, `dockview-react`) |

---

## 2. Deliberate dependency minimalism

Four runtime dependencies total. Notably absent and why:

- **No router.** Three mutually exclusive views (setup, login, workspace) plus
  two overlays are application state, not URL structure. Adding a router would
  create routes to maintain for no user-visible benefit.
- **No state library.** One `WorkspaceProvider` context is sufficient for a
  single-user workspace; Redux-class machinery would be ceremony.
- **No icon package.** Event glyphs come from a small mapping in
  `utils/format.ts`, keeping the bundle small.
- **No CSS framework.** A single `styles.css` with custom properties keeps the
  palette tunable in one place.

---

## 3. Module map

| Area | Files |
|---|---|
| Entry | `main.tsx`, `App.tsx` |
| API | `api/client.ts` — typed, error-normalising fetch wrapper |
| State | `state/WorkspaceProvider.tsx` — the single source of client state |
| Hooks | `hooks/useWebSocket.ts`, `hooks/useMediaQuery.ts` |
| Views | `components/LoginView.tsx`, `SetupView.tsx`, `WorkspaceView.tsx` |
| Chrome | `components/Header.tsx`, `StatusBadge.tsx`, `Toasts.tsx` |
| Settings | `components/SettingsView.tsx`, `ProjectDialog.tsx` |
| Layout | `components/DockLayout.tsx`, `StackedLayout.tsx` |
| Panels | `panels/ConversationPanel.tsx`, `ActivityPanel.tsx`, `InspectorPanel.tsx` |
| Utilities | `types.ts`, `utils/format.ts` |

---

## 4. The three panels

### A — Conversation (primary)

Voice start/stop control with listening/speaking/connecting indicators, live
transcript, text input as an equal fallback, attachment control, and a context
indicator naming the project and the task a message targets.

**Honest-by-default:** the voice and attachment controls are rendered
**disabled** with explicit "Phase 4" / "Phase 5" labels and explanatory
tooltips. A control that looks active but does nothing would be worse than no
control. The context chip shows the real selected/active task, so the user
always knows where a message will land.

Enter sends, Shift+Enter inserts a newline. A failed send restores the draft
rather than discarding the user's words.

### B — Coding Agent Activity (monitor)

Current task and status, high-level activity timeline, changed-file list, test
results, and concise progress summaries.

Derived from normalized events only. Raw protocol output and internal
chain-of-thought are never shown — the panel surfaces *observable tool activity*
and user-facing summaries. Changed files are derived from `file.changed` events
on the client, so the panel stays correct as new events stream in without an
extra round trip.

### C — Inspector (initially passive)

An empty state when nothing is selected, then task history and details for the
selected task: id, type, status, timestamps, changed files, result and error.
It is intentionally generic so a later phase can render a file excerpt or a
generated diagram here without restructuring the layout.

---

## 5. Dockview behaviour

- Three panels registered in a `components` map; panel ids
  (`conversation`, `activity`, `inspector`) are stable so a restored layout
  rebinds correctly.
- Default layout: Conversation on the left, Activity to the right, Inspector
  below the Conversation.
- Layout persisted under `solo.layout.v1` on every `onDidLayoutChange`.
- **A corrupt or incompatible stored layout can never trap the user**: loading
  validates by attempting `fromJSON` inside a `try/catch`; on failure the key is
  cleared and the default layout is rebuilt.
- **Panel state is independent of task state.** Moving, resizing, tabbing or
  hiding a panel cannot affect a running task, because panels render from the
  provider and never drive lifecycle.
- Below 900 px the tiled layout is replaced by `StackedLayout`, a tab bar over
  the same three panel components — the same code paths, not a second
  implementation.

Theme: `themeAbyss` from dockview, with its `--dv-*` custom properties retuned
to the application palette so the tab strip matches the surrounding chrome.

---

## 6. Live event handling

`useWebSocket` opens `wss?://<host>/api/ws`, authenticating via the session
cookie, and reconnects with exponential backoff (500 ms → 10 s cap).

Three rules keep it correct:

1. **Selection lives in refs.** The WebSocket handler reads the current task and
   project through refs, so changing the selected task does *not* tear down and
   rebuild the socket.
2. **Deduplicate on append.** Events and messages are appended only if their id
   is not already present, because REST history and live frames can overlap.
3. **The client never guesses.** After sending a message the client re-fetches
   the transcript instead of optimistically fabricating the user's own message
   (which the server does not broadcast).

Channel handling: `task` upserts into the task list, `event` appends when it
belongs to the selected task, `message` appends to the transcript.

---

## 7. Settings UI

Sections for OpenRouter, ElevenLabs, the coding agent (Pi) and preferences.

- Secrets are **write-only**: the input shows a masked status
  (`configured (****cdef)`) and is blank; leaving it blank keeps the current key.
  A "Remove stored key" action deletes it.
- Each provider has a real **Test connection** button that calls
  `POST /api/settings/test/{provider}` and renders the actual result, with the
  detail line shown only when the provider supplies one.
- Only the fields the user actually changed are sent, so a save cannot wipe a
  stored secret.
- The Pi section reports the detected version and states plainly that the active
  backend is the Phase 1 simulator that modifies nothing.

---

## 8. Design system

A restrained dark palette defined once as custom properties: a near-black
background, three surface elevations, one accent, and success/danger/warning
tones each with a soft variant. Components consume tokens only — retuning the
palette is a single-block edit.

Reusable primitives: `.btn` (+ `--primary`, `--danger`, `--ghost`, `--sm`),
`.pill` (+ five tones), `.field`/`.input`, `.panel` (`__bar`, `__body`,
`__footer`), `.empty`, `.bubble`, `.timeline`, `.list`, `.card`, `.overlay`,
`.toast`, `.stacked`.

Accessibility basics: labels bound to inputs, `role="tab"`/`aria-selected` on
the stacked tabs, `role="alert"` on errors, `aria-modal` on overlays,
`aria-hidden` on decorative glyphs, and a keyboard-operable send action.

---

## 9. Frontend tests

| File | Tests | Covers |
|---|---|---|
| `utils/format.test.ts` | 8 | Status labels/tones, event labels/glyphs, relative time (including future timestamps), truncation |
| `types.test.ts` | 3 | `isActive` / `isTerminal` classification matrix |
| `components/LoginView.test.tsx` | 3 | Render, successful submit, rejection path with error and no callback |
| `components/StackedLayout.test.tsx` | 2 | Default tab, switching between panels |
| `panels/ActivityPanel.test.tsx` | 6 | Empty state, summary/metrics, changed files from events, timeline order, error surfacing, active-task fallback |

The API module is mocked in component tests, so no test performs network I/O.
