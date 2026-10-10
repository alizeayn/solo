# 27 — Summary: Runtime Isolation and In-Place Updates

**Stage:** Summary
**Date:** 2026-10-10
**Milestone:** Solo owns its Pi Agent; Solo updates in place
**Status:** ✅ Complete and verified with the global installation removed from `PATH`

---

## 1. The root cause, in one paragraph

Solo resolved its coding agent with `shutil.which("pi")` and defaulted Pi's
configuration directory to `~/.pi/agent`. The `pi` on this machine lives under an
nvm directory that is only on `PATH` while nvm is active in that shell, so a
background-started Solo could not find it — and when it *did* find it, it used
the user's installation and **had already written a credential into
`~/.pi/agent/auth.json`**. The design was justified in Phase 2 by the finding
"a fresh agent directory has zero models". That finding was incomplete: a fresh
directory has no models because it is *unauthenticated*. With one credential it
reports **401** models from the package's bundled catalogs. Isolation therefore
costs nothing, and the corrected experiment made the requested design both
possible and obviously right.

---

## 2. What Solo looks like now

```
<data>/pi-runtime/          Solo's own Pi Agent (npm prefix, pinned to 1.1.0)
    node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js
    runtime.json            version, node path, installed_at, last_error
<data>/pi/agent/            PI_CODING_AGENT_DIR — Solo's Pi configuration
    auth.json               credentials entered in Solo's Settings UI (mode 600)
    settings.json           defaultProjectTrust=never
    models-store.json       Solo's own catalog
<data>/install.json         version, previous_version, commit, fingerprints
<data/backups/              pre-update snapshots of db, key, secrets, .env
```

Solo is invoked as `node <absolute cli.js>` — never the `.bin/pi` shim, whose
`#!/usr/bin/env node` would reintroduce the `PATH` dependency being removed.

| Guarantee | Enforced by | Verified by |
|---|---|---|
| `PATH` is never consulted | `resolve_argv()` returns an absolute pair or nothing | a `pi` on `PATH` is ignored; 39/39 live checks with `pi` absent |
| `~/.pi` is never touched | the agent directory always resolves inside Solo | `~/.pi` hashed before/after a credential cycle: identical |
| A bare `PI_EXECUTABLE` cannot cause a silent fallback | bare names are refused and explained | dedicated test |
| `installed` never implies `verified` | `verified` requires actually starting the runtime | separate states in the API and the UI |

---

## 3. Updates

`./solo --update` fetches `origin`, refuses a dirty tree, backs up the database,
key, secrets and `.env`, and then rebuilds **only what changed** — backend
dependencies, frontend dependencies, the web UI, Solo's Pi runtime and database
migrations each have their own recorded fingerprint. If anything fails it rolls
the checkout and the data back and restarts the previous version.

Verified end to end against a temporary upstream:

| Check | Result |
|---|---|
| Version moves | `2.2.0 → 2.7.0` |
| `previous_version` is correct | `2.7.0` for the `2.7.0 → 2.8.0` step |
| Persistent data preserved | `app.db`, `master.key`, `.env` **byte-for-byte identical** |
| Backup written before the change | `data/backups/pre-update-<ts>/` with db, key, secrets, `.env`, manifest |
| Migrations applied and reported | `schema 1 → 1 (no changes)` |
| **Incremental** | a version-only update performed **0** rebuild steps |
| Dirty tree refused | clear error, nothing overwritten |

Versioning: `VERSION` (the code), `data/install.json` (this installation),
`/api/health` (the running process), `./solo.sh version` (both, plus commits
behind). Semantic, with `describe_change` turning `2.2.0 → 2.3.0` into "feature
update".

---

## 4. Workspace tiles

| Tile | What was added |
|---|---|
| **Pi Agent** | A runtime card answering *"is it ready?"* in one glance, with a provenance line stating the runtime is Solo's own copy, the dirs/executable/Node/sessions, and Install-repair / Verify / Refresh-catalog actions |
| **Write** | A focused writing surface: open a file by path, edit, revert, save, and upload. Backed by a security boundary that validates every path inside the project root and refuses to write `.solo/` or `.git/` |
| **Upload** | Part of the Write tile; the server reduces a browser filename to a basename and rejects hidden names, traversal and oversize files |
| **Voice** | `VoiceOrb` — a CSS-only animated orb (breathing core, animated waveform, staggered ripples) that respects `prefers-reduced-motion`, and is **explicitly labelled a preview** in the pill, the hint and the accessible name |

---

## 5. Tests and results

| Suite | Before | **After** |
|---|---|---|
| Backend | 288 | **339** |
| Frontend | 68 | **82** |
| Simulator end-to-end | 53 | 53 |
| Live end-to-end | 26 | **39** |

**513 checks passing** (339 + 82 + 39 + 53). The most important single result is
the one run with `pi` absent from `PATH`:

```
$ command -v pi
NOT FOUND
$ ./scripts/e2e-live.sh
  ✓ Solo's own Pi Agent runtime installed and verified
  ✓ runtime is isolated (source=managed)
  ✓ Solo's credential file is separate from the host's
  ✓ hello_world.py exists … contains the requested text
 Result: 39 passed, 0 failed
```

**Seven defects** found and fixed (D-17…D-23). Two were product defects in new
code; the other five were in the verification, which is itself a finding: three
of the seven were the *test* being wrong in a way that pointed at the product.
The sharpest is D-17 — the verification step added to prove the runtime works
was the one thing that did not, and it reported a perfectly installed runtime as
broken.

---

## 6. How to update an existing installation

```bash
cd ~/Desktop/solo          # the directory you cloned
git remote -v              # must show an origin you can fetch from

./solo --update            # fetch, update incrementally, restart, report
./solo.sh version          # installed vs available
./solo.sh doctor           # prerequisites, including Pi runtime isolation
```

Nothing else is required: no package manager, no reinstall, no deletion. Projects,
memory, sessions, credentials and provider configuration are all preserved, and a
failed update rolls back rather than leaving a partial state. Full detail,
including manual rollback and restoring a backup: [docs/updating.md](../../docs/updating.md).

---

## 7. Remaining limitations

1. **The Docker image was not built** (D-08 — no daemon access). The Dockerfile
   now bakes the pinned Pi runtime into the image and puts Pi's configuration in
   the volume; that step is unverified.
2. **No version-range compatibility gate.** The updater detects what changed and
   refuses a diverged history, but does not yet refuse "too old for this release".
3. **Workspaces are not in the pre-update backup** — deliberate, since they are
   the user's own files and can be large; `scripts/backup.sh` covers them.
4. **The live test needs a credential.** Because Solo's Pi configuration is
   isolated, the test seeds one through Solo's own API (from the machine's
   existing Pi credential, or `PI_TEST_API_KEY`). Without one it reports the
   isolation results and skips the coding task.
5. **The voice indicator is a placeholder.** No audio is processed, and the UI
   says so in three places.
6. **Pi is not sandboxed.** Solo bounds *which* directories can be opened, not
   what Pi may do inside one.

---

## 8. Conclusion

The reported bug and the underlying request were the same problem seen from two
angles: Solo was looking for its coding agent in the wrong place, and finding it
there meant using — and modifying — an installation that was not its own. Fixing
that required no cleverness, only acting on the correct facts: resolve an
absolute path inside Solo, keep Pi's configuration inside Solo, and let Pi's own
bundled catalogs supply models once Solo has its own credential. The assumption
that had blocked it turned out to be a half-finished experiment.

The update mechanism is the other half of the same idea: an installation you own
should be maintainable. It rebuilds what changed rather than everything, backs up
before it touches anything, and rolls back if it cannot finish — so the failure
mode is "still the old version", never "somewhere between the two".

The honest summary of the verification is that the product defects were fewer
than the verification defects, and that the single most valuable test was the
one run with the global `pi` deleted from `PATH`. Anyone can reproduce it in one
command, and it is now the shipped acceptance test for this guarantee.
