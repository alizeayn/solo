# 11 — Phase 1.5 Scope: Naming, Project Model, Installation

**Stage:** Planning
**Date:** 2026-10-10
**Milestone:** Phase 1.5 — Solo, the project model, and public readiness

---

## 1. Why this phase exists

Phase 1 delivered a working application shell with one project concept:
"create a workspace, or upload a ZIP". Before starting Phase 2 (the real Pi
integration) four things had to be fixed, because each one changes the shape of
the product rather than adding to it:

| # | Request | Why it could not wait for Phase 2 |
|---|---|---|
| 1 | Name the project **Solo** | Naming appears in package names, API titles, the container image, docs and the UI. Renaming later means touching every artefact again. |
| 2 | Separate **Create Project** from **Open Project** | Open Project changes what a "project" *is*: a directory on disk, read in place, not a managed copy. That is an architectural change to the project entity, the path policy and the state store. |
| 3 | Make installation a genuine single command | The README's quick start had never been executed end to end on a machine without Docker. |
| 4 | Prepare for a **public** repository | Requires reproducible instructions for strangers, and a secrets audit. |

**Explicitly out of scope** (per instruction): Phase 2 (Pi RPC), OpenRouter,
ElevenLabs, Pygments or any other integration.

---

## 2. What was already true (audit before writing code)

Reviewed before changing anything. This is what Phase 1 actually shipped:

| Already working | Evidence |
|---|---|
| FastAPI + React app on one origin, Docker deployment | `docker-compose.yml`, `Dockerfile`, e2e SPA check |
| Single-user auth with hashed password and HttpOnly cookie | 15 tests in `test_api_auth.py` |
| Encrypted secrets, masked in responses, redacted in logs | `test_api_settings.py`, `test_security.py` |
| Projects confined to `workspaces/`, Zip-Slip-safe import | `test_api_projects.py`, `test_archive.py` |
| Task lifecycle, normalized events, WebSocket push | `test_api_tasks.py`, `test_orchestrator.py` |
| Intent routing (question / steer / stop / new task) | `test_intent.py`, `test_api_messages.py` |
| Restart recovery to `RECOVERY_REQUIRED` | `test_orchestrator.py` |
| Tiled Dockview UI with layout persistence | `frontend` tests + manual |
| Installer, backup/restore, dev workflow | scripts existed but only the Docker path was ever exercised |

## 3. What was missing

| Gap | Consequence |
|---|---|
| No way to work on an existing repository without copying it | The primary real-world workflow was impossible |
| No per-project state on disk | Config, memory and sessions lived only in SQLite; a project was not portable |
| No structured project state | Nothing to inspect or manage per project |
| No filesystem browsing | Opening a path was impossible |
| No memory or session retention model | The specification's "minimal memory" requirement had no implementation |
| Native (non-Docker) install path | Untested; Docker was assumed |
| `Secure` cookie tied to `APP_ENV` | Would break sign-in on any plain-HTTP install |
| Never installed from a clean checkout | The public quick start was unverified |

---

## 4. The decision I want confirmed

Opening a path on the server is a deliberate narrowing of the Phase-1 security
posture, which stated: *"The MVP must not allow a browser user to select
arbitrary server filesystem paths."* Open Project requires exactly that.

**How it is implemented:**

- authenticated single user only (no change to the auth model);
- paths fully resolved before any check, so symlinks cannot escape a rule;
- a hard-blocked set — `/proc`, `/sys`, `/dev`, `/etc`, `/boot`, `/run`,
  `/root`, `/var/lib/docker`, `/var/lib/solo` — plus the Solo `data/` directory
  (which holds the master encryption key), on every deployment;
- `ALLOW_ANY_PROJECT_PATH` (default `true`) governs whether other folders are
  allowed, with `PROJECT_ROOTS` as an explicit allow-list;
- the browser only ever receives directory names, never file contents, and
  every path is re-validated server-side.

**The trade-off, stated plainly:** with the default setting, anyone who can sign
in can make Solo read any directory the process can read — and, once Phase 2
lands, let the coding agent **write** there. For a personal, local-first,
single-user install that is the intended and useful behaviour, and it is what
"open a folder on my machine" means.

**Default chosen: permissive (`true`), prominently documented.**
**Recommendation: set `ALLOW_ANY_PROJECT_PATH=false` + `PROJECT_ROOTS` before
exposing Solo beyond your own machine.** This is documented in the README
security section, `docs/projects.md` §8, and `docs/deployment.md` §2.

**Please confirm** whether the default should stay permissive or flip to
allow-list-only. Flipping it is a one-line change plus a README/install note.

---

## 5. Success criteria

1. Solo is named consistently in every artefact.
2. Create Project produces a self-contained project folder with structured
   state; Open Project adopts an existing folder **without copying anything**;
   Import ZIP remains available.
3. Project configuration, memory, sessions, task history and state are stored
   in a documented, inspectable, tree-shaped structure.
4. `./install.sh` installs and starts Solo on a machine with no Docker.
5. A stranger can clone the repository, follow the README, and have a running
   instance without asking questions.
6. No secret, credential or generated artefact is committed.
7. Every earlier guarantee still holds (all Phase 1 tests still pass).
