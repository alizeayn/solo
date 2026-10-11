# 32 — Summary: Product Direction, Presentation and Accounts

**Stage:** Summary
**Date:** 2026-10-10
**Milestone:** Voice foundation, theme system, account management, README
**Status:** ✅ Complete; verified except for visual appearance, which has no automated check

---

## 1. What this pass was

Not a feature phase. A review that asked one question of the project — *does it
look and behave like what it says it is?* — and fixed the places where the answer
was no.

Six requests, three of which turned out to be real implementation work:

| Request | Kind | Outcome |
|---|---|---|
| Voice-native interaction is the top priority | Direction | **Architecture**: a narration pipeline, built and tested before audio exists |
| Rewrite the README professionally | Documentation | Rewritten; no phase tracking, product-first |
| Review the spec; theme, login, account management | Spec + **3 features** | Spec updated; all three implemented |
| Correct Pi Agent naming | Correctness | One real correction; nothing had leaked into code or paths |
| Implement and verify | Process | 478 tests passing |
| Report | Documentation | Documents 28–32 |

---

## 2. The one that mattered: voice

The request was emphatic that voice is the product's biggest advantage and should
be a foundation rather than a feature. The honest state before this pass was that
the specification said so, the UI had an animated indicator, and **nothing in the
code expressed voice as an output channel**.

Rather than wait for audio, the hard parts were built now:

```
agent activity ──► select ──► order ──► coalesce ──► rate limit ──► yield on barge-in
                                                                        │
                                                          Phase 4 attaches a transport
```

Every one of those decisions is testable with a transport that records instead of
speaks, so the behaviour is verified today and Phase 4 replaces one class. The
consequences that will matter most later:

- **Only milestones are spoken.** Tool calls never are.
- **A newer summary replaces a stale one** rather than replaying "found the module"
  after "the tests pass".
- **Barge-in is complete**: stop speech, drop queued progress, keep errors, refuse
  new progress while the user speaks.
- **Nothing is audio-only.** Every line is visible, always.

The Voice panel is a first-class panel, not a settings toggle, and it reports
`audio_available: false` in words rather than implying playback.

---

## 3. What else changed

**Theme system.** A dark and a light theme, plus "follow the system", switchable
from the header or settings, persisted locally and in the account, applied before
first paint so there is no flash, and driving the Dockview chrome. The light theme
is designed rather than inverted, and the eight hard-coded colours that would have
survived a naive implementation were found by an audit grep before they could
become a bug report.

**Account management.** Username and password changes from the workspace, so the
password an installer generates can be replaced without touching a terminal. Both
require the current password — a session proves a browser signed in, not who is at
the keyboard, and this account runs code. A password change signs out every other
device and keeps the one you are using.

**Sign-in screens.** Rewritten as a two-panel view that states what the product is,
shows the running version and agent backend, is themed, and produces specific
errors for each failure mode.

**README.** Rewritten for a visitor: why Solo exists, what it does, how it works,
how to install and configure it, and an accurate limitations section. The roadmap
is forward-looking; the phase-status table is gone.

**Specification.** Corrected rather than rewritten — version 0.2, retitled `Solo`,
the Pi Agent naming resolved to its verified answer, and new requirements for
appearance, sign-in screens and account management that the build now meets.

---

## 4. Verification

| Suite | Before | After |
|---|---|---|
| Backend | 339 | **375** |
| Frontend | 82 | **103** |
| Simulator end-to-end | 53 | 53 |
| Live end-to-end | 39 | 39 |

**478 automated tests passing**, plus the end-to-end suites.

**Four defects**, and they are more interesting than the count suggests:

| Id | What | How it was found |
|---|---|---|
| D-24 | `interrupt()` counted dropped lines but never recorded them | a test asserting the *counter*, not just the return value |
| D-25 | A test asserted on ambient `PATH` and silently covered nothing; **three more were quietly skipping** | a failure in a neighbouring case |
| D-26 | Two fields shared the label "Current password" | an ambiguous query in a test |
| D-27 | Eight colours that only worked in the dark theme | a one-line grep, before any screenshot |

**D-27 was found by inspection and D-25 by accident**, which is the useful lesson
of this round: the theme audit was a grep, not a review, and it found all eight
problems in seconds; and the pyright tests had been reporting "skipped" for two
milestones without anyone noticing. A passing suite can hide more than a failing
one.

---

## 5. Weakest point, stated plainly

**There is no automated visual verification.** The theme, the sign-in layout and
the Voice panel are verified by type checking, component tests, and construction —
not by a browser. That means:

- the light theme's *contrast and taste* are unverified;
- layout at specific breakpoints is unverified;
- a visual regression would not be caught.

Everything else in this pass has an executable check. This does not, and pretending
otherwise would be the least useful thing this report could do. A browser-driven
test layer (Playwright) is the natural next investment, and it becomes more
valuable as the voice interface adds interactive surface.

---

## 6. Documentation created or updated

| Path | Contents |
|---|---|
| `README.md` | **Rewritten.** Public-facing: why Solo, capabilities, architecture, install, configuration, usage, security, updating, status and limitations, development, testing, structure, roadmap, contributing |
| `PROJECT_SPEC.md` | **Updated.** Version 0.2, retitled `Solo`; voice-native vision in §1; theme in §2 and §5.6; sign-in screens §5.7; account management §5.8 and §10.1; Pi Agent naming corrected; §8 reframed as the primary channel with the narration requirements; acceptance criteria extended to 20 |
| `docs/architecture.md` | **Updated.** New modules in the map; a new §11 Appearance covering theme tokens, resolution, no-flash and Dockview switching |
| `docs/api.md` | **Updated.** Account endpoints, the voice endpoints with their honest `audio_available` field, and the `narration` / `voice` WebSocket channels |
| `docs/development.md` | **Updated.** New test files in the inventory |
| `project-report/01-planning/review-and-priorities-0028.md` | **New.** What was reviewed, what the review found (with the commands), how the work was ordered, the decisions taken, what was deferred |
| `project-report/02-implementation/voice-foundation-theme-account-0029.md` | **New.** The narration pipeline, the theme system, account management, the sign-in screens, and an exact file list |
| `project-report/04-defects/defect-log-0030.md` | **New.** D-24 … D-27 with root cause, fix and lesson |
| `project-report/05-verification/acceptance-criteria-0031.md` | **New.** 36 requirements traced to evidence, the verification matrix, and the unverified list |
| `project-report/06-summary/summary-0032.md` | **New.** This document |
| `project-report/README.md` | **Updated.** Index and change log for milestone 2.3 |

---

## 7. What is next

In priority order, consistent with the direction:

1. **Audio.** Attach an ElevenLabs transport to the narration pipeline. Nothing
   else changes — the selection, ordering and barge-in behaviour are already
   decided and tested.
2. **Speech input**, so the conversation is genuinely two-way.
3. **A browser-driven test layer**, which closes the gap in §5 and starts paying
   for itself the moment the voice interface has interactive surface.
4. **Deeper reasoning** — retrieval-backed project questions and re-planning that
   consumes the mid-task instructions the orchestrator already records.

---

## 8. Conclusion

The review found the project in better shape than its documentation suggested and
in worse shape than its tests implied. The naming was clean; the theme, accounts
and voice foundation were genuinely missing. Three of the six requests were
implementation work, not documentation, and treating them as such was the whole
job.

The most valuable change is not visible in a screenshot. Voice is now an *output
channel with policy* — what is worth saying, in what order, what to drop, and when
to stop — rather than an indicator on a button. When audio arrives, the part that
is actually hard will already be built, tested, and reasoned about.

The most useful thing this pass produced, though, may be the defect that was
already green: three tests skipping silently while the suite reported success. That
is worth more than any of the features, because it changes what the green tick
means.
