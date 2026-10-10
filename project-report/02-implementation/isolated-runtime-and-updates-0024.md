# 24 — Isolated Runtime, In-Place Updates and Workspace Tiles

**Stage:** Implementation
**Date:** 2026-10-10

---

## 1. Solo's own Pi Agent

### New module: `services/pi_runtime.py` (~430 lines)

One object owns everything about Solo's Pi installation.

```
<data>/pi-runtime/                    npm prefix
│   node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js
│   node_modules/.bin/pi              (never used — see below)
│   runtime.json                      manifest: package, version, node, timestamps, last error
└──
<data>/pi/agent/                      PI_CODING_AGENT_DIR
    auth.json                         written mode 600 through Solo's Settings API
    settings.json                     {"defaultProjectTrust": "never", "quietStartup": "header"}
    models-store.json                 Solo's own fetched catalog
    sessions/                         Pi's ephemeral session scratch
```

Key methods:

| Method | Responsibility |
|---|---|
| `resolve_argv()` | Absolute interpreter + script, or `None`. **No `PATH` lookup.** |
| `source()` | `managed` · `external` · `none` |
| `env()` | `PI_CODING_AGENT_DIR` = Solo's directory, always |
| `initialize()` | Creates both directories at mode `700`, seeds isolated settings and an empty `auth.json` |
| `install(force=)` | `npm install --prefix <runtime> @earendil-works/pi-coding-agent@1.1.0`, idempotent, reports failures |
| `rpc_probe()` | Starts the runtime in RPC mode and runs a command — the only thing that sets `verified` |
| `status(verify=)` | Truthful state, cached version, recorded failure |

### The three isolation guarantees and how they are enforced

**1. The executable is never resolved through `PATH`.**

```python
def resolve_argv(self) -> list[str] | None:
    external = self.external_executable()
    if external is not None:
        ...
    cli = self.managed_cli()          # <runtime>/node_modules/.../cli.js
    if cli is None:
        return None                   # nothing installed → nothing to run
    node = self.node_path()
    if node is None:
        return None
    return [node, str(cli)]
```

`external_executable()` deliberately **refuses a bare command name**:

```python
if os.sep not in raw and (os.altsep is None or os.altsep not in raw):
    return None          # PI_EXECUTABLE=pi is not a path — refuse it
```

so `PI_EXECUTABLE=pi` yields `source = "none"` with a message explaining why,
rather than silently resolving to the desktop installation.

**2. The agent directory is always Solo's.**

```python
def agent_dir(self) -> Path:
    override = (self._settings.pi_agent_dir or "").strip()
    if override:
        base = Path(override).expanduser()
    else:
        base = self._settings.app_data_dir / "pi" / "agent"   # never ~/.pi/agent
    return base.resolve() if base.is_absolute() else (Path.cwd() / base).resolve()
```

**3. Every subprocess gets Solo's configuration.** `env()` returns
`{"PI_CODING_AGENT_DIR": <Solo's>, "PI_SKIP_VERSION_CHECK": "1"}` and is passed
to every spawn: the long-lived task session, the one-shot probes and the CLI
subcommands (`pi auth check`, `pi update --models`).

### Invoking `node <cli.js>` instead of the shim

`node_modules/.bin/pi` is a symlink to `cli.js`, whose first line is
`#!/usr/bin/env node`. Using it would reintroduce a `PATH` dependency for
`node` — the same class of failure being fixed. Solo resolves Node once, records
the absolute path in `runtime.json`, and passes it explicitly. Only if that
recorded path disappears (an nvm upgrade) does it re-resolve and re-record.

### Why isolation is free

Verified before implementing:

| Agent directory | Credential | Models |
|---|---|---|
| empty | none | 0 |
| empty | one OpenRouter key | **401** |

The catalogs are bundled in the package
(`node_modules/@earendil-works/pi-ai/dist/providers/data/*.json`); Pi lists models
for authenticated providers. So saving a credential through Solo is enough — and
`PUT /api/pi/providers/{id}/credential` now **also runs
`pi update --models`** and reports the model count, so the isolated runtime
becomes usable with no terminal step.

### Failure handling

| Situation | Behaviour |
|---|---|
| Node missing | `install()` returns *"Node.js was not found, so Pi Agent cannot be installed"* with a link, before npm is invoked |
| npm missing | the same, naming npm |
| npm fails | the error output is captured, `last_error` is recorded in the manifest, the install reports failure, and `resolve_argv()` still returns `None` — no half-usable runtime |
| Runtime directory incomplete | `status()` says so and points at *Install / repair* |
| Runtime will not start | `verified` stays false with the reason; **`installed` is never conflated with `verified`** |
| An external `PI_EXECUTABLE` is set | honoured, labelled `external`, and reported as *not* Solo's own runtime |

---

## 2. Other backend changes

| Module | Change |
|---|---|
| `adapters/pi_session.py` | `build_pi_argv(exec_prefix, config)` takes an argv prefix; `PiSessionManager` takes the runtime and re-reads it before every run, so a reinstall or a credential change applies to the next task without restarting Solo |
| `adapters/pi_rpc.py` | `start()` accepts an absolute path as-is and only falls back to `which()` for a bare name that a caller deliberately passed |
| `adapters/pi_agent.py` | `probe_pi_runtime(settings)` delegates to the runtime; `health()` reports `installed`/`verified`/`source`/`isolated`/`node`/dirs |
| `adapters/__init__.py` | `resolve_backend("auto")` selects Pi only when **Solo's own runtime** is installed, never because `pi` is on `PATH` |
| `services/pi_config.py` | All path and executable resolution delegates to the runtime; `invalidate_model_cache()` added for the post-credential refresh |
| `api/pi.py` | `GET /api/pi/runtime`, `POST /api/pi/runtime/install`, `POST /api/pi/runtime/verify`; credential saves refresh the catalog |
| `api/health.py` | Reports `pi_version`, **`pi_isolated`** and `schema_version` |
| `main.py` | Runtime directories are created at startup so Settings reports truthfully on first load |
| `services/project_files.py` | **New** — safe read/write/upload inside a project (see §4) |
| `api/files.py` | **New** — the endpoints the Writing panel uses |

---

## 3. In-place updates

### New CLI: `python -m app.pi_install`

The shell installer and the Settings UI share one implementation:

```bash
PYTHONPATH=backend ./venv/bin/python -m app.pi_install [--force] [--verify] [--json]
```

Exit codes: `0` success, `1` install/verify failure, `2` unusable configuration.

### `./solo --update`

`./solo` is a symlink to `./solo.sh`; `update`, `--update` and `-u` are the same
command.

```
1  check      git checkout? origin configured? fetch origin
2  compare    same commit → "already up to date"
3  guard      refuse a dirty working tree (unless --force)
4  back up    app.db, master-key, secrets.enc, .env → data/backups/pre-update-<ts>
5  pull       fast-forward only
6  detect     compare recorded fingerprints
7  rebuild    only what changed
8  migrate    apply and report schema migrations
9  restart    start and wait for /api/health
10 record     version, commit, fingerprints → data/install.json
```

**Step 6 is what makes it incremental.** Fingerprints are stored after every
successful start or update:

| Changed | Rebuild |
|---|---|
| `backend/requirements.txt` | backend dependencies |
| `frontend/package-lock.json` | frontend dependencies |
| the frontend sources | the web UI |
| the pinned Pi Agent version | Solo's Pi runtime (then verify it starts) |
| none of the above | **nothing — restart only** |

Verified: an update whose only change was `VERSION` reported *"No dependency or
build changes detected — restarting only"* and performed **zero** rebuild steps.

**Rollback.** `rollback_update()` resets the checkout to the recorded commit,
restores the backed-up database, key, secrets and `.env`, reinstalls the previous
requirements and restarts — then reports where the backup is. It is called from
every failure path: a failed dependency install, a failed build, a failed
migration, a failed start, or a failed health check.

**Versioning.**

| Where | What |
|---|---|
| `VERSION` | The code's version (`2.2.0`) |
| `data/install.json` | version, previous_version, commit, fingerprints, timestamps |
| `GET /api/health` | the running version, `pi_isolated`, `schema_version` |
| `./solo.sh version` | installed vs available, and commits behind |

`backend/app/version.py` reads `VERSION` and provides `parse_version`,
`is_newer` and `describe_change`, so `2.2.0 → 2.3.0` is described as a "feature
update" rather than a bare string diff.

**Migrations.** `backend/app/migrations.py` adds a `schema_meta` table, a
`SCHEMA_VERSION`, an ordered `MIGRATIONS` map and a `migrate()` that creates
missing tables, applies pending statements and records the new version — a failed
migration leaves the recorded version untouched so the next start retries. It
runs at startup and the updater reports it (`schema 1 → 1 (no changes)`).

---

## 4. Workspace tiles

### Write panel (`frontend/src/panels/WritePanel.tsx`)

A focused writing surface for the open project: type a path and **Open**,
edit, **Save**, or **Upload file**. It is deliberately not a code editor — Solo
coordinates the coding agent rather than replacing it — but the workspace now has
somewhere to write notes, docs and small changes.

Backed by `services/project_files.py`, which is a **security boundary**:

| Rule | Why |
|---|---|
| Paths resolved inside the project root, symlinks re-checked | the same policy as the ZIP extractor |
| Absolute paths and `..` rejected | no traversal |
| `.solo/**` and `.git/**` are not writable | Solo's state store and git metadata must not be corruptible from the UI |
| Upload names reduced to a basename, hidden names rejected | a browser filename cannot choose a location |
| 512 KiB read, 1 MiB write, 50 MiB upload | a mistaken paste cannot fill the disk |
| Binary files are reported, not mangled | honest behaviour instead of corrupting a file |
| Writes are atomic (temp file + `os.replace`) | an interrupted save cannot truncate a file |
| Nothing is executed | project content stays data |

### Pi runtime card

A single-glance answer to *"is Solo's Pi Agent ready?"* — a coloured card stating
**installed and verified** / **installed** / **not installed**, the provenance
line (*"isolated — this is Solo's own copy, independent of any Pi on this
computer"*), and the dirs, executable, Node path and live sessions. With
**Install / repair** and **Verify runtime** actions, plus **Refresh catalog**.

### Voice indicator

`components/VoiceOrb.tsx`: a CSS-only animated orb — a breathing core, four
animated waveform bars and three staggered ripple rings — placed above the
composer.

It is **explicitly labelled as a preview**: the accessible name contains "Phase
4", the pill reads *"Voice preview"* and the hint reads *"not enabled yet"*. The
animation communicates the intended interaction without claiming a feature that
does not exist. `prefers-reduced-motion` is respected by dropping the animation
while keeping the indicator.

### Layout

The Write panel is registered in both layouts (Dockview and the narrow-screen
tabs), so the tiled workspace is now: Conversation over Write, Activity on the
right, Inspector tabbed with Write.

---

## 5. Installation and configuration

| Item | Change |
|---|---|
| `solo.sh install` | Calls `python -m app.pi_install --verify`; no global npm install, no sudo |
| `solo.sh doctor` | Reports the runtime directory, agent directory, executable, source, version, Node, isolation, and warns when a *separate* global `pi` also exists |
| `install.sh` | Native path delegates to `solo.sh install`, so it installs the isolated runtime too |
| `requirements.txt` | `pyright==1.1.414` |
| `Dockerfile` | Installs the pinned Pi package into `/opt/solo-pi-runtime` (baked into the image); sets `PI_RUNTIME_DIR` and `PI_AGENT_DIR=/data/pi/agent` so configuration lives in the volume. **Unverified — no Docker daemon (D-08).** |
| `.env.example` | Documents that `PI_EXECUTABLE` must be absolute and that a bare name is refused; documents `PI_RUNTIME_DIR` and `PI_AGENT_DIR` |
| `.gitignore` | `.tools/` (superseded but harmless) |

A fresh install therefore: creates the virtualenv, installs Solo's Pi Agent into
`<data>/pi-runtime`, initialises `<data>/pi/agent` with isolated defaults,
verifies the runtime actually starts, builds the UI, and starts the server.
