# Solo — project status report

| | |
|---|---|
| **Version** | 2.6.1 |
| **Date** | 2026-10-13 |
| **Scope** | Everything built to date, measured against the MVP specification |
| **Reading time** | ~15 minutes |

---

## 1. Executive summary

**Solo is feature-complete against its own MVP specification.** All twenty
acceptance criteria in `PROJECT_SPEC.md` have an implementation. The product
installs, authenticates, manages projects, drives a real coding agent, narrates
progress aloud, and updates itself in place.

**The remaining gap is not features. It is verification.**

Three things are consistently unproven, and each has an environment cause rather
than a code cause:

1. **Nothing has been verified in a browser.** There is no browser automation in
   this environment, so no layout, animation, playback or microphone behaviour has
   been observed directly — only asserted in unit tests and reasoned about.
2. **Docker has never been built.** No daemon socket access (D-08, open since
   Phase 1).
3. **Providers are intermittently out of credit.** ElevenLabs' free allowance is
   spent and no OpenCode Go key is available, so the two most recently added
   integrations have been verified at the protocol level but not end to end.

A reader should take away this: **the architecture and the feature set are
settled and tested; the outstanding risk is concentrated in the last mile —
real devices, real credentials, real containers.**

---

## 2. What Solo is meant to be

From `PROJECT_SPEC.md` §1:

> **Voice-native conversation is the primary product direction.** The user should
> be able to work with an agent by talking, with text as an equal and
> always-available fallback.

A single-user, browser-based workspace for working on a software project through
real-time voice, text and file input: open or upload a project, send a coding task
to an agent, watch meaningful progress, ask questions mid-task, and give
follow-up instructions without returning to a terminal.

Seven principles govern the build, and it is worth checking the implementation
against them because they are the part that is expensive to change later:

| Principle | Held? |
|---|---|
| Modular monolith, one origin, one port | ✅ |
| Core logic must not depend on one provider | ✅ — three providers have now been swapped through the same seams |
| Backend owns task state; panel state is never authoritative | ✅ |
| Event-driven progress, not log dumping | ✅ |
| One active modifying task per project | ✅ |
| Isolated Pi Agent, never `PATH`, never `~/.pi` | ✅ |
| Build the smallest useful thing first | ✅ — with one documented exception, D-49 |

---

## 3. What has been built

### 3.1 Platform and delivery

* Single FastAPI backend serving the REST API, the WebSocket and the built React
  app from **one origin and one port**.
* SQLite persistence for users, sessions, projects, conversations, tasks, events,
  settings and milestones.
* `install.sh` / `solo.sh` with `install · start · stop · restart · status · logs ·
  version · doctor · cert · access · update`.
* **In-place update** that backs up first, rebuilds only what changed, applies
  migrations, rolls back on failure, and preserves projects, credentials, memory
  and sessions. Verified repeatedly during this project — every release since 2.5
  was delivered through it.
* Docker and Compose files exist and are **unverified** (D-08).

### 3.2 Projects

* Create a project, **open an existing folder in place** (nothing is copied), or
  import a ZIP with extraction guards.
* A per-project `.solo/` state store holding the file tree, memory, sessions,
  milestones and configuration.
* Path safety: blocked system paths, an optional root allow-list, and a
  configurable "any readable path" mode.

### 3.3 Coding agent (Pi)

* Solo installs and owns its **own** Pi Agent under `<data>/pi-runtime`, with its
  own agent directory at `<data>/pi/agent`. The host's `pi` and `~/.pi` are never
  read or written.
* Driven over `pi --mode rpc`; Pi events are translated into a normalised event
  model.
* Provider, model, credential management, model discovery and catalog refresh are
  all available from Settings, including importing the Orchestrator's key.
* **Verified live**: a real task ran end to end producing `hello_world.py`
  (83 bytes), and `scripts/e2e-live.sh` passed 42 checks.

### 3.4 Orchestrator

The layer that decides *what the user meant* and *what to do about it*.

* Intent classification, planning, progress summarisation and project question
  answering.
* Deterministic rules router as the fallback, so a provider outage degrades
  instead of blocking.
* Evidence-backed milestones: phases advance only when real events justify them.
  There is no timer and no fabricated progress.
* Steering: a message during a running task is recorded and forwarded to the agent.
* **Two providers** (2.6.1): OpenRouter and OpenCode Go, selected by a setting. A
  provider is a descriptor, not a branch, so a third needs no frontend change.
* **Verified live**: 5/5 classifications correct with genuine per-message
  reasoning after the 2.5.1 structured-output fix.

### 3.5 Voice — the differentiator

| Capability | State |
|---|---|
| Narration selection, ordering, coalescing, barge-in, rate limiting | ✅ |
| ElevenLabs text-to-speech, real audio | ✅ **verified live** (HTTP 200, valid MP3) |
| Milestone narration in natural language | ✅ |
| Acknowledgements and file-change narration | ✅ |
| Session greeting | ✅ |
| Single unified conversation (voice + text + files) | ✅ (2.6.0) |
| Realtime speech-to-text over WebSocket, single-use token | ✅ implemented; protocol verified live |
| Batch transcription fallback | ✅ |
| Playback with autoplay recovery | ✅ — **confirmed working by ear** |

The narration design decision has aged well: **text is the channel, audio is an
enhancement.** Every narrated line reaches the UI as text whether or not it is
spoken, which is why the workspace stays useful when the voice pipeline is broken.

### 3.6 Interface

* Dark / light / follow-system theming, applied before first paint.
* Dockview tiled workspace, layout persisted and versioned (currently `v4`).
* Panels: Conversation (unified), Pi Agent Activity, Orchestrator Milestones,
  Orchestration, Write, Inspector, Project State.
* Per-panel error boundaries, so one failing tile cannot blank the workspace.
* Account management: username and password change, both requiring the current
  password, with a password change revoking other sessions.
* Phone-first CSS (2.6.0): 44px targets, safe-area insets, sticky composer,
  bottom navigation, 16px inputs to prevent iOS zoom.
* **Never verified visually.**

---

## 4. Current state in numbers

| Metric | Value |
|---|---|
| Version | **2.6.1** |
| Commits | 54 |
| Backend tests | **482 passing** |
| Frontend tests | **152 passing**, 20 files |
| Backend source | 70 files, ~15,800 lines |
| Frontend source | 38 files, ~11,300 lines |
| Project reports | 92 |
| Reference documentation | 27 files across 4 doc folders |
| Defects found / fixed | **75 / 71** |
| Defects open | **4** |

### What is verified, and how

| Area | Evidence |
|---|---|
| Pi Agent end to end | Real task, real file produced; `e2e-live.sh` 42 checks |
| Orchestrator reasoning | 5/5 live classifications with reasoning |
| ElevenLabs TTS | Live 200 + valid MP3 + full speech-to-text round trip |
| Voice playback | **Confirmed by the user** after 2.5.4 |
| Realtime STT protocol | Live handshake, accepted frame, rejected frame shape |
| OpenCode Go protocol | Live 200 model list; 400/401 error conditions reproduced |
| Update in place | Every release since 2.5 delivered through it |
| Installer, auth, themes | Automated tests; installer exercised repeatedly |

### What is not verified

| Area | Why |
|---|---|
| Any browser behaviour | No browser automation in this environment |
| Mobile layout, keyboard, safe areas | No device |
| iOS Safari microphone and autoplay policy | No iPhone; **the strictest platform** |
| Docker image | No daemon socket access (D-08) |
| Realtime speech heard end to end | ElevenLabs balance exhausted |
| A completion on OpenCode Go | No key available |

---

## 5. What is not working correctly

Four defects are open. Two are genuine product issues, two are environment.

### 5.1 D-49 — Answers are presented as completed tasks *(medium, deliberate)*

When you ask a question, the answer is stored on a `QUESTION` task that is
immediately marked **COMPLETED**. The row is a container for the reply, but the UI
presents it exactly like a coding task.

**Consequence.** Typing "hi" or "what is your model?" produces a task reading
*Completed* with no agent run. This reads as *"my task finished and nothing
happened"* — and it is literally the report that started the 2.5.1 investigation.

**Not fixed deliberately.** Correcting it changes what a task *means* in the UI and
belongs with the Activity presentation work, not a patch release.

### 5.2 Narration granularity *(low, by design)*

File-change narration coalesces, so a burst of writes reports the latest file
rather than each one. The phase-level truth still comes from milestones. This is
intentional but worth knowing: you will not hear every file.

### 5.3 D-08 — Docker build never executed *(environment)*

The Dockerfile and Compose file exist and are maintained, but no image has ever
been built. Open since Phase 1.

### 5.4 Voice input on plain HTTP *(browser constraint, not a bug)*

Browsers expose the microphone only in a secure context. Over
`http://<lan-ip>` voice input **cannot** work, regardless of what Solo does.
`./solo.sh cert` provides HTTPS and `./solo.sh access` explains the situation, but
this will surprise anyone who has not read the documentation.

### 5.5 Recurring defect class, now closed

Worth recording because it recurred five times (D-28, D-29, D-38, D-51, D-55) and
each instance was expensive:

> **A component reported itself healthy while doing none of the work.**

Examples: an orchestrator that silently fell back to rules because its model
rejected `response_format` (D-47); a voice transport that caught every synthesis
failure and returned normally, so lines with no audio were recorded as spoken
(D-51); narration published twice under one id where the second, authoritative
message was discarded — sound generated, paid for, never fetched (D-59).

The class is closed structurally: the single-configuration-source rule, per-panel
error boundaries, honest status fields, and tests that assert *values* rather than
truthiness.

---

## 6. What has not been implemented

### 6.1 Explicitly out of scope (spec §"Explicitly out of scope")

Multi-user accounts, teams, roles, billing, a SaaS control plane; a plugin
marketplace; concurrent agents on one project; long-term semantic memory or vector
search; image generation; a full IDE; microservices; automatic execution of
uploaded project scripts.

**None of these is blocked by the architecture** — the seams exist and were
exercised when a third provider was added without touching the frontend.

### 6.2 Deferred within scope

| Item | Note |
|---|---|
| Mobile responsive UI | **Implemented in 2.6.0** but never seen on a device |
| Voice input on a phone | Needs HTTPS + a real device |
| Answer rows distinguished from tasks | D-49, deferred |
| Streaming TTS (`stream-input`) | Not needed; current path is fast enough |

---

## 7. How far from the goal?

Measured against the twenty acceptance criteria in `PROJECT_SPEC.md` §11.

| # | Criterion | Implemented | Verified |
|---|---|---|---|
| 1 | Installer delivers a working app | ✅ | ✅ (Docker ❌) |
| 2 | Authentication required | ✅ | ✅ |
| 3 | Configure, test, persist provider credentials | ✅ | ✅ |
| 4 | Create or import a project safely | ✅ | ✅ |
| 5 | Voice conversation **and** text fallback | ✅ | ⚠️ output by ear; realtime input not heard |
| 6 | A code change reaches Pi RPC in the project dir | ✅ | ✅ live |
| 7 | Activity shows live events, correct terminal status | ✅ | ✅ |
| 8 | Mid-task question answered without interrupting | ✅ | ✅ (D-49 affects presentation) |
| 9 | Follow-up associated and steered | ✅ | ✅ |
| 10 | State survives restart; uncertain tasks flagged | ✅ | ✅ |
| 11 | Progress summaries visual; **voice counted complete only after overlap/interruption tested** | ✅ | ⚠️ **not tested with real audio** |
| 12 | Panel move/close does not stop the task | ✅ | ✅ |
| 13 | Secrets never in responses, logs, storage or bundle | ✅ | ✅ |
| 14 | Automated tests cover the named areas | ✅ | ✅ |
| 15 | Dark/light/system theme, no flash | ✅ | ⚠️ not observed in a browser |
| 16 | Sign-in presents the product, actionable errors | ✅ | ⚠️ not observed |
| 17 | Account management with current-password checks | ✅ | ✅ |
| 18 | Narration ordering, overlap, barge-in, honesty | ✅ | ⚠️ behaviour tested; audio not heard |
| 19 | Isolated Pi, succeeds with host `pi` removed | ✅ | ✅ |
| 20 | In-place update without loss; rollback | ✅ | ✅ |

**Score: 20 of 20 implemented. 14 fully verified, 6 partially.**

Criterion 11 is the most significant gap in spirit: it explicitly says voice
announcements count as complete only after overlap and interruption have been
tested. Those behaviours are implemented and unit-tested, but they have not been
exercised with real audio. By the specification's own standard, that item is
**not yet met**.

---

## 8. The verification debt, stated plainly

This is the honest core of the report. Each row is something that should be
confirmed and currently is not.

| # | Unverified | What it would take | Risk if wrong |
|---|---|---|---|
| 1 | Realtime voice on a real device | A phone, HTTPS, a funded key | **High** — the headline feature |
| 2 | iOS Safari microphone and autoplay | An iPhone | **High** — strictest platform |
| 3 | Mobile layout at 320–414px | A browser or device | Medium |
| 4 | Audio overlap and barge-in with real speech | A funded key | Medium — criterion 11 |
| 5 | Docker image builds and runs | Daemon access | Medium |
| 6 | OpenCode Go completion | A Go key | Low — protocol confirmed |
| 7 | Theme applied without flash | A browser | Low |
| 8 | Every visual claim in the docs | A browser | Low–medium |

**Nothing here is believed to be broken.** Each is a case where the
implementation exists, is tested at the level the environment allows, and has not
been observed doing the real thing.

That distinction matters. A status report that said "voice works" on the strength
of unit tests would repeat the mistake that D-47, D-51 and D-59 all were.

---

## 9. Recommended next steps

Ordered by risk reduced per unit of effort.

1. **Verify voice on a real phone.** `./solo.sh cert`, then open the LAN address,
   grant the microphone, and run one task. Start here: it is the headline feature,
   the least verified, and the only way to settle criterion 11.
2. **Add credits or use a free model.** `longcat-2.5-preview-free` on OpenCode Go
   is free and unlimited for a limited time, which would close the OpenCode Go
   verification at no cost.
3. **Resolve D-49.** Distinguish answer rows from coding tasks in the transcript.
   It is the one open defect a user is likely to hit.
4. **Build the Docker image** once daemon access exists, or drop the claim from the
   documentation until it can be verified.
5. **Consider browser automation** (Playwright) — the single largest structural gap
   in this project's ability to verify itself. Nearly every ⚠️ in §7 is caused by
   its absence.

---

## 10. Honest conclusion

Solo has delivered what it set out to deliver: a voice-first workspace where a
person can describe a change, watch it happen, hear about it, correct it
mid-flight, and never open a terminal. The architecture has now absorbed three
model providers and two speech directions without a rewrite — which is the clearest
evidence that the seams were drawn correctly.

What remains is not construction. It is **proof**: a phone, a funded key, and a
Docker daemon. Until those exist, a meaningful part of this project's confidence
rests on tests and reasoning rather than observation, and it should be described —
as it is here — in exactly those terms.

---

*No code was modified in producing this report.*
