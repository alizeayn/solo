# Project Report — Solo

Engineering report for the **Solo** voice-first AI workspace.

| | |
|---|---|
| **Project** | Solo (`alizeayn/solo`) |
| **Phase** | 1 ✅ · 1.5 (project model) ✅ · 2 (Pi Agent, Orchestrator) ✅ · 2.2 (isolated runtime, updates) ✅ · 2.3 (voice foundation, theme, accounts) ✅ · 2.4 (Orchestrator config, tiles, milestones) ✅ · **2.5 (voice activation)** ✅ · **2.6 (live voice, session)** ✅ · **2.7 (2.5.1)** ✅ · **2.8 (2.5.2)** ✅ · **2.9 (2.5.3)** ✅ · **2.10 (2.5.4)** ✅ · **2.11 (2.5.5)** ✅ · **2.12 (2.6.0)** ✅ · **2.13 (2.6.1)** ✅ |
| **Last updated** | 2026-10-13 (2.6.1) |
| **Automated checks** | **665 passing** — 458 backend, 131 frontend, + 23 live voice, + 76 simulator e2e |
| **Defects** | 75 found, 71 fixed with regression coverage, 4 open (D-08 Docker, D-49 answer rows, device verification, provider/ElevenLabs credentials) |

---

## Report index

### Phase 1 — Deployable shell

| # | Stage | Document |
|---|---|---|
| 01 | Planning | [scope-0001.md](01-planning/scope-0001.md) |
| 02 | Planning | [phase-plan-0002.md](01-planning/phase-plan-0002.md) |
| 03 | Implementation | [backend-0003.md](02-implementation/backend-0003.md) |
| 04 | Implementation | [frontend-0004.md](02-implementation/frontend-0004.md) |
| 05 | Implementation | [deployment-and-docs-0005.md](02-implementation/deployment-and-docs-0005.md) |
| 06 | Testing | [test-report-0006.md](03-testing/test-report-0006.md) |
| 07 | Testing | [e2e-verification-0007.md](03-testing/e2e-verification-0007.md) |
| 08 | Defects | [defect-log-0008.md](04-defects/defect-log-0008.md) |
| 09 | Verification | [acceptance-criteria-0009.md](05-verification/acceptance-criteria-0009.md) |
| 10 | Summary | [summary-0010.md](06-summary/summary-0010.md) |

### Phase 2 — Pi Agent, Orchestrator, state foundation

| # | Stage | Document |
|---|---|---|
| 17 | Planning | [phase-2-scope-0017.md](01-planning/phase-2-scope-0017.md) |
| 18 | Implementation | [pi-integration-0018.md](02-implementation/pi-integration-0018.md) |
| 19 | Implementation | [orchestrator-and-ui-0019.md](02-implementation/orchestrator-and-ui-0019.md) |
| 20 | Defects | [defect-log-0020.md](04-defects/defect-log-0020.md) |
| 21 | Verification | [acceptance-criteria-0021.md](05-verification/acceptance-criteria-0021.md) |
| 22 | Summary | [summary-0022.md](06-summary/summary-0022.md) |

### Phase 2.2 — Isolated runtime, in-place updates, workspace tiles

| # | Stage | Document |
|---|---|---|
| 23 | Planning | [isolation-and-updates-0023.md](01-planning/isolation-and-updates-0023.md) |
| 24 | Implementation | [isolated-runtime-and-updates-0024.md](02-implementation/isolated-runtime-and-updates-0024.md) |
| 25 | Defects | [defect-log-0025.md](04-defects/defect-log-0025.md) |
| 26 | Verification | [acceptance-criteria-0026.md](05-verification/acceptance-criteria-0026.md) |
| 27 | Summary | [summary-0027.md](06-summary/summary-0027.md) |

### Phase 2.3 — Voice foundation, theme system, accounts

| # | Stage | Document |
|---|---|---|
| 28 | Planning | [review-and-priorities-0028.md](01-planning/review-and-priorities-0028.md) |
| 29 | Implementation | [voice-foundation-theme-account-0029.md](02-implementation/voice-foundation-theme-account-0029.md) |
| 30 | Defects | [defect-log-0030.md](04-defects/defect-log-0030.md) |
| 31 | Verification | [acceptance-criteria-0031.md](05-verification/acceptance-criteria-0031.md) |
| 32 | Summary | [summary-0032.md](06-summary/summary-0032.md) |

### Project status — as at 2.6.1

| # | Stage | Document |
|---|---|---|
| 93 | Status report | [project-status-0093.md](06-summary/project-status-0093.md) |

A full assessment of everything built to date measured against the MVP
specification: what works, what does not, what is deferred, and the distance to
the goal. Read this first if you are new to the project.

### Phase 2.13 — 2.6.1: OpenCode Go as a second Orchestrator provider

| # | Stage | Document |
|---|---|---|
| 87 | Planning | [orchestrator-providers-0087.md](01-planning/orchestrator-providers-0087.md) |
| 88 | Implementation | [orchestrator-providers-0088.md](02-implementation/orchestrator-providers-0088.md) |
| 89 | Testing | [orchestrator-providers-0089.md](03-testing/orchestrator-providers-0089.md) |
| 90 | Defects | [defect-log-0090.md](04-defects/defect-log-0090.md) |
| 91 | Verification | [acceptance-criteria-0091.md](05-verification/acceptance-criteria-0091.md) |
| 92 | Summary | [summary-0092.md](06-summary/summary-0092.md) |

### Phase 2.12 — 2.6.0: unified conversation, realtime voice, mobile

| # | Stage | Document |
|---|---|---|
| 81 | Planning | [unified-voice-conversation-0081.md](01-planning/unified-voice-conversation-0081.md) |
| 82 | Implementation | [unified-voice-conversation-0082.md](02-implementation/unified-voice-conversation-0082.md) |
| 83 | Testing | [unified-voice-conversation-0083.md](03-testing/unified-voice-conversation-0083.md) |
| 84 | Defects | [defect-log-0084.md](04-defects/defect-log-0084.md) |
| 85 | Verification | [acceptance-criteria-0085.md](05-verification/acceptance-criteria-0085.md) |
| 86 | Summary | [summary-0086.md](06-summary/summary-0086.md) |

### Phase 2.11 — 2.5.5: voice-first conversation

| # | Stage | Document |
|---|---|---|
| 75 | Planning | [voice-first-conversation-0075.md](01-planning/voice-first-conversation-0075.md) |
| 76 | Implementation | [voice-first-conversation-0076.md](02-implementation/voice-first-conversation-0076.md) |
| 77 | Testing | [voice-first-conversation-0077.md](03-testing/voice-first-conversation-0077.md) |
| 78 | Defects | [defect-log-0078.md](04-defects/defect-log-0078.md) |
| 79 | Verification | [acceptance-criteria-0079.md](05-verification/acceptance-criteria-0079.md) |
| 80 | Summary | [summary-0080.md](06-summary/summary-0080.md) |

### Phase 2.10 — 2.5.4: narration delivery, mobile and visible degradation

| # | Stage | Document |
|---|---|---|
| 69 | Planning | [narration-delivery-0069.md](01-planning/narration-delivery-0069.md) |
| 70 | Implementation | [narration-delivery-0070.md](02-implementation/narration-delivery-0070.md) |
| 71 | Testing | [narration-delivery-0071.md](03-testing/narration-delivery-0071.md) |
| 72 | Defects | [defect-log-0072.md](04-defects/defect-log-0072.md) |
| 73 | Verification | [acceptance-criteria-0073.md](05-verification/acceptance-criteria-0073.md) |
| 74 | Summary | [summary-0074.md](06-summary/summary-0074.md) |

### Phase 2.9 — 2.5.3: narration playback and stream recovery

| # | Stage | Document |
|---|---|---|
| 63 | Planning | [audible-narration-0063.md](01-planning/audible-narration-0063.md) |
| 64 | Implementation | [audible-narration-0064.md](02-implementation/audible-narration-0064.md) |
| 65 | Testing | [audible-narration-0065.md](03-testing/audible-narration-0065.md) |
| 66 | Defects | [defect-log-0066.md](04-defects/defect-log-0066.md) |
| 67 | Verification | [acceptance-criteria-0067.md](05-verification/acceptance-criteria-0067.md) |
| 68 | Summary | [summary-0068.md](06-summary/summary-0068.md) |

### Phase 2.8 — 2.5.2: ElevenLabs integration and spoken milestones

| # | Stage | Document |
|---|---|---|
| 57 | Planning | [voice-pipeline-and-natural-milestones-0057.md](01-planning/voice-pipeline-and-natural-milestones-0057.md) |
| 58 | Implementation | [voice-pipeline-0058.md](02-implementation/voice-pipeline-0058.md) |
| 59 | Testing | [voice-pipeline-0059.md](03-testing/voice-pipeline-0059.md) |
| 60 | Defects | [defect-log-0060.md](04-defects/defect-log-0060.md) |
| 61 | Verification | [acceptance-criteria-0061.md](05-verification/acceptance-criteria-0061.md) |
| 62 | Summary | [summary-0062.md](06-summary/summary-0062.md) |

### Phase 2.7 — 2.5.1: Orchestrator/Pi defects, network access and TLS

| # | Stage | Document |
|---|---|---|
| 51 | Planning | [network-mobile-and-agent-fixes-0051.md](01-planning/network-mobile-and-agent-fixes-0051.md) |
| 52 | Implementation | [network-mobile-and-agent-0052.md](02-implementation/network-mobile-and-agent-0052.md) |
| 53 | Testing | [agent-and-network-0053.md](03-testing/agent-and-network-0053.md) |
| 54 | Defects | [defect-log-0054.md](04-defects/defect-log-0054.md) |
| 55 | Verification | [acceptance-criteria-0055.md](05-verification/acceptance-criteria-0055.md) |
| 56 | Summary | [summary-0056.md](06-summary/summary-0056.md) |

### Phase 2.6 — Live verification, regression fix, voice session

| # | Stage | Document |
|---|---|---|
| 45 | Planning | [live-verification-and-voice-session-0045.md](01-planning/live-verification-and-voice-session-0045.md) |
| 46 | Implementation | [live-voice-and-session-0046.md](02-implementation/live-voice-and-session-0046.md) |
| 47 | Testing | [live-voice-and-workspace-0047.md](03-testing/live-voice-and-workspace-0047.md) |
| 48 | Defects | [defect-log-0048.md](04-defects/defect-log-0048.md) |
| 49 | Verification | [acceptance-criteria-0049.md](05-verification/acceptance-criteria-0049.md) |
| 50 | Summary | [summary-0050.md](06-summary/summary-0050.md) |

### Phase 2.5 — Voice activation

| # | Stage | Document |
|---|---|---|
| 39 | Planning | [voice-activation-0039.md](01-planning/voice-activation-0039.md) |
| 40 | Implementation | [elevenlabs-voice-0040.md](02-implementation/elevenlabs-voice-0040.md) |
| 41 | Testing | [voice-loop-test-0041.md](03-testing/voice-loop-test-0041.md) |
| 42 | Defects | [defect-log-0042.md](04-defects/defect-log-0042.md) |
| 43 | Verification | [acceptance-criteria-0043.md](05-verification/acceptance-criteria-0043.md) |
| 44 | Summary | [summary-0044.md](06-summary/summary-0044.md) |

### Phase 2.4 — Orchestrator config, workspace tiles, milestones

| # | Stage | Document |
|---|---|---|
| 33 | Planning | [workspace-tiles-and-milestones-0033.md](01-planning/workspace-tiles-and-milestones-0033.md) |
| 34 | Implementation | [orchestrator-config-and-tiles-0034.md](02-implementation/orchestrator-config-and-tiles-0034.md) |
| 35 | Testing | [e2e-workspace-flow-0035.md](03-testing/e2e-workspace-flow-0035.md) |
| 36 | Defects | [defect-log-0036.md](04-defects/defect-log-0036.md) |
| 37 | Verification | [acceptance-criteria-0037.md](05-verification/acceptance-criteria-0037.md) |
| 38 | Summary | [summary-0038.md](06-summary/summary-0038.md) |

### Phase 1.5 — Solo, project model, public readiness

| # | Stage | Document |
|---|---|---|
| 11 | Planning | [phase-1.5-scope-0011.md](01-planning/phase-1.5-scope-0011.md) |
| 12 | Implementation | [project-model-0012.md](02-implementation/project-model-0012.md) |
| 13 | Implementation | [installation-and-public-readiness-0013.md](02-implementation/installation-and-public-readiness-0013.md) |
| 14 | Defects | [defect-log-0014.md](04-defects/defect-log-0014.md) |
| 15 | Verification | [acceptance-criteria-0015.md](05-verification/acceptance-criteria-0015.md) |
| 16 | Summary | [summary-0016.md](06-summary/summary-0016.md) |

---

## Structure

```
project-report/
├── README.md                    this index
├── 01-planning/                 scope, phase plans, environment audit
├── 02-implementation/           what was built, per subsystem
├── 03-testing/                  test inventory, coverage, e2e evidence
├── 04-defects/                  every defect found, with root cause
├── 05-verification/             acceptance criteria, traced to evidence
└── 06-summary/                  outcomes, metrics, risks, next phase
```

---

## Change log

| Phase | Date | Summary | Checks | Defects |
|---|---|---|---|---|
| 1 | 2026-10-10 | Deployable shell: auth, settings, Dockview UI, task/event pipeline, Docker, docs | 171 (123 BE · 22 FE · 26 e2e) | D-01…D-08 |
| 1.5 | 2026-10-10 | Renamed to **Solo**; Create/Open/Import project model; `.solo` state store with state tree, memory, sessions, per-project config; native one-command install; public-readiness audit | 286 (194 BE · 39 FE · 53 e2e) | D-09…D-12 |
| 2 | 2026-10-10 | **Pi Agent over RPC** (real file changes verified end to end), Pyright verification, OpenRouter Orchestrator (intent, planning, summaries), prioritised dependency-aware queue, full Settings-UI configuration for both models, tabbed settings + Plan panel | 382 (288 BE · 68 FE · 26 live e2e) + 53 simulator e2e | D-13…D-16 |
| 2.2 | 2026-10-10 | **Solo's own isolated Pi Agent** (never the host's, never `PATH`), **in-place updates** with fingerprint-driven rebuilds, backups and rollback, versioning and a migration runner, Writing panel + file upload, animated voice preview | 513 (339 BE · 82 FE · 39 live e2e) + 53 simulator e2e | D-17…D-23 |
| 2.13 | 2026-10-13 | **2.6.1.** Added **OpenCode Go** as a second Orchestrator provider without touching OpenRouter. The Orchestrator had been wired to OpenRouter *by name* — key and model read directly in five places. A provider is now a **descriptor** (`orchestrator_providers.py`): base URL, key/model settings, extra headers, account endpoint. One transport serves both; it gained only `extra_headers`, carrying 2.5.1's structured-output fallback along for free. **The docs' "should" is a "must"**: `x-opencode-session` is mandatory and omitting it is a 400 on every call — found by live testing, not reading. Three defects the second provider exposed: `verify_key` is OpenRouter-only (`GET /key`), the model was always written to `openrouter_model`, and status masked OpenRouter's key for every provider. New `OpenCode Go Docs/` (5 files) records the verified protocol, errors and 39-model catalogue. **Not verified:** a real completion — no Go key was available. | 482 BE · 152 FE | D-72…D-75 |
| 2.12 | 2026-10-13 | **2.6.0.** Merged `Conversation`, `Voice` and `Write` into **one surface**: typed messages and spoken narration interleaved chronologically, with voice, attachments and speech output in the composer. `VoiceChannel` deleted; the `voice` tile/tab removed and the Dockview key bumped `v3→v4`. Voice is now **real-time** (`useRealtimeVoice`: AudioWorklet → 16 kHz PCM → ElevenLabs Realtime with a **single-use token**, so the API key stays server-side); only `committed_transcript` dispatches, partials are shown but never acted on, and batch remains the fallback. **The documentation would have broken it silently** — the API reference says `inputAudioChunk`, the live protocol uses `message_type`; sending `type` yields `input_error` and a session that connects and transcribes nothing. Caught by testing the live service, now pinned by a test. Microphone input now survives Orchestrator/Pi failures and a failed turn is not lost. Mobile was the desktop layout shrunk (1 media query, 0 phone breakpoints, sub-44px targets): now 44px targets, safe areas, sticky composer, bottom nav. **Not verified by ear** — balance is 0. | 470 BE · 152 FE | D-66…D-71 |
| 2.11 | 2026-10-13 | **2.5.5.** Made the voice exchange conversational. The agent only spoke on milestones, so a session opened in **silence**, a request produced **no spoken acknowledgement**, and file changes were **inaudible** — one-sided, because `_narrate` forwarded only `progress.summary` and `error`. `assistant.message` and `file.changed` are now narrated, the acknowledgement is rewritten for speech (`"Got it. I'll get started on this: create a login page."`) at IMPORTANT priority so it is never superseded or dropped mid-utterance, and file changes are phrased by verb (created/updated/removed) and coalesce under load. A session now opens with a contextual greeting through **`POST /api/voice/say`** — the same narration pipeline, not a second mechanism. Steering and per-project context already existed and needed no change. **Not verified by ear:** the ElevenLabs balance is exhausted again (10000/10000). | 468 BE · 150 FE | D-62…D-65 |
| 2.10 | 2026-10-13 | **2.5.4.** Found the reason audio was generated and never heard. The mobile log showed **24 successful TTS calls and 0 requests for `/api/voice/audio`**. A narration line is published **twice under one id** (queued `spoken:false`, then delivered `spoken:true`) and the provider merged narration with `appendUnique`, which **discards an id it has already seen** — so the delivered message was thrown away, every line stayed unspoken, and the player (which only plays lines with audio) fetched nothing. The milestone channel in the same handler used an upsert with a comment describing exactly this case. Fixed with `upsertNarration`, proven on the wire and covered by a test that fails on the old code. Also: narration missed during a disconnect is now recovered, and a rate-limited Orchestrator is reported in the workspace tile with the provider's own message. **Not verified:** hearing it — needs a browser and a funded key. | 147 FE | D-59…D-61 |
| 2.9 | 2026-10-13 | **2.5.3.** Credit was consumed but nothing was heard. The provider log showed **82 requests, all HTTP 200, 13 successful TTS calls**; Solo's log showed `/api/voice/audio` requested **zero times**. Playback defaulted to **off**, so Solo synthesised, paid and stored audio the client never fetched. Now on by default and persisted; an autoplay refusal is recovered on the next gesture and shown as `tap anywhere to enable sound`. Two further bugs surfaced: a refused line was marked *seen* and could never play, and the audio element was created in an effect declared *after* the code that needed it. The perceived connection drops were 30-of-32 explained by restarts/page loads; the real defect was that nothing refetched after a drop — `WorkspaceProvider` now resyncs on reconnect. **Not verified:** hearing a milestone — the stored key reports 0 credits. | 139 FE | D-55…D-58 |
| 2.8 | 2026-10-13 | **2.5.2.** Fixed the voice pipeline. The ElevenLabs account has **0 credits** (`401 quota_exceeded`) — an account state, not a bug — but Solo **hid the failure at four points**: the transport swallowed every synthesis error and returned normally, `audio_available` was an OR of "configured" and "working", the transport flag meant "has delivered once", and failed lines were counted as *spoken*. All four now report the truth, with the real API message reaching the UI. **Milestones had never been sent to the voice channel at all** (`_narrate` allowed only progress/error); they are now spoken with natural phrasing, rewordable by the model and never invented. Narration stays **text-first**, so a typed task still produces a conversational account of the work with no audio. Not verified: hearing real speech — impossible at 0 credits. | 465 BE · 133 FE | D-51…D-54 |
| 2.7 | 2026-10-12 | **2.5.1.** Fixed the reported "task shows Completed but nothing happens": the **Orchestrator had never made a single routing decision** — the configured model rejects `response_format` with a bare 400 while advertising structured output, so every `classify()` returned `None` and silently fell back to rules. `complete_json` now retries once without it (400 only) and describes required keys in prose. Pi Agent now reports an unusable model instead of running with a phantom `unknown`. Confirmed LAN access already worked (0.0.0.0, LAN IP 200); added TLS support, `./solo.sh cert` and `./solo.sh access` so phone voice can obtain a secure context. Mobile-responsive UI and cross-device testing remain **outstanding**. | 463 BE · 131 FE | D-47…D-50 |
| 2.6 | 2026-10-12 | **Live ElevenLabs verification with a real (scoped) key**: models read, speech synthesised, audio served by Solo, transcription round-tripped. Fixed a **workspace regression** — `/api/voice/state` made a blocking third-party call and the Voice panel polled it on every narration line, starving every other tile — and made one tile unable to break the rest. Voice interaction redesigned as a **continuous session** (one click to start, one to end, no holding), with barge-in by voice. ElevenLabs docs renamed to `ElevenLabs Docs/` and one earlier model claim corrected against the live API. | 458 BE · 131 FE · 23 live · 76 e2e | D-42…D-46 |
| 2.5 | 2026-10-11 | **Voice activated**: speech input feeds the existing dispatch path (browser → Scribe → `/api/projects/{id}/messages`), and speech output speaks milestones through ElevenLabs TTS at the transport seam `NarrationService` already defined — so the Orchestrator, Pi Agent and milestone pipeline are unchanged. Live model and voice discovery from the account (no hardcoded catalog), a real Voice settings pane, barge-in, and a player. The Agents Platform is deliberately not used. Verified API notes in `ElevenLabs Docs/`. | 664 (456 BE · 132 FE · 76 e2e) | D-37…D-41 |
| 2.4 | 2026-10-11 | **Orchestrator configuration flow fixed** (key saved but no model yet no longer reports a missing key; the enable toggle now reaches the runtime); **workspace tiles** for every registered panel, including an evidence-derived **Orchestrator Milestone** tile with progressive reveal, and a voice tile prepared for ElevenLabs; the **state flow** from Pi Agent events to structured milestones, published live and persisted to `.solo/state/milestones.json`; canonical **commit policy** | 632 (411 BE · 116 FE · 63 simulator e2e · 42 live e2e) | D-28…D-36 |
| 2.3 | 2026-10-10 | **Voice foundation**: a narration pipeline (selection, ordering, coalescing, rate limiting, barge-in) with a pluggable transport; **theme system** (dark / light / system, no flash, Dockview); **account management** (username and password from the workspace); professional README; specification reviewed and corrected | 478 (375 BE · 103 FE) + 39 live e2e + 53 simulator e2e | D-24…D-27 |

---

## Headline result

**Phase 1** delivered a secure, deployable, single-origin application whose whole
critical path was exercised end to end: sign in → create or import a project →
ask a question → start a coding task → watch live normalised events → steer the
running task → reach a terminal status → survive a restart.

**Phase 2.3** made the product's stated direction real. Voice is now an *output
channel with policy* — what is worth saying, in what order, what to drop, and when
to stop — built and tested before audio exists, so Phase 4 attaches a transport and
nothing else changes. Solo also gained a dark/light/auto theme, account management
from the workspace, and a README written for a visitor rather than the author.

**Phase 2.2** removed Solo's last dependency on the machine it runs on. It now
installs, owns and invokes **its own Pi Agent**, with its own configuration
directory, so the desktop Pi installation is never read, written or executed —
verified by running a full coding task with the global `pi` deleted from `PATH`.
It also became maintainable in place: `./solo --update` rebuilds only what
changed, backs up first, and rolls back rather than leaving a partial state.

**Phase 2** made Solo do real work. A request typed into Chat is classified and
planned by an OpenRouter model (with deterministic rules as a permanent
fallback), handed to a long-lived **Pi Agent** process whose working directory is
the opened project, executed for real — `hello_world.py` on disk with the
requested contents — streamed back as normalised events, verified by **Pyright**,
summarised, and recorded in the project's own state store. Both models are
configured entirely from the Settings UI, with validation states that never claim
more than was actually verified.

**Phase 1.5** redefined what a *project* is. It is now a directory on disk with a
`.solo/` state store inside it, so a project carries its own configuration,
memory, sessions, task history and structured state tree — and can be opened
where it already lives, on any machine, without copying anything. Installation
became a single command that runs on a machine without Docker, and the repository
was audited for public release (no secrets, no generated artefacts, no API key
required to install or explore).

The coding agent is still a **deliberate simulator**: it emits realistic, ordered
events and modifies nothing. Every place that is not yet real is labelled as such
in the UI and the docs — including the disabled voice control, which carries an
explicit "Phase 4" note rather than pretending to work.

### Open items

| Item | Where |
|---|---|
| Confirm the Open Project path-policy default (`ALLOW_ANY_PROJECT_PATH=true`) | [11 §4](01-planning/phase-1.5-scope-0011.md) |
| Docker image build not verified in this environment (D-08) | [14 §D-08](04-defects/defect-log-0008.md#d-08--docker-image-build-could-not-be-executed-in-this-environment) |
| Docker image still not built — no daemon access (D-08) | [20 §D-08](04-defects/defect-log-0008.md) |
| No version-range compatibility gate in the updater | [26 §6](05-verification/acceptance-criteria-0026.md) |
| Live test used `opencode-go`; OpenRouter returned 402 (no credit) | [22 §7](06-summary/summary-0022.md) |
| Voice input and audio playback not implemented — the narration pipeline is ready | [32 §5](06-summary/summary-0032.md) |
| No automated visual verification (no browser-driven tests) | [31 §9](05-verification/acceptance-criteria-0031.md) |
