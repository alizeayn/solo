# 26 — Acceptance Criteria (Runtime Isolation and Updates)

**Stage:** Verification
**Date:** 2026-10-10

Every verdict was produced by running something. Where a claim could not be
verified in this environment it says so.

---

## 1. The primary criterion: Solo runs its own Pi Agent

> *Solo must run its own isolated Pi Agent instance and must never silently fall
> back to my global desktop installation.*

**Verdict: ✅ verified, with the global installation removed from `PATH`.**

The decisive test: a full coding task, end to end, in a shell where `pi` does
not exist.

```
$ command -v pi
NOT FOUND

$ ./scripts/e2e-live.sh
▸ Installing Solo's isolated Pi Agent runtime (what Easy Installation does)
  ✓ Solo's own Pi Agent runtime installed and verified
  ✓ no global pi on PATH — this run proves independence from it
▸ Pre-flight: Solo's own Pi runtime and a usable credential
  ✓ Solo's runtime: managed v1.1.0
  ✓ runtime is isolated (source=managed)
  ✓ runtime lives inside this installation
  ✓ Pi configuration is isolated from the desktop installation
  ✓ runtime is outside the source checkout
  ✓ Pi configuration is not ~/.pi/agent
  ✓ Solo accepted the credential into its own Pi configuration
  ✓ credential stored in Solo's agent directory
  ✓ Solo's credential file is separate from the host's
  ✓ 401 models discovered for opencode-go
▸ Submit a coding task through Chat
  ✓ intent(rules) → START_CODING_TASK
  ✓ task reached COMPLETED
  ✓ hello_world.py exists (85 bytes), contains the requested text, has the guard
  ✓ pre-existing file untouched
 Result: 39 passed, 0 failed
```

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | Solo has its own dedicated Pi Agent installation | ✅ | Installed into `<data>/pi-runtime`; `source=managed`; `./solo.sh doctor` prints the runtime dir, executable, version and Node path |
| 2 | Its dependencies and runtime are managed within Solo | ✅ | An npm prefix inside Solo's data directory; `runtime.json` records the version, Node path and any last error |
| 3 | Configuration, credentials and model selection are independent of the desktop Pi | ✅ | `<data>/pi/agent` holds Solo's own `auth.json`, `settings.json` and `models-store.json`; the live test asserts the credential file is separate from the host's |
| 4 | The harness explicitly invokes its own executable | ✅ | `resolve_argv()` returns `[<absolute node>, <absolute cli.js>]`; asserted in `test_managed_runtime_resolves_to_an_absolute_interpreter_and_script` |
| 5 | No dependency on the global installation | ✅ | 39/39 live checks with `pi` absent from `PATH` |
| 6 | Installing/updating Solo does not modify the desktop Pi setup | ✅ | `~/.pi/agent/{auth,settings}.json` hashed before and after a credential save **and** delete through Solo's API: **byte-for-byte identical**. A decoy `~/.pi/agent` is also asserted untouched in `test_the_host_pi_directory_is_never_touched` |
| 7 | Never silently falls back | ✅ | `test_path_is_never_used_even_when_pi_is_available` puts a `pi` on `PATH` and asserts `resolve_argv()` is still `None`; `PI_EXECUTABLE=pi` is refused with an explanation (`test_a_bare_command_name_is_refused`) |

**20 dedicated isolation tests** cover these guarantees
(`backend/tests/test_pi_runtime.py`).

---

## 2. Easy Installation

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 8 | A fresh installation sets up the isolated environment | ✅ | `./solo.sh install` on this machine created the venv, installed Solo's Pi Agent, initialised the agent directory and started the server |
| 9 | Installs the Pi Agent package and dependencies | ✅ | `npm install --prefix …/pi-runtime @earendil-works/pi-coding-agent@1.1.0`; the version is pinned so installs are reproducible and an update can detect a change |
| 10 | Configures the runtime to use the correct executable | ✅ | `resolve_argv()` + `PI_CODING_AGENT_DIR` passed to every spawn; no `PATH` lookup anywhere |
| 11 | Initialises Solo's independent Pi configuration | ✅ | `initialize()` creates `<data>/pi/agent` at mode `700`, `auth.json` (`{}`, mode `600`) and `settings.json` with `defaultProjectTrust: "never"` — the only directory where Pi permits that key |
| 12 | Verifies the runtime can start and execute | ✅ | `./solo.sh install` runs `--verify`; `doctor` and *Verify runtime* in Settings do the same. It really starts Pi in RPC mode and runs `get_state` |
| 13 | Does not merely check `PATH` | ✅ | The installer resolves Node and npm, then verifies **its own** installation by starting it |
| 14 | Handles missing installations, failed installs, upgrades and init errors | ✅ | Tests cover: no Node, no npm, npm failure (with `last_error` recorded and no half-usable runtime), incomplete runtime directory, an unstartable runtime, and an explicit external override |

---

## 3. In-place updates

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 15 | `solo --update` updates the existing installation | ✅ | `./solo --update`, `./solo.sh update` and `-u` are the same command; exercised against a temporary upstream |
| 16 | Fetches the latest changes from the configured branch | ✅ | `git fetch origin <branch>`, branch configurable with `SOLO_BRANCH` |
| 17 | Updates the application code | ✅ | Fast-forward merge; a diverged branch refuses with an explanation unless `--force` |
| 18 | Detects dependency changes and installs only what is required | ✅ | Fingerprints for `requirements.txt`, `package-lock.json`, the frontend sources and the pinned Pi version. Verified: a version-only update performed **0** rebuild steps and reported *"No dependency or build changes detected"* |
| 19 | Applies database migrations safely | ✅ | `schema_meta` + `migrate()` runs at startup; the updater reports `schema 1 → 1 (no changes)`. A failed migration leaves the version unrecorded so the next start retries |
| 20 | Updates Solo's Pi runtime only when required | ✅ | Triggered by a change to the pinned version; verified by observing the runtime reinstall and re-verify when the pin moved |
| 21 | Preserves projects, settings, credentials, sessions, memory and workspace state | ✅ | `app.db`, `master.key` and `.env` were hashed before and after a real update: **all byte-for-byte identical**. `data/` is never in the update path |
| 22 | Avoids overwriting user modifications | ✅ | A dirty working tree is **refused** (this was observed working, and cost a debugging cycle before it was understood) |
| 23 | Version tracking and incrementing | ✅ | `VERSION` file, `data/install.json`, `/api/health`, `./solo.sh version`; `parse_version`/`is_newer`/`describe_change` unit-tested |
| 24 | Compatibility checks | ⚠️ **partial** | The updater detects what changed and refuses a diverged history. There is no version-range compatibility gate (e.g. "requires ≥ 2.0"), because every change so far has been additive. The mechanism is documented as the place to add one |
| 25 | Backup/rollback before risky updates | ✅ | `data/backups/pre-update-<ts>/` containing `app.db`, `app.db-wal`, `master.key`, `secrets.enc`, `env.backup` and `install.json` — observed created with `master.key` and `env.backup` present |
| 26 | Clear error handling on failure | ✅ | Every failure path calls `rollback_update()`, which restores the checkout, the data, the dependencies and restarts the previous version, then prints where the backup is |
| 27 | Final report of previous version, new version, changes and outcome | ✅ | `2.2.0 → 2.8.0`, the commit range, the list of applied changes and the backup path. `previous_version` was fixed during this phase (D-21) and re-verified |
| 28 | Never leaves a partially updated state | ✅ | Rollback on any failure in steps 6–9, including a failed health check |
| 29 | Works for a clone-installed Solo, with no package manager | ✅ | The update path is `git` + the existing venv and npm; nothing assumes a package registry |

---

## 4. Orchestrator, regression and UI

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 30 | The existing Orchestrator configuration continues to work | ✅ | The Orchestrator layer is untouched by this phase; its tests pass unchanged (33 in `test_orchestration_layer.py`, 14 API tests). The isolation change affects only *Pi's* provider path |
| 31 | Opening an existing project and creating a new project both work | ✅ | The live test opens an existing directory in place and completes a task in it; creation is covered by `test_api_projects.py` and the simulator end-to-end run |
| 32 | Changes do not break the existing application | ✅ | **339 backend** (from 288), **82 frontend** (from 68) and **53 simulator end-to-end** checks all pass. No existing test was weakened; the five that changed did so because the isolation redesign changed their subject |
| 33 | Pi Agent tile shows runtime status clearly | ✅ | A runtime card: **installed and verified** / **installed** / **not installed**, with a provenance line stating the runtime is Solo's own copy, plus dirs, executable, Node, sessions and Install/repair + Verify actions |
| 34 | Writing interface | ✅ | The Write panel: open, edit, revert and save a text file, with unsaved state, size limits, an atomic server-side write and a clear error for a rejected path |
| 35 | File upload into the workspace | ✅ | The Write panel uploads a file into the project; the server reduces the name to a basename and rejects hidden names, traversal and oversize uploads |
| 36 | Animated, appealing voice placeholder | ✅ | `VoiceOrb` — breathing core, animated waveform, staggered ripples; CSS-only, respects `prefers-reduced-motion` |
| 37 | The voice placeholder does not imply working voice | ✅ | The pill reads *"Voice preview"*, the hint *"not enabled yet"*, and the accessible name contains "Phase 4". A test asserts exactly this |

---

## 5. Verification matrix

| Layer | Method | Result |
|---|---|---|
| Backend unit + API | `pytest` | ✅ **339 passed** |
| Isolation specifically | `tests/test_pi_runtime.py` | ✅ **20 passed** |
| Frontend unit + component | `vitest` | ✅ **82 passed** |
| Types | `tsc --noEmit`, `strict` | ✅ 0 errors |
| Simulator end-to-end | `scripts/e2e.sh` | ✅ 53/53 |
| **Live end-to-end, global `pi` absent from `PATH`** | `scripts/e2e-live.sh` | ✅ **39/39** |
| Isolation of the host configuration | hash before/after a credential cycle | ✅ byte-for-byte identical |
| Native install | `./solo.sh install` then `doctor` | ✅ runtime installed, verified, `source=managed`, `isolated=yes` |
| Update: fresh manifest | `./solo.sh update` against a temporary upstream | ✅ 2.2.0 → 2.7.0, data preserved, backup created |
| Update: incremental | a second update with only a version change | ✅ **0** rebuild steps |
| Update: previous version | same run | ✅ `previous_version: 2.7.0` for `2.7.0 → 2.8.0` |
| Update: dirty tree | uncommitted edit present | ✅ refused with a clear message |
| Scripts | `bash -n` × 6 | ✅ |
| Compose configuration | `docker compose config --quiet` | ✅ |
| Docker image | `docker compose build` | ❌ **not executed** — no daemon access (D-08) |

---

## 6. Known limitations

1. **The Docker image was not built** — no daemon access (D-08). The Dockerfile
   now bakes the pinned Pi runtime into `/opt/solo-pi-runtime` and puts Pi's
   configuration in the volume; that step is **unverified**.
2. **No version-range compatibility gate.** The updater detects what changed and
   refuses a diverged history, but does not yet refuse "this installation is too
   old for this release".
3. **Workspaces are not in the pre-update backup.** The backup covers the
   database, encryption key, secrets and `.env`, because project directories can
   be large and are the user's own files. `scripts/backup.sh` remains available
   for a full volume backup.
4. **The live test needed a credential.** Solo's Pi configuration is isolated, so
   the test seeds one through Solo's own API from the machine's existing Pi
   credential (or `PI_TEST_API_KEY`). Without either it reports the isolation
   results and skips the coding task rather than failing.
5. **`updated_by`/`previous_version` are only as good as the last successful
   write.** An update interrupted by a power loss leaves the previous manifest in
   place, which is the safe direction, but the recorded history is then one step
   stale.
6. **The voice indicator is a placeholder.** No audio is processed. It is
   labelled as such in the UI, the accessible name and the tests.
7. **Pi is not sandboxed.** Solo bounds *which* directories can be opened, not
   what Pi may do inside one.
