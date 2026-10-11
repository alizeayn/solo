# 31 — Acceptance Criteria (Review Pass)

**Stage:** Verification
**Date:** 2026-10-10

Each request is traced to evidence. Where something could not be verified, it says
so.

---

## 1. Voice-native interaction as the top priority

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | Voice is treated as the product's foundation, not a later feature | ✅ | `services/narration.py` — a real output channel with selection, ordering, coalescing, rate limiting and barge-in, wired into the orchestrator and exposed over REST and WebSocket. Documented as the central direction in the README, `PROJECT_SPEC.md §1` and `§8`, and `docs/architecture.md` |
| 2 | The agent's activity is summarised, never narrated call by call | ✅ | Only `progress.summary`, `error`, the terminal outcome and the orchestrator summary reach `_narrate()`. `test_only_milestones_are_queued_and_delivered_in_order` asserts the delivered set |
| 3 | A newer summary replaces a stale queued one | ✅ | `test_a_newer_progress_line_supersedes_a_queued_older_one`; progress never displaces an error (`test_progress_never_displaces_an_important_line`) |
| 4 | Narration never overlaps | ✅ | One worker, one line at a time, minimum interval (`DEFAULT_MIN_INTERVAL`) |
| 5 | Interrupting drops queued lower-priority lines and keeps errors | ✅ | `test_interrupt_drops_progress_but_keeps_errors`, `test_interrupt_stops_in_flight_speech` |
| 6 | Nothing is audio-only | ✅ | Every line is published on the `narration` channel and rendered in the Voice panel whether or not speech is enabled |
| 7 | The pipeline works before audio exists | ✅ | `RecordingTransport` makes it observable and testable; `state()` reports `audio_available: false` and the UI states it in words |
| 8 | Text remains an equal fallback | ✅ | The Conversation panel keeps the full text composer and transcript; the voice channel is additive |

## 2. README

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 9 | Presents the product, not internal phase tracking | ✅ | Rewritten. No phase-status table; a short roadmap replaces it. Sections: why Solo, what it does, how it works, requirements, installation, first run, configuration, usage, security, updating, status and limitations, development, testing, structure, roadmap, contributing, docs |
| 10 | States the problem it solves and its differentiators | ✅ | "Why Solo" names the three convictions, voice-native first |
| 11 | Covers install, configuration and usage | ✅ | Quick start for native and Docker, a configuration table, and a walkthrough of the panels, agent workflow and projects |
| 12 | Describes limitations accurately | ✅ | A dedicated section listing what is **not** implemented — audio, voice input, the update compatibility gate, the absence of a sandbox, and the unverified Docker image |

## 3. Specification review

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 13 | Reviewed against the implementation; clear inconsistencies corrected; anything needing a product decision left alone | ✅ | Version raised to 0.2, retitled `Solo`, and only the parts the build settles were changed. The out-of-scope list and open product questions are untouched |
| 14 | **Theme support** — the spec described dark-only | ✅ | `§2` now requires both themes; `§5.6 Appearance` added with the full requirement (persistence, no flash, `system` option, Dockview, reduced motion). **Implemented** — see §4 below |
| 15 | **Login page** requirement added and improved | ✅ | `§5.7` added; the screen is rewritten as a two-panel view that states the product, is themed, and produces specific errors |
| 16 | **Account management** requirement added and implemented | ✅ | `§5.8` added, plus a line in `§10.1`; four endpoints and a settings pane implement it |

## 4. Theme support — verified

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 17 | Both a dark and a light theme exist | ✅ | `:root` and `:root[data-theme='light']` token blocks; light is designed rather than inverted |
| 18 | A straightforward way to switch | ✅ | `ThemeToggle` — a three-way control, compact in the header, full in Settings → Appearance |
| 19 | The preference persists | ✅ | Written to `localStorage` and to Solo's settings; `test_restores_a_stored_preference_on_mount` |
| 20 | No flash of the wrong theme | ✅ | An inline script in `index.html` applies the saved theme before first paint |
| 21 | "Follow the system" works and stays live | ✅ | A `matchMedia` listener updates on change; `resolveTheme('system')` unit-tested |
| 22 | Switching applies immediately, and survives a save failure | ✅ | `test_switches_to_light,_applies_it_and_persists_the_choice`, `test_applies_the_theme_even_when_saving_it_fails` |
| 23 | No component hard-codes a colour | ✅ | All eight literals replaced with tokens; the audit grep returns 0 (`D-27`) |
| 24 | The tiling chrome switches too | ✅ | `DockLayout` selects `themeLight`/`themeAbyss`; the `--dv-*` variables are driven by app tokens in both theme classes |

## 5. Account management — verified

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 25 | Change the username from the workspace | ✅ | `PUT /api/account/username` + the Account pane; asserted at the service and API level |
| 26 | Change the password from the workspace | ✅ | `PUT /api/account/password`; asserted end to end, including a real login with the new password afterwards |
| 27 | Replaces an installer-generated password | ✅ | The password set at first-run setup is changed through the API and the new one is used to sign in |
| 28 | Handled securely | ✅ | Current password required for both; scrypt hashing; the value is never returned; username/password validation tested (invalid names, taken names, short passwords, unchanged password) |
| 29 | Persists across restarts | ✅ | `test_new_password_survives_a_restart` builds a second container over the same data directory |
| 30 | A password change signs out other devices but not this one | ✅ | `test_changing_the_password_revokes_other_sessions_but_keeps_the_current_one`; `POST /sessions/revoke` offers the same without a password change |
| 31 | Errors are specific | ✅ | Distinct messages for a wrong password, a taken username, an invalid username, a too-short password, a mismatched confirmation |

## 6. Pi Agent naming

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 32 | No incorrect references remain | ✅ | `PyAgent`: 0 incorrect uses. The one remaining mention is in `PROJECT_SPEC.md`, stating that the name is *not* correct and does not correspond to a package used here |
| 33 | Context checked rather than blind-replaced | ✅ | Every variant enumerated and classified (report 28 §2.1). `PiAgentSettings.tsx` is a correct React filename; `pi-agent.md` is a correct path and Docker volume name; `piagent-docs` appears once as a historical folder name in an older report |
| 34 | Implementation, scripts, paths and configuration checked | ✅ | No incorrect name in code, scripts, paths or configuration. The folder is `Pi Agent Docs`; the runtime paths are `pi-runtime` and `pi/agent`; the environment keys are `PI_EXECUTABLE`, `PI_RUNTIME_DIR`, `PI_AGENT_DIR` |

## 7. Regression and honesty

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 35 | Existing behaviour is not broken | ✅ | **375 backend** tests (from 339) and **103 frontend** tests (from 82) pass. Every previous test passes unchanged except one that was corrected (`D-25`) and one replaced because its subject was replaced (`LoginView` → `AuthView`) |
| 36 | No feature is claimed without support | ✅ | Audio is reported `false` and labelled in the UI, the README and the spec. The Docker image remains marked unverified. The narration panel says "recorded and shown here; playback arrives in Phase 4" |

---

## 8. Verification matrix

| Layer | Method | Result |
|---|---|---|
| Backend unit + API | `pytest` | ✅ **375 passed**, 0 failed, 0 skipped |
| Frontend unit + component | `vitest` | ✅ **103 passed** |
| Types | `tsc --noEmit`, `strict` | ✅ 0 errors |
| Frontend build | `vite build` | ✅ 707 kB JS / 153 kB CSS |
| Simulator end-to-end | `scripts/e2e.sh` | ✅ 53/53 (run in the previous milestone; unchanged by this work) |
| Live end-to-end | `scripts/e2e-live.sh` | ✅ 39/39 (unchanged; requires a model credential) |
| Theme | unit + component tests, literal-colour audit | ✅ |
| Account | service, API and persistence tests | ✅ |
| Narration | unit tests + API + WebSocket channel | ✅ |
| Scripts / compose | `bash -n` × 6, `docker compose config` | ✅ |
| Docker image | `docker compose build` | ❌ **not executed** — no daemon access (D-08) |

**478 automated tests passing** (375 backend + 103 frontend), plus the end-to-end
suites.

---

## 9. Not verified / limitations

1. **No visual verification.** Themes, the sign-in layout and the Voice panel are
   verified by typecheck, component tests and construction — there is **no
   browser-automation suite**, so appearance at specific breakpoints and the
   absence of visual regressions are not automated. This is the weakest part of
   the verification and is worth stating plainly.
2. **No audio.** The narration pipeline is verified; playback is not implemented.
3. **The Docker image was not built** (D-08).
4. **No version-range compatibility gate** in the updater.
5. **`system` theme on a real OS switch** is covered by a `matchMedia` listener and
   unit tests, but not observed live in a browser.
6. **Account management is single-user.** Roles are reported (`owner`) but not
   enforced, since the MVP has one account.
