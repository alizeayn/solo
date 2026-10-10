# Updating Solo

Solo updates **in place**. Projects, memory, sessions, credentials, provider
configuration and workspace state all survive, and nothing has to be reinstalled
from scratch.

---

## 1. The commands

```bash
cd ~/Desktop/solo        # wherever you cloned it
./solo --update          # or: ./solo.sh update
```

`./solo` is a symlink to `./solo.sh`, so `solo --update`, `solo update` and
`solo.sh update` are the same command.

Useful variants:

```bash
./solo.sh update --no-restart   # apply changes, restart later yourself
./solo.sh update --force        # allow a dirty tree, or reset a diverged branch
./solo.sh version               # installed vs available version, commits behind
./solo.sh update                # the normal update
```

Prerequisites: the checkout must be a git clone with an `origin` remote you can
fetch from. No package manager is involved, and your `.env` and `data/` are never
overwritten.

---

## 2. What an update actually does

```
1  check        git checkout?  origin configured?  fetch origin
2  compare      same commit → "already up to date", done
3  guard        refuse to overwrite uncommitted work (unless --force)
4  back up      app.db, master.key, secrets.enc, .env → data/backups/pre-update-<ts>
5  pull         fast-forward only; a diverged branch refuses and explains
6  detect       compare recorded fingerprints to decide what to rebuild
7  rebuild      only the affected parts (see below)
8  migrate      apply pending schema migrations, and report them
9  restart      start the new version and wait for /api/health
10 record       version, commit, fingerprints → data/install.json
```

If **any** of steps 6–9 fails, the updater rolls the checkout back to the
previous commit, restores the backed-up data, reinstalls the previous
dependencies and restarts the old version. It never leaves a partial state, and
it tells you where the backup is.

### Step 6 — what gets rebuilt, and what does not

| Recorded fingerprint changed | Action |
|---|---|
| `backend/requirements.txt` | `pip install -r backend/requirements.txt` |
| `frontend/package-lock.json` | `npm ci` |
| the frontend sources | `npm run build` |
| the pinned Pi Agent version | reinstall Solo's Pi runtime, then verify it starts |
| neither of the above | **restart only** — no dependency work at all |

Verified in practice: an update whose only change was `VERSION` reported
*"No dependency or build changes detected — restarting only"* and performed zero
rebuild steps.

### What is never touched

`data/` (database, encryption key, encrypted secrets, workspaces, Solo's Pi
runtime and Pi configuration), `.env`, and any file you have modified yourself —
the updater refuses to run on a dirty working tree rather than overwriting it.

---

## 3. Versioning

| Where | What |
|---|---|
| `VERSION` (repository root) | The version of the code in the checkout |
| `data/install.json` | What this installation is on: version, commit, previous version, fingerprints, timestamps |
| `GET /api/health` | The running version, plus `pi_isolated` and `schema_version` |
| `./solo.sh version` | Both, side by side, with commits behind |

Semantic versioning:

- **MAJOR** — an incompatible change to stored data or configuration
- **MINOR** — a new capability (a phase)
- **PATCH** — fixes and internal changes

`previous_version` is the version that was replaced, so an update report reads
`2.2.0 → 2.3.0` rather than leaving you to work it out.

---

## 4. Database migrations

`schema_meta` records the schema version; `backend/app/migrations.py` holds the
ordered statements. They run automatically at startup, so both `./solo.sh start`
and `./solo.sh update` apply them, and the updater prints what changed:

```
▸ Applying database migrations
  schema 1 → 1 (no changes)
```

A failed migration leaves the recorded version untouched, so the next start
retries instead of believing it succeeded. Schema changes so far have been
additive (handled by `create_all`), which is why the mechanism currently reports
"no changes" — it exists so a non-additive change has somewhere correct to live.

---

## 5. Rolling back

An update that fails rolls back automatically. To go back deliberately:

```bash
./solo.sh stop
git log --oneline -5                 # find the commit you want
git reset --hard <commit>
./venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm ci && npm run build)
./solo.sh start
```

Your data is untouched by a rollback, which is why the checkout can be moved
freely: everything persistent lives in `data/`.

Restoring from a pre-update backup:

```bash
ls data/backups/
./solo.sh stop
cp data/backups/pre-update-<stamp>/app.db      data/app.db
cp data/backups/pre-update-<stamp>/master.key  data/master.key
cp data/backups/pre-update-<stamp>/secrets.enc data/secrets.enc
./solo.sh start
```

`master.key` and `secrets.enc` must be restored **together** — the key decrypts
the secrets.

---

## 6. Docker

```bash
docker compose pull          # if you use a published image
git pull
docker compose up -d --build
```

The `solo-data` volume holds everything persistent, so a rebuild keeps your
projects and credentials. Back it up with `./scripts/backup.sh`.

---

## 7. Failure modes

| Symptom | Cause and fix |
|---|---|
| `Local changes would be overwritten` | You have uncommitted edits. Commit or stash them, or use `--force` if you are sure. |
| `cannot be fast-forwarded (diverged history)` | The checkout has its own commits. Re-run with `--force` to reset to `origin/<branch>`. |
| `Solo was not installed from a git checkout` | The updater needs git history. Re-clone and move `data/` and `.env` across. |
| `Could not fetch from origin` | Network or credentials. Check `git -C . fetch origin` manually. |
| Update stops at the health check | The new version did not start; the updater rolled back and restarted the old one. `./solo.sh logs` shows why. |
| `The server did not report healthy` | Same as above; the previous version is running. |
| Pi Agent reports "not installed" after an update | The runtime is reinstalled only when its pinned version changes. Run `./solo.sh install`, or *Install / repair* in Settings → Pi Agent. |
