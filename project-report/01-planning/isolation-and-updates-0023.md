# 23 — Scope: Runtime Isolation, In-Place Updates and Workspace Tiles

**Stage:** Planning
**Date:** 2026-10-10
**Milestone:** Solo owns its Pi Agent; Solo can be updated in place

---

## 1. Why this phase exists

Two problems were reported after using the Phase 2 build.

**The reported symptom.** *Settings → Pi Agent* showed
`The 'pi' executable was not found on PATH`, while `./solo.sh doctor` on the same
machine reported `Pi Coding Agent on PATH: 1.1.0`.

**The underlying request.** Solo must run **its own isolated Pi Agent** and must
never silently fall back to the desktop installation, which the user relies on
for unrelated work.

**The second request.** Updating Solo must not mean deleting and reinstalling it,
and must not disturb projects, credentials, memory or sessions.

---

## 2. Root-cause investigation

### 2.1 Why the executable was "not found" — two independent causes

```
$ command -v pi
/home/paya/.nvm/versions/node/v24.16.0/bin/pi

$ env -i PATH="/usr/local/bin:/usr/bin:/bin" sh -c 'command -v pi'
NOT FOUND
```

`pi` lived in an **nvm** directory that is only on `PATH` while nvm is active in
that shell. Solo ran `shutil.which("pi")`:

```python
# backend/app/adapters/pi_agent.py, before
resolved = shutil.which(executable)          # PATH lookup
agent_dir = os.environ.get(
    "PI_CODING_AGENT_DIR", os.path.expanduser("~/.pi/agent")
)                                            # the user's desktop config
```

So a background-started Solo (nohup, a different shell, systemd, a container)
could not find it, and — worse — when it *did* find it, it used the user's
installation.

### 2.2 It was not only reading the wrong installation — it was writing to it

```python
    def auth_file(self) -> Path:
        return self.agent_dir() / "auth.json"     # → ~/.pi/agent/auth.json
```

`save_credential()` wrote into `~/.pi/agent/auth.json`. Confirmed by mtime: the
file had been modified during earlier testing. **Solo had already modified the
user's desktop Pi configuration**, which is precisely the outcome the request
forbade.

### 2.3 The assumption that justified the old design was wrong

Phase 2 deliberately reused the host installation, on this recorded finding:

> *"A fresh agent directory has **zero models** (verified). … Solo therefore
> reuses your existing Pi installation, which also preserves your model
> catalog."*

Re-tested properly, the real rule is:

| Agent directory | Credential | Models reported |
|---|---|---|
| empty | none | **0** |
| empty | one OpenRouter credential | **401** |

The package ships the provider catalogs
(`node_modules/@earendil-works/pi-ai/dist/providers/data/*.json`); Pi lists models
for **providers it has credentials for**. A fresh directory has no models only
because it is *unauthenticated*.

**Conclusion: isolation costs nothing.** The Phase 2 trade-off was based on an
incomplete experiment, and the corrected finding makes the requested design both
possible and correct.

---

## 3. What had to change

| # | Requirement | Consequence |
|---|---|---|
| 1 | Solo installs and owns its own Pi Agent | An installer, a runtime directory, a manifest, and a way to repair |
| 2 | Never resolve `pi` through `PATH` | Explicit resolution, and an explicit refusal of bare names |
| 3 | Never touch `~/.pi/agent` | Agent directory defaults inside Solo; every subprocess gets Solo's `PI_CODING_AGENT_DIR` |
| 4 | Credentials and model selection are Solo's own | Save through Solo's API, then refresh Solo's own catalog |
| 5 | Easy Installation sets all of this up | `solo.sh install` calls a shared installer; `doctor` reports provenance |
| 6 | Failures are handled | Missing Node/npm, failed install, incomplete runtime, unstartable runtime |
| 7 | `./solo --update` updates in place | Versioning, change detection, backup, rollback, migration |
| 8 | Preserve everything persistent | Fingerprints, backups, and a refusal to overwrite a dirty tree |
| 9 | UI: Pi status, Writing, Upload, Voice | A runtime card, a Write panel, file upload, an animated voice indicator |

---

## 4. Design decisions

| Decision | Choice | Rationale |
|---|---|---|
| Where the runtime lives | `<data>/pi-runtime` | Inside Solo, on the persistent volume, so it survives updates and container rebuilds |
| Where Pi's config lives | `<data>/pi/agent` | Must never be `~/.pi/agent`; travels with the installation |
| How Pi is invoked | `node <cli.js>` (absolute both) | The `.bin/pi` shim's `#!/usr/bin/env node` would reintroduce a `PATH` dependency |
| Node discovery | Resolved once, recorded in `runtime.json` | Re-resolved only if the recorded path disappears (an nvm upgrade) |
| `PI_EXECUTABLE` | Optional, **absolute paths only** | A deliberate escape hatch that cannot become a silent fallback |
| Installer location | `python -m app.pi_install` | The shell installer and the Settings UI share one implementation |
| Isolation defaults | `defaultProjectTrust: "never"` in Solo's agent dir | Pi permits this key *only* in the agent directory, and a project must not load executable extensions unprompted |
| Update trigger detection | Recorded fingerprints, not a rebuild-everything default | "Update only what is necessary" |
| Update safety | Backup, then rollback on any failure | "Must not silently leave the installation broken" |
| Version source | A `VERSION` file | The shell, the app and the updater agree without parsing Python |
| Migration mechanism | `schema_meta` + ordered statements | Exists *now* so a non-additive change has somewhere correct to live |

---

## 5. Success criteria

1. Solo installs, locates, verifies and runs **its own** Pi Agent.
2. `~/.pi` is never read or written; a full coding task completes with the global
   `pi` removed from `PATH`.
3. A bare `PI_EXECUTABLE` is refused rather than resolved.
4. Easy Installation installs and initialises the isolated runtime, and reports
   failure honestly instead of pretending.
5. `./solo --update` updates in place, rebuilding only what changed, preserving
   every persistent artefact, and rolling back on failure.
6. The Orchestrator configuration continues to work.
7. No existing behaviour regresses.
8. The Writing, Upload and Voice tiles exist; the voice indicator is animated but
   explicitly labelled as a preview.
9. Every claim is backed by a test that was actually run, with the Docker image
   still clearly marked unverified.
