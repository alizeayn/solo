# Project Report — Solo

Engineering report for the **Solo** voice-first AI workspace.

| | |
|---|---|
| **Project** | Solo (`alizeayn/solo`) |
| **Phase** | 1 ✅ · 1.5 (project model & public readiness) ✅ · **2 (Pi Agent, Orchestrator, state foundation)** ✅ |
| **Last updated** | 2026-10-10 |
| **Automated checks** | **382 passing** — 288 backend, 68 frontend, 26 live end-to-end (+53 simulator e2e) |
| **Backend coverage** | 86 % |
| **Defects** | 16 found, 15 fixed with regression coverage, 1 environment gap |

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

---

## Headline result

**Phase 1** delivered a secure, deployable, single-origin application whose whole
critical path was exercised end to end: sign in → create or import a project →
ask a question → start a coding task → watch live normalised events → steer the
running task → reach a terminal status → survive a restart.

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
| Live test used `opencode-go`; OpenRouter returned 402 (no credit) | [22 §7](06-summary/summary-0022.md) |
| Voice (Phase 4) and spoken progress (Phase 5) not implemented, by instruction | [22 §8](06-summary/summary-0022.md) |
