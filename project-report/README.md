# Project Report — Solo

Engineering report for the **Solo** voice-first AI workspace.

| | |
|---|---|
| **Project** | Solo (`alizeayn/solo`) |
| **Phase** | 1 ✅ · 1.5 (project model) ✅ · 2 (Pi Agent, Orchestrator) ✅ · 2.2 (isolated runtime, updates) ✅ · 2.3 (voice foundation, theme, accounts) ✅ · **2.4 (Orchestrator config, tiles, milestones)** ✅ |
| **Last updated** | 2026-10-11 |
| **Automated checks** | **632 passing** — 411 backend, 116 frontend, 63 simulator e2e, 42 live e2e |
| **Defects** | 36 found, 35 fixed with regression coverage, 1 environment gap |

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
