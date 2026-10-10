# 15 — Acceptance Criteria (Phase 1.5)

**Stage:** Verification
**Date:** 2026-10-10

Verification of the five requests that defined this phase, traced to concrete
evidence. Every claim below was produced by running something.

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | Project is named **Solo** consistently | ✅ | `grep` for the old name across the repository returns only `PROJECT_SPEC.md` (the requirements document, intentionally verbatim). Covered artefacts: README, FastAPI title, dev root payload, `pyproject.toml`, `package.json`, `index.html`, header brand, login heading, Dockerfile, compose image/container name, installer banner, and all docs. |
| 2a | **Create Project** creates a local project directory holding all project-specific data | ✅ | Live check: `POST /api/projects {"name":"Demo App"}` → `location: managed`, `root: /…/data/workspaces/demo-app`. The folder was created and initialised with `.solo/{project.json,config.json,.gitignore,state/,memory/,sessions/,tasks/}`. `test_create_initialises_the_metadata_store` asserts every path. |
| 2b | Each project has isolated data and configuration | ✅ | Every artifact is namespaced by project root and by id: `.solo/config.json` per project, `memory/entries/<id>.json`, `sessions/<id>.json`, `tasks/<id>.json`. Config updates are deep-merged and per project (`test_config_is_deep_merged_and_persisted`). A second project's store is a different directory. |
| 2c | **Open Project** selects an existing directory on the local machine or server | ✅ | `GET /api/fs/list` browses the server's filesystem (directories only) and `POST /api/projects/open {"path": …}` adopts it. Verified live against a real repository. Six frontend tests cover the browser; nine backend API tests cover open. |
| 2d | The application reads the project **directly from its existing location**; no upload, no copy | ✅ | Live check: opened `/tmp/my-existing-repo` → `location: external`, `root: /tmp/my-existing-repo`, `file_count: 2`. Files remained in place; only `.solo/` was added. The e2e suite asserts the project's file contents are **byte-for-byte unchanged** (`md5sum` before/after, excluding `.solo/`). |
| 2e | Opening loads existing configuration, memory, sessions and state | ✅ | Live check on a fresh project showed the tree, memory and sessions populated from the store. Portability is covered by `test_open_adopts_state_written_by_another_installation` (a pre-existing `.solo/project.json` id is adopted and a foreign task index entry survives) and `test_refresh_preserves_records_written_by_another_installation`. |
| 2f | Configuration for memory management, state management and the project tree | ✅ | `.solo/config.json` carries `tree` (max depth, max entries, exclusions), `memory` (max entries, auto-capture), `sessions` (retention) and `state` (auto-refresh). Editable in the UI (**Inspector → Project state → Config**) and via `PUT /api/projects/{id}/config`. Verified live and by `test_project_config_round_trip`. |
| 2g | Project state represented and stored in a structured, tree-like format | ✅ | `.solo/state/tree.json`: a `project` root with `Files`, `Tasks`, `Memory` and `Sessions` branches; nodes carry `kind`, `ref` to detail files, and activity metadata. Written atomically. `test_tree_has_the_four_state_groups` and `test_file_tree_lists_project_files_and_excludes_noise` assert structure; `test_the_metadata_directory_is_excluded_from_a_populated_tree` asserts exclusions. |
| 3a | Single command installs backend and frontend and starts the app on a port | ✅ | `./install.sh` from a clean checkout (`rm -rf data .env`) installed, built and started Solo on `:8080`, printing a URL and a one-time password. Verified by `curl /api/health`, `/`, and a successful login with the generated password. |
| 3b | Reproducible, actually launched and tested on a local machine | ✅ | The native install was executed on this machine (Ubuntu, Python 3.12.3, Node 24.16.0). Health reported `pi_version: 1.1.0`; the SPA was served; create/import/open/task/memory/config flows were all exercised against the running server. |
| 3c | Prerequisites, environment variables and manual steps identified | ✅ | Prerequisites table in the README (Python 3.10+, Node 20+, `curl`, or Docker). Every operational variable documented in `.env.example`, the README table and `docs/deployment.md`. **Manual steps remaining: none for install**; the only post-install actions are the optional ones (add API keys in Settings, choose a project). `./solo.sh doctor` reports missing prerequisites without changing anything. |
| 4a | README and Quick Start work for a **fresh** environment | ✅ | The install was run with `.env` and `data/` deleted, i.e. the exact state a stranger starts from. `scripts/dev.sh` was corrected to run from the repository root so the development path matches the installed path. |
| 4b | Clone → install → configure → launch → browser documented | ✅ | README "Quick start": prerequisites, one command, what the installer creates, then "Settings → Create/Open → type a request". Both native and Docker journeys are documented, including day-2 commands. |
| 4c | Hand the repository to someone else to install and test | ✅ | Requirements are only Python+Node or Docker; **no API key is needed to install or explore**. The simulator backend means the whole UI path is usable with zero credentials. `docs/projects.md` explains the model independently of this conversation. |
| 4d | Required environment variables, API keys and configuration documented | ✅ | README configuration table; `.env.example` grouped and commented; `docs/deployment.md` §2; secrets documented as UI-managed, encrypted, never in `.env`. |
| 4e | No secrets, credentials or sensitive information exposed | ✅ | Audit table in report 13 §5. `.env`, `data/`, `initial-admin-password`, `venv/`, `node_modules/`, `frontend/dist/` are all untracked; `.dockerignore` excludes the same; a scan of tracked files found no credential-shaped strings; the local install has no stored API keys. |
| 5 | Summary in the CLI, documented in the Project Report | ✅ | This report set (documents 11–16) plus the CLI summary delivered with it. |
| 6 | Do not start Phase 2 | ✅ | No Pi RPC, OpenRouter, ElevenLabs or Pygments work was done. `PiCodingAgentAdapter` remains a stub that fails loudly, `AGENT_BACKEND` remains `mock`, and the voice control remains disabled with a phase label. |

---

## Regression check: Phase 1 guarantees are intact

Every Phase 1 acceptance criterion was re-verified. Nothing regressed.

| Phase 1 criterion | Status after this phase |
|---|---|
| Authentication required for all functionality | ✅ unchanged; 3 new cookie tests added |
| Secrets stored encrypted, never returned or logged | ✅ unchanged |
| ZIP import safe against traversal, symlinks and bombs | ✅ unchanged |
| Path boundaries enforced | ✅ **strengthened** — the policy is now one module with a blocked set and optional allow-list |
| One modifying task per project | ✅ unchanged |
| Cancellation confirmed, not assumed | ✅ unchanged |
| A question does not interrupt a running task | ✅ unchanged |
| State survives restart; interrupted tasks marked for review | ✅ unchanged |
| Moving/closing a panel does not affect a task | ✅ unchanged |

---

## Verification matrix

| Layer | Method | Result |
|---|---|---|
| Backend unit + API | `pytest --cov=app` | ✅ **194 passed**, 91 % coverage |
| Frontend unit + component | `vitest run` | ✅ **39 passed** |
| Types | `tsc --noEmit`, `strict` | ✅ 0 errors |
| Frontend bundle | `npm run build` | ✅ 661 kB JS (170 kB gzip) |
| End-to-end (real server) | `scripts/e2e.sh` | ✅ **53 passed**, 0 failed |
| Native install | `./install.sh` from a clean checkout, then live API checks | ✅ |
| Shell scripts | `bash -n` × 6 | ✅ |
| Compose configuration | `docker compose config --quiet` | ✅ |
| Docker image build | `docker compose build` | ⚠️ still blocked (D-08 — daemon socket inaccessible) |

**Total automated checks: 286** (194 + 39 + 53), all passing.

---

## Known limitations

1. **The coding agent is still a simulator.** It emits realistic events and
   modifies nothing. Stated in the README status table, in the Settings UI, and
   here.
2. **The Docker image was still not built** (D-08). The native install path was
   executed end to end instead; the Dockerfile's steps were verified
   individually in report 07.
3. **`ALLOW_ANY_PROJECT_PATH` defaults to permissive.** Correct for a personal
   install; documented as needing to change before wider exposure, and flagged
   for your confirmation in report 11 §4.
4. **No browser-driven UI automation (Playwright/Cypress).** Component tests plus
   a real-server API-level end-to-end run cover the path; the UI itself is
   verified by typecheck, component tests and manual use.
5. **The state store reflects history, not a full audit log.** Task records are
   bounded (50 tasks, 500 events per task) and older detail files are retained
   on disk but no longer indexed.
6. **No migration framework.** Schema changes are additive only; documented in
   `docs/development.md`.
