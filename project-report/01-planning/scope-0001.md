# 01 — Scope

**Stage:** Planning
**Date:** 2026-10-10

---

## 1. Objective

Build the **smallest useful, polished, deployable MVP** of a single-user,
browser-based AI workspace for working on a software project through real-time
voice, text and file input — testable on a Linux server and extendable without
rewriting its core.

Source of truth for requirements: `PROJECT_SPEC.md` (v0.1) in the repository
root.

---

## 2. Deliverable for this engagement

**Phase 1 only — the deployable shell.** Explicitly in scope:

1. FastAPI backend + React/TypeScript frontend served from one public origin.
2. Persistent SQLite storage behind repositories.
3. Single-user authentication (hashed password, HttpOnly cookie).
4. Settings UI with encrypted credential storage and real connection tests.
5. Create / upload / list / open projects inside an app-managed directory.
6. A Dockview tiled workspace with three panels and persisted layout.
7. A complete task lifecycle: create → run → events → terminal status,
   persisted and broadcast live over WebSocket.
8. Intent routing: question vs. steer vs. stop vs. new task.
9. A coding-agent **adapter contract** plus a deterministic simulator.
10. Docker Compose, `install.sh`, backup/restore, and documentation.
11. Automated tests plus a real-server end-to-end smoke test.

Explicitly **deferred** to later phases (with the seams built now):

| Deferred | Phase | Seam already in place |
|---|---|---|
| Real Pi RPC subprocess | 2 | `CodingAgentAdapter` protocol, `build_adapter` switch |
| OpenRouter routing/Q&A/summaries | 3 | `IntentRouter` contract, `ContextSnapshot`, `build_snapshot` |
| ElevenLabs live voice | 4 | Settings fields, `voice_enabled`, disabled UI control |
| Proactive speech queue | 5 | `progress_speech_enabled`, `progress.summary` events |

Out of scope for the whole MVP (unchanged from the spec): multi-user accounts,
teams/billing, plugin marketplace, vector memory, concurrent writers per
project, and a source-code editor.

---

## 3. Constraints and ground rules

| Constraint | How it was honoured |
|---|---|
| Do not guess package names, RPC commands or model IDs | The Pi tool was confirmed as the installed `pi` CLI v1.1.0; authoritative local docs (`docs/rpc.md`, `rpc-commands.md`, `cli-integration.md`) were located and referenced. No protocol is invented. |
| Provider-specific details stay in adapters | `PiCodingAgentAdapter`, `OpenRouterAdapter`, `ElevenLabs*Adapter` are the only places provider protocol may live. Phase 1 ships the mock adapter behind that contract. |
| Backend owns task state | Panel visibility cannot affect a task; the UI mirrors, never owns. |
| Never expose an unauthenticated UI | All routes except `/api/health` and first-run `/api/auth/*` require a session; the WebSocket checks the cookie before accepting. |
| No secrets in images, logs, responses or browser storage | Encrypted at rest; masked in responses; registered with a log redactor; never in local storage; `.dockerignore` excludes `.env` and data. |
| Idempotent, non-destructive installer | `install.sh` detects an existing volume and leaves credentials and data untouched. |

---

## 4. Environment audit

Performed before writing code.

| Tool | Found | Requirement | Verdict |
|---|---|---|---|
| Python | 3.12.3 | 3.12+ | ✅ |
| Node | 24.16.0 | 20+ (Vite 8) | ✅ |
| npm | 11.13.0 | – | ✅ |
| Docker | 29.8.0 | for deployment | ⚠️ client OK; daemon socket not accessible to this user |
| Docker Compose | v5.5.1 | v2+ | ✅ |
| `pi` CLI | 1.1.0 | Phase 2 | ✅ present |
| git | 2.43.0 | – | ✅ |
| ffmpeg | 6.1.1 | Phase 4/5 | ✅ present |

**Key finding.** The spec asked to verify that "Pi Coding Agent" is the intended
tool and not an unrelated package called "PyAgent". Confirmed: it is the
installed **`pi` CLI v1.1.0**, and the exact authoritative documentation the
spec references exists locally under
`…/pi-coding-agent/docs/` (`rpc.md`, `rpc-commands.md`, `cli-integration.md`).
Phase 2 will build against those, not against guesses.

**Blocking finding.** `docker info` fails: `/var/run/docker.sock` is owned by
`root:docker` and this user is not in the `docker` group; `sudo` requires an
interactive password. Consequence recorded as **D-08** in the defect log — the
image build could not be executed here, so the Dockerfile's constituent steps
were verified natively instead.

---

## 5. Repository baseline

The repository existed but was **empty of source** — only `PROJECT_SPEC.md`,
two empty documentation folders (`elevenlabs-docs/`, `piagent-docs/`) and a bare
`venv/`. The git remote `origin` was already configured
(`https://github.com/alizeayn/solo.git`) with no commits.
