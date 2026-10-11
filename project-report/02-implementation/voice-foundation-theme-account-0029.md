# 29 — Voice Foundation, Theme System, Account Management

**Stage:** Implementation
**Date:** 2026-10-10

---

## 1. Voice foundation (`services/narration.py`)

The architectural answer to "voice-native is the top priority", built so the hard
parts are done and tested **before** audio exists.

```
agent activity ──► NarrationService ──► NarrationTransport ──► (Phase 4: audio)
                        │
                        ├── selection      milestones only, never tool calls
                        ├── ordering       (priority, sequence)
                        ├── coalescing     a newer progress line supersedes an older one
                        ├── rate limiting  one line at a time, minimum interval
                        ├── barge-in       stop speech, drop lower-priority lines
                        └── observability  every line on the WebSocket, always visible
```

| Type | Role |
|---|---|
| `NarrationLine` | One thing to say: text, kind, priority, task/project, spoken timestamp |
| `Priority` | `CRITICAL` (errors, decisions) · `IMPORTANT` (outcome, summary) · `PROGRESS` |
| `NarrationTransport` | Protocol with `deliver()` and `stop()` — the only thing Phase 4 replaces |
| `RecordingTransport` | Default: records instead of speaking, so the pipeline is observable |
| `NarrationService` | Selection, ordering, coalescing, rate limiting, barge-in, state |

**Behaviour worth naming:**

- **Never narrates every operation.** Only `progress.summary`, `error`, the
  terminal outcome and the orchestrator's summary reach the channel. Tool calls
  never do — they remain visible in the Activity panel, which is where detail
  belongs.
- **A newer progress line supersedes a queued older one.** Saying "found the
  module" *after* "the tests pass" would be nonsense; the queue is filtered rather
  than replayed.
- **Progress never displaces an error.** Coalescing only removes lines of equal or
  lower priority.
- **Barge-in yields completely.** `interrupt()` stops in-flight speech, drops
  queued progress, keeps critical lines, and refuses new progress while the user is
  speaking. `resume()` reopens the channel.
- **A failing transport is contained.** A missing audio device logs a warning and
  the worker continues; the visual channel is unaffected.
- **Honest state.** `state()` reports `audio_available: false` while the transport
  is the recorder, and the UI says so in words.

**Wiring.** `OrchestratorService._narrate()` is called from `_emit()`, so every
event passes one gate that decides whether it is worth saying. Nothing else needs
to know about narration.

**Endpoints and channels.** `GET /api/voice/state`, `GET /api/voice/history`,
`POST /api/voice/interrupt`, `POST /api/voice/resume`; a `narration` WebSocket
channel carries each line when queued and again when delivered, and a `voice`
channel carries barge-in notices.

**UI.** A first-class **Voice** panel (Dockview and the stacked layout) showing the
animated orb, the current state, barge-in controls, and the recent lines with their
kind and whether they were delivered — plus the honest note that playback arrives
later. The conversation composer keeps its own always-visible voice control, so the
primary panel stays voice-first.

---

## 2. Theme system

| Piece | File | Responsibility |
|---|---|---|
| Tokens | `styles.css` | One palette per theme under `:root` and `:root[data-theme='light']`; every component consumes only these |
| Logic | `hooks/useTheme.ts` | Resolve `dark`/`light`/`system` → an effective theme; apply `data-theme`; persist |
| Context | `state/ThemeProvider.tsx` | One owner, so the header, settings and Dockview agree |
| Control | `components/ThemeToggle.tsx` | A three-way segmented control, compact in the header, full in settings |
| No-flash | `index.html` | A small inline script applies the saved theme **before first paint** |

Details that make it correct rather than merely present:

- **Light is designed, not inverted.** Surfaces stay warm-neutral, the accent
  darkens so it remains legible on white, and the "soft" tones become tints rather
  than glows.
- **`system` is a real option.** A `matchMedia` listener keeps it live, so a laptop
  switching appearance at dusk follows without a reload.
- **The theme applies even if saving it fails.** The visual change is local and
  immediate; the server write is best effort.
- **Dockview switches with everything else.** `DockLayout` selects `themeLight` or
  `themeAbyss` explicitly, and the `--dv-*` variables are driven by the app tokens
  in **both** theme classes.
- **`localStorage` is a cache, not a source of truth.** The authoritative value is
  Solo's setting; the cache exists only to beat the first paint.
- **Reduced motion is respected** by the voice indicator, and `color-scheme` drives
  native form controls per theme.

Eight literal colours that only worked in the dark theme were replaced with tokens
(see D-27).

---

## 3. Account management

### Backend

| Module | Addition |
|---|---|
| `services/account_service.py` | **New** — describe, change username, change password, revoke other sessions |
| `repositories/sessions.py` | `delete_for_user(except_token_hash=…)`, `count_for_user(…)` |
| `api/account.py` | **New** — four endpoints |
| `api/auth.py`, `deps.py` | unchanged; the existing session cookie is reused |

**Both changes require the current password.** This is the deliberate part: the
caller already holds a valid session, but a session proves the browser signed in at
some point — it does not prove the person at the keyboard owns the account. This
account can run code and edit files, so the confirmation matters.

Other rules enforced and tested:

| Rule | Why |
|---|---|
| Username validated: 3–64 chars, `A-Za-z0-9` plus `._-`, must start alphanumeric | Prevents an ambiguous or unusable identity |
| A username already in use is rejected | Explicit error rather than a unique-constraint traceback |
| Password at least 8 characters and different from the current one | Rejects the trivial cases before hashing |
| The new password is hashed with scrypt | Consistent with first-run setup; nothing is stored in clear |
| **Every other session is revoked**, the current one is kept | A password change ends access on other devices without throwing the user out of the work in front of them |
| `POST /sessions/revoke` | The same outcome without changing the password |

### Frontend

**Settings → Account** shows the username, role, creation date and signed-in
session count, then two forms: change username and change password (with
confirmation). Errors are specific — wrong password, taken username, mismatched
confirmation — and a successful password change explains that other devices were
signed out.

---

## 4. Sign-in and first-run screens

`components/AuthView.tsx` replaces the previous `LoginView` and `SetupView` (both
deleted; the old test was replaced by `AuthView.test.tsx`), because the two screens
had drifted into near-duplicates.

A two-panel layout: the form on the right, and on the left what the product is.

- States the product's three differentiators: voice-native conversation, the real
  isolated Pi Agent, and state that stays on your machine.
- Shows the running version and the active coding-agent backend, so a user can see
  what they are signing into.
- Themed with the same tokens, with the appearance control available before
  signing in.
- First-run setup explains *why* an account exists (the app runs code) and states
  the password policy before submission.
- Specific, actionable errors: wrong credentials, mismatched confirmation, and a
  too-short password are distinct messages.
- Collapses to a single column below 860 px.

---

## 5. Files changed

**Added (11):**
`backend/app/services/{narration,account_service}.py`,
`backend/app/api/{account,voice}.py`,
`backend/tests/test_account_and_voice.py`,
`frontend/src/{hooks/useTheme.ts,state/ThemeProvider.tsx}`,
`frontend/src/components/{ThemeToggle,AuthView,AccountSettings,VoiceChannel}.tsx`
(+ their tests),
`frontend/src/components/{AuthView,AccountSettings,ThemeToggle}.test.tsx`.

**Removed (3):** `frontend/src/components/{LoginView,SetupView}.tsx` and
`LoginView.test.tsx`.

**Modified (~25):** `container.py`, `domain.py`, `schemas.py`, `main.py`,
`services/{settings_service,orchestrator}.py`,
`repositories/sessions.py`, `frontend/src/{types.ts,styles.css,index.html}`,
`api/client.ts`, `state/WorkspaceProvider.tsx`,
components `{Header,SettingsView,DockLayout,StackedLayout}.tsx`,
`README.md`, `PROJECT_SPEC.md`, `docs/{architecture,api,development}.md`,
`tests/test_checks_and_api_pi.py`.
