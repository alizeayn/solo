# 28 — Review, Findings and Priorities

**Stage:** Planning
**Date:** 2026-10-10
**Milestone:** Product direction, public presentation, appearances and accounts

---

## 1. Purpose of this review

A maintenance pass on the project rather than a feature phase: confirm the stated
direction is reflected in the code and the documentation, fix the parts that had
drifted, and fill two gaps the implementation had left.

Six items were requested. They are of different kinds, so they were triaged rather
than treated as one list.

| # | Request | Kind | Priority |
|---|---|---|---|
| 1 | Voice-native interaction must remain the top priority | Direction | **Highest** — it constrains everything else |
| 2 | Rewrite the README to professional open-source standards | Documentation | High — it is the project's front door |
| 3 | Review and update `PROJECT_SPEC.md`; add theme support, login polish, account management | Spec + **implementation** | High — two of the three are real features |
| 4 | Correct incorrect references to Pi Agent | Correctness | Medium — small, but it is the product's name |
| 5 | Implement and verify | Process | — |
| 6 | Update the project report | Documentation | — |

---

## 2. What the review found

### 2.1 Naming: nearly clean, one real problem

A systematic search for every plausible variant:

| Variant | Occurrences | Verdict |
|---|---|---|
| `PyAgent` | 2 | **1 real** — the specification's caution that the tool must not be an unrelated package called "PyAgent". The verification it asked for was completed in Phase 2; the phrasing still read as though it were outstanding |
| `PiAgent` | 19 | Mostly `PiAgentSettings.tsx` and its test — a legitimate React filename (PascalCase), not prose |
| `pi-agent` | 5 | Legitimate: the `docs/pi-agent.md` path and a Docker volume name in Pi's own upstream documentation |
| `piagent-docs` | 1 | A historical folder name in an old report; the folder was renamed to `Pi Agent Docs` in Phase 2 |

**Nothing incorrect had leaked into code, scripts, paths or configuration.** The
only user-facing correction needed is the specification's wording, which now
records the verified outcome instead of an open instruction.

### 2.2 Theme: absent, and the specification assumed a single theme

```
$ grep -n "data-theme" frontend/src/styles.css frontend/index.html
(no matches)

$ sed -n '/^:root/,/^}/p' frontend/src/styles.css
:root { --bg: #0a0d13; … color-scheme: dark; }
```

The specification itself said *"A polished, responsive **dark-themed** browser
UI"*, so the implementation matched the spec — but the request is for both themes,
which makes this a specification change as much as an implementation one.

Also found while assessing the work:

```
$ grep -cE "background: #[0-9a-fA-F]{3,6}|color: #[0-9a-fA-F]{3,6}" frontend/src/styles.css
8
```

Eight literal colours outside the token block. Harmless in a dark-only UI;
**guaranteed** to look wrong in a light one. This is the class of defect a theme
change exposes, and it is cheaper to find by inspection than by screenshot.

### 2.3 Account management: missing entirely

```
$ grep -n "change.*password\|update.*username" backend/app/api/auth.py
(no matches)
```

No endpoint, no service method, no UI. The installer generates a password and
there was no way to replace it from the workspace — which is precisely the gap the
request describes.

### 2.4 Voice: the right idea, not yet an architecture

The request is explicit that voice-native interaction is the product's biggest
advantage and should be a foundation rather than a later feature.

Three things were true at once:

1. the specification already made voice a first-class requirement (§8);
2. the UI had an animated voice indicator, disabled and labelled;
3. **nothing in the code expressed voice as an output channel** — no queue, no
   prioritisation, no barge-in, no notion of what is worth saying.

The indicator was honest, but it was decoration. The gap was architectural.

### 2.5 Login page and README

The sign-in screen was a centred card with a heading and two fields — functional,
generic, and not describing the product. The README led with a phase-status table:
accurate for the author, wrong for a visitor, who needs to know what the project
*is* before it tells them what is finished.

---

## 3. How the work was ordered

Sequenced so that each step depends only on what precedes it:

```
1. Voice foundation        the stated top priority, and the most architectural
2. Theme system            independent; touches every component
3. Account management      independent; backend + settings UI
4. Sign-in screens         consumes the theme and states the product direction
5. README rewrite          can only be written once 1–4 exist
6. Specification update    records the decisions 1–5 settled
7. Verification + report
```

Voice came first deliberately. It is the only item that changes the shape of the
system, and writing the README before the architecture would have meant describing
a direction that did not yet exist in code.

---

## 4. Design decisions taken

| Decision | Choice | Rationale |
|---|---|---|
| What "voice foundation" means **without audio** | A narration service: selection, ordering, coalescing, rate limiting, barge-in, pluggable transport | These are the hard parts and they are testable today. Phase 4 supplies a transport and nothing else changes |
| Default transport | `RecordingTransport` | Makes the pipeline observable and testable without pretending speech exists |
| What gets narrated | Milestones only: progress summaries, errors, outcome, final summary | The request is explicit: never every tool call |
| Theme preference storage | `localStorage` **and** Solo's settings | The cache exists so the theme can apply before first paint; the server copy so it follows the account. The cache is never the source of truth |
| Theme model | Three preferences, not a two-state toggle | "Follow the system" is a distinct and commonly wanted choice |
| Theme implementation | CSS custom properties per theme on `<html data-theme>` | One attribute switches everything; no component knows the theme |
| Account change authorisation | Current password required for both operations | A session proves a browser signed in, not who is at the keyboard — and this account runs code |
| Password change | Revoke every other session, keep the current one | Ends access elsewhere without throwing the user out of their work |
| Pi Agent naming in the spec | Record the verified outcome, keep one accurate mention of the wrong name | The clarification is only useful if it says the wrong name was checked and rejected |

---

## 5. Explicitly deferred

- **Audio.** No transport, no ElevenLabs session, no microphone. The pipeline is
  ready for it and reports `audio_available: false` until then.
- **A full README pass.** The request notes that further feedback will follow; this
  is a first professional version, not the final word.
- **Spec sections needing a product decision.** The out-of-scope list, the
  acceptance criteria for voice, and the multi-agent question are untouched beyond
  what the current build settles.
- **Renaming `PiAgentSettings.tsx`.** It is a correct React component name, and
  renaming it would churn imports for no benefit.
