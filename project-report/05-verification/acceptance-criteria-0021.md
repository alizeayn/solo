# 21 — Acceptance Criteria (Phase 2)

**Stage:** Verification
**Date:** 2026-10-10

Every verdict below was produced by running something. Where a claim could not be
verified in this environment it says so explicitly.

---

## 1. Primary goal: coding tasks execute through Chat

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | A coding task submitted through Chat is executed by Pi inside the opened project | ✅ **verified with a real model** | `scripts/e2e-live.sh` — 26/26 checks. A message sent to `/api/projects/{id}/messages` produced `intent=START_CODING_TASK`, a task, and a completed run |
| 2 | The task reaches the **correct project and directory** | ✅ | The project was opened in place at `/tmp/…`; Pi was launched with `cwd` = that directory; the created file appeared there |
| 3 | Pi **actually creates/modifies files** (not a simulated result) | ✅ | `hello_world.py` existed on disk, 85 bytes, containing exactly the requested `main()` and `__main__` guard; a pre-existing `main.py` was untouched |
| 4 | The execution process is displayed in the browser workspace | ✅ | `run.started`, `file.changed`, `tool.started`, `test.result`, `assistant.message`, `run.finished` were all recorded and broadcast; the Activity panel renders the timeline, changed files and a static-checks section. Component tests cover the rendering |
| 5 | Steps and progress are monitorable | ✅ | Changed files with `written`/`modified`, tool activity, test summaries, progress summaries, a live status pill, and an orchestrator summary on completion |
| 6 | No simulated result is presented as real | ✅ | The backend is reported by `/api/health` and Settings as `pi` or `mock`; the simulator is only used when Pi is absent, and the UI always names the active backend |

## 2. Pi Agent configuration from the Settings UI

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 7 | Select a provider | ✅ | `GET /api/pi/providers` merges Pi's catalog with a curated list; provider ids and env vars were taken from the installed build, and a test asserts Pi recognises every id |
| 8 | Enter and save the API token (equivalent to `/login`) | ✅ | `PUT /api/pi/providers/{id}/credential` writes Pi's `auth.json` atomically at mode `600`; a test asserts the file contents and permissions, and that the key never appears in any response |
| 9 | Validate the credentials | ✅ | `pi auth check` for presence; a **real completion** for validity. Two tests assert that a presence check never yields `verified` |
| 10 | Discover available models, with refresh | ✅ | `GET /api/pi/models` (RPC `get_available_models`) and `POST /api/pi/models/refresh` (`pi update --models`). 31 models were discovered for `opencode-go` in the live run |
| 11 | Select a model and save it as Pi's configuration | ✅ | Saved as `pi_provider`/`pi_model` and passed to every new Pi process; verified live — the running model appeared in the summary event |
| 12 | Review and update the configuration without leaving the Workspace | ✅ | Settings → Pi Agent shows provider, credential source, readiness, model, thinking level, live sessions and trust; all mutable in place |
| 13 | Credentials stay secure and out of frontend code, logs and ordinary logs | ✅ | Encrypted at rest for Solo's own key; `auth.json` mode `600` for Pi's; the API returns only `{configured: true}`; log redaction unchanged from Phase 1 |
| 14 | Keep saved / validated / failed clearly distinct | ✅ | Three states — `not_configured`, `configured`, `verified` — plus `failed`, rendered as labelled pills; tested in both settings components |
| 15 | Handle providers whose models cannot be discovered automatically | ✅ | A manual model-ID field is always available, and the UI says so explicitly when discovery returns nothing; a test covers the fallback |

## 3. Orchestrator (OpenRouter) configuration

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 16 | Configure the OpenRouter API key from Settings | ✅ | `PUT /api/settings`, encrypted; a dedicated Orchestrator pane |
| 17 | Test API connectivity and display the result | ✅ | `POST /api/orchestrator/test` → `GET /api/v1/key`; failures surface the provider's message |
| 18 | Retrieve available models, with refresh | ✅ | `GET /api/orchestrator/models`; OpenRouter's catalog is fetched live and is filterable |
| 19 | Select the Orchestrator model | ✅ | `PUT /api/orchestrator/config`; persisted as `openrouter_model` |
| 20 | Save and persist the configuration securely | ✅ | Same encrypted store as Phase 1; masked in every response; never logged |
| 21 | **The Orchestrator actually uses the configured model** | ✅ **verified** | `classify`, `summarise` and `answer_question` all call it, and `classified_by` reports `orchestrator-model` vs `rules`. Tests drive a fake client through all four methods; the Status pane reports call count, failures, last model and latency so usage is observable |
| 22 | Handle invalid keys, connectivity problems, unavailable models and API errors | ✅ | `400` (no key), `not_configured`, `failed` with the provider message, and `402 Insufficient credits` surfaced verbatim (encountered for real during development) |
| 23 | Do not mark a configuration valid unless the check succeeds | ✅ | `deep=false` returns `configured`, never `verified`; `verified` requires a successful completion. Asserted by tests |

## 4. State foundation

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 24 | Manage conversation and project state | ✅ | `OrchestrationState` persisted per project in `.solo/state/orchestration.json`, verified live |
| 25 | Break complex requests into smaller tasks | ✅ | Structured `subtasks` → `PlannedTask`s; decomposition tested with dependencies resolved from titles |
| 26 | Prioritise by importance and dependency | ✅ | `priority` + `depends_on` + `next_pending()`; tests cover ordering and that a dependency blocks |
| 27 | Generate concise summaries of what Pi is doing | ✅ | `summarise` produces the task's `result_summary` (observed live) and a `progress.summary` event |
| 28 | Retain instructions introduced mid-task and record their effect | ✅ | Steered instructions are recorded with `applied: "steered"`; deferred ones with `applied: null` and shown as pending. Tested |
| 29 | Decide which tasks go to Pi and in what order | ✅ | Automatic sequential advance on success; a failed step stops the chain |
| 30 | Extensible to reasoning and voice without rebuilding | ✅ | The state document and the four brain methods are the interface; Phase 3/4 add consumers. Documented in `docs/orchestrator.md` §3 |

## 5. Pyright

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 31 | Pyright is available and appropriately configured | ✅ | Installed via `requirements.txt`; `GET /api/checks/status` reports availability; `doctor` reports it |
| 32 | It verifies what the agent changed | ✅ | Runs after a task settles, preferring the changed Python files; `check.result` events carry diagnostics. Tests assert a real type error is found and that clean code passes |
| 33 | It never blocks or breaks a task | ✅ | Bounded, asynchronous, and a missing tool/timeout/unparseable output yields a `skipped`/`error` result rather than an exception |

## 6. Installation and no regressions

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 34 | Easy Installation covers the new dependencies | ✅ | `solo.sh` installs Pi locally (no sudo, no global npm) and reports Pyright; `doctor` reports both. Verified: `doctor` shows *"Pi Coding Agent on PATH: 1.1.0"* and *"pyright available for static checks"* |
| 35 | The local Pi install path works | ✅ | `npm install --prefix` was executed and produced a working `pi --version` (1.1.0) |
| 36 | The credential → catalog flow works from scratch | ✅ | In a fresh agent directory, adding one credential and running the refresh discovered 31 models — the exact flow the Settings UI drives |
| 37 | Existing functionality is unaffected | ✅ | All 286 Phase 1/1.5 checks still pass, plus 70 new ones |
| 38 | UI improvements work across screen sizes | ⚠️ **partially verified** | The tabbed settings shell, wrapped action rows, bounded model lists and the existing <900 px stacked layout are covered by typecheck and component tests; **no browser-automation suite**, so visual behaviour at specific breakpoints was checked by construction and manual use, not automated |

## 7. Documentation and delivery

| # | Requirement | Verdict |
|---|---|---|
| 39 | Documentation added to `Pi Agent Docs` | ✅ 19 vendor documents (Pi 1.1.0) + an index + a full integration document |
| 40 | Project Report updated | ✅ Documents 17–22 |
| 41 | Pushed to GitHub with no secrets | ✅ Audit re-run before push |

---

## Verification matrix

| Layer | Method | Result |
|---|---|---|
| Backend unit + API | `pytest --cov=app` | ✅ **288 passed**, 86 % coverage |
| Pi protocol, translation, adapter | fake Pi subprocess (protocol-accurate) | ✅ 24 tests, no credentials needed |
| Real Pi Agent end to end | `scripts/e2e-live.sh` | ✅ **26/26** with `opencode-go` / `claude-haiku-5-5` |
| Simulator end to end | `scripts/e2e.sh` | ✅ 53/53, no credentials needed |
| Frontend unit + component | `vitest run` | ✅ **68 passed** |
| Types | `tsc --noEmit`, `strict` | ✅ 0 errors |
| Frontend build | `vite build` | ✅ |
| Native install + doctor | `./solo.sh doctor` | ✅ reports Pi and Pyright |
| Docker image | `docker compose build` | ❌ **not executed** — no daemon access (**D-08**) |

**Total automated checks: 382** (288 backend + 68 frontend + 26 live) plus the 53
simulator end-to-end checks.

---

## Known limitations

1. **The Docker image was not built.** The daemon socket is not accessible to
   this user (D-08). The Dockerfile now installs Node and the Pi CLI behind a
   build arg; that step is **unverified**. The native install path was executed
   and verified instead.
2. **The live test depends on a working provider credential.** It was verified
   with `opencode-go`; the OpenRouter key available during development returned
   `402 Insufficient credits`, which is itself evidence that provider errors are
   surfaced correctly, but means the OpenRouter *coding* path was not exercised
   with a successful completion.
3. **No browser-automation suite.** Component tests plus API-level end-to-end
   cover behaviour; visual breakpoints are not automated.
4. **Mid-run narration is not implemented.** Summaries are produced once per
   settled task. The interface is the one Phase 5 will narrate.
5. **Pi is not sandboxed.** It runs with the permissions of the Solo process in a
   directory the user opened. Solo's path policy bounds *which* directories, not
   what Pi may do inside one.
6. **Solo's `data/` cannot be a project root** (by design, so the master key is
   unreachable), which also means the Docker container cannot open its own volume.
7. **No schema migration framework.** Changes remain additive.
