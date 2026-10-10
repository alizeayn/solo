# 07 — End-to-End Verification

**Stage:** Testing
**Date:** 2026-10-10
**Command:** `./scripts/e2e.sh`
**Result:** ✅ **26 passed, 0 failed**

---

## 1. Method

`scripts/e2e.sh` starts a **real** uvicorn process — not a `TestClient` — on a
throwaway port with a temporary data directory, the production frontend build,
and an installer-style bootstrap password. It then exercises the critical path
over real HTTP with `curl`, asserting on responses and on the database file
itself. The process and its data directory are removed on exit.

This is deliberately different from the pytest suite: it proves that the
assembly works as a running service (lifespan, SPA mount, cookie handling,
environment configuration), not merely that units behave.

---

## 2. Recorded output

```
▸ Starting the server on port 8099

▸ Health endpoint
  ✓ status is ok
  ✓ database reachable
  ✓ health leaks no secrets

▸ Authentication is enforced
  ✓ unauthenticated request rejected (401)

▸ Bootstrap admin login
  ✓ admin auto-created from installer password
  ✓ authenticated request accepted

▸ Settings are masked
  ✓ raw API key is never returned
  ✓ secret reported as configured
  ✓ secret encrypted at rest

▸ Project creation
  ✓ project created (c6495e44…)

▸ Zip-slip upload is rejected
  ✓ malicious archive rejected (400)
  ✓ no file escaped the workspace

▸ Question is answered without starting a coding task
  ✓ question classified as CHAT_OR_EXPLAIN
  ✓ answer derived from the project snapshot

▸ Coding task runs to completion with normalised events
  ✓ task created (16af0384…)
  ✓ task reached COMPLETED
  ✓ event present: run.started
  ✓ event present: file.changed
  ✓ event present: test.result
  ✓ event present: run.finished
  ✓ event present: task.status_changed
  ✓ result summary recorded

▸ Follow-up steering while a task is running
  ✓ follow-up routed sensibly (STEER_ACTIVE_TASK)

▸ Single-page app is served from the same origin
  ✓ index.html served at /
  ✓ OpenAPI docs available at /api/docs

▸ Task state is persisted in SQLite
  persisted status: COMPLETED
  ✓ persisted task state verified
──────────────────────────────────────────────────────────────
 Result: 26 passed, 0 failed
──────────────────────────────────────────────────────────────
```

Every check is an assertion, not a printout: `pass()` and `fail()` increment
counters and the script exits non-zero if anything failed. A failed run dumps
the last 60 lines of the server log.

---

## 3. Strong assertions worth highlighting

| Check | Why it is strong |
|---|---|
| `secret encrypted at rest` | Runs `grep -rq "sk-or-v1-e2e-secret-key" "$DATA_DIR/app.db"` and **fails if the plaintext appears anywhere in the database file**. This is a direct test of the encryption guarantee, not of the API's masking. |
| `no file escaped the workspace` | Builds a ZIP containing `../escaped.txt`, uploads it, then asserts `"${DATA_DIR}/escaped.txt"` **does not exist**. It tests the filesystem outcome, not the HTTP status alone. |
| `raw API key is never returned` | Greps the full settings response body for the submitted key. |
| `admin auto-created from installer password` | Proves the whole bootstrap chain: env var → consumed password → account created → password file lifecycle. |
| `event present: …` (5 types) | Asserts the normalized vocabulary reaches the API, not raw provider output. |
| `persisted status verified` | Opens the SQLite file directly with `sqlite3` from Python and asserts `status == 'COMPLETED'` **and** that `result_summary` is non-empty. It bypasses the API entirely to confirm durable storage. |
| `index.html served at /` | Confirms the static SPA mount coexists with, and does not shadow, the API routes. |

---

## 4. Independent runtime verification (Dockerfile stage 2 reproduction)

To compensate for being unable to build the image (**D-08**), the Dockerfile's
runtime stage was reproduced natively in a clean virtual environment containing
**only** `backend/requirements.txt`:

| Observation | Result |
|---|---|
| `pip install -r backend/requirements.txt` into a fresh venv | ✅ `RUNTIME_DEPS_OK` — the runtime dependency set is complete and sufficient |
| `python -m app` (the exact container `CMD`) with `APP_ENV=production` | ✅ started and served |
| `GET /api/health` | ✅ `{"status":"ok","version":"0.1.0","database":true,"workspaces_dir":true,"coding_agent":"mock","pi_version":"1.1.0"}` |
| `POST /api/auth/login` with the bootstrap password | ✅ `{"initialized":true,"authenticated":true,"username":"admin"}` |
| `GET /` with `FRONTEND_DIST` set | ✅ `<!doctype html>…` — SPA served |
| Session cookie attributes in production mode | ✅ `HttpOnly` **and** `Secure` present |
| Pi runtime probe | ✅ detected `1.1.0` from a separate process |

This confirms that nothing test-only leaked into the production dependency set,
and that the container's start command and environment contract are correct.

---

## 5. Frontend production build verification

```
dist/index.html                   0.59 kB │ gzip:   0.34 kB
dist/assets/index--Qkn24c5.css  139.47 kB │ gzip:  13.10 kB
dist/assets/index-D995TE_m.js   644.84 kB │ gzip: 166.92 kB
✓ built in 248ms
```

Reproduced after a clean `npm ci` against the committed lockfile — the same
operation the Docker build performs — so the lockfile is verified complete and
consistent.

---

## 6. Verification matrix

| Layer | Artefact verified | Method | Result |
|---|---|---|---|
| Unit | 123 backend tests | pytest | ✅ |
| Unit | 22 frontend tests | Vitest | ✅ |
| Types | 20 TS modules | `tsc --noEmit`, `strict` | ✅ 0 errors |
| Integration | API + DB + WebSocket | TestClient with lifespan | ✅ |
| System | Real uvicorn + real SPA + real SQLite | `scripts/e2e.sh` | ✅ 26/26 |
| Runtime deps | Container dependency set | Fresh venv, `python -m app` | ✅ |
| Build | Frontend bundle | `npm ci && npm run build` | ✅ |
| Scripts | 4 shell scripts | `bash -n` | ✅ |
| Compose | `docker-compose.yml` | `docker compose config --quiet` | ✅ |
| Container image | `Dockerfile` | `docker compose build` | ⚠️ not executable here (D-08) |

Nine of ten verification layers pass. The tenth is blocked by an environment
permission, is documented with a reproduction command, and its constituent steps
all pass individually.
