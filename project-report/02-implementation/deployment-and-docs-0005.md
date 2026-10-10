# 05 — Deployment and Documentation

**Stage:** Implementation
**Date:** 2026-10-10

---

## 1. Deliverables

| Artefact | Purpose |
|---|---|
| `Dockerfile` | Two-stage build: Node builds the SPA, Python serves API + SPA |
| `docker-compose.yml` | Single service, named volume, health check, non-root |
| `.dockerignore` | Keeps secrets, data, `node_modules` and reports out of the build context |
| `install.sh` | One-command first-time install; idempotent |
| `scripts/dev.sh` | Non-Docker development workflow |
| `scripts/e2e.sh` | Real-server end-to-end smoke test |
| `scripts/backup.sh` | Timestamped archive of the whole data volume |
| `scripts/restore.sh` | Restore with explicit confirmation |
| `.env.example` | Non-secret operational settings, documented |
| `README.md` | Overview, quick starts, security model, troubleshooting |
| `docs/architecture.md` | Modules, data model, event flow, extension points |
| `docs/deployment.md` | Docker, HTTPS reverse proxy, backup/restore, failure modes |
| `docs/development.md` | Dev workflow, conventions, adding an adapter, regression notes |
| `docs/api.md` | REST + WebSocket reference |

---

## 2. Single-origin design

One user-facing port. The API, the WebSocket and the built SPA are served by the
same FastAPI app; the SPA is mounted at `/` **after** every API route, so a
static mount can never shadow `/api/*`. Consequences:

- No CORS configuration is needed, and none is enabled by default.
- Session cookies are same-origin, so `SameSite=Lax` genuinely mitigates CSRF.
- In development, Vite proxies `/api` (including the WebSocket upgrade) to the
  backend, so the browser sees the same single-origin shape as production.

---

## 3. Dockerfile

Two stages:

```
node:24-alpine  ── npm ci ── npm run build ──►  dist/
                                                  │
python:3.12-slim ── pip install requirements ─────┴──►  /app/frontend/dist
```

Runtime hardening:

- Runs as a **non-root** user (`solo`, uid 10001).
- `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`, `PIP_NO_CACHE_DIR=1`.
- Only `requirements.txt` (runtime) is installed — no test tooling in the image.
- `HEALTHCHECK` polls `/api/health`.
- `/data` is the single persistent volume.
- Compose adds `security_opt: no-new-privileges:true` and
  `restart: unless-stopped`.
- No secret is ever copied into the image; `.dockerignore` excludes `.env`,
  `data/`, `*.key` and `initial-admin-password`.

---

## 4. Installer behaviour

```bash
./install.sh              # install / update
./install.sh --no-start   # prepare config and credentials only
```

Steps and their failure modes:

| Step | Check | Failure output |
|---|---|---|
| 1 | `docker` on PATH | "Docker is not installed. Install it first: …" |
| 2 | `docker info` succeeds | "Cannot talk to the Docker daemon. Is it running, and is your user in the 'docker' group?" |
| 3 | `docker compose version` | "The 'docker compose' plugin (v2) is required." |
| 4 | `.env` exists | Creates it from `.env.example` at `0600` |
| 5 | `APP_PORT` free (`ss` or `lsof`) | "Port N is already in use. Set a different APP_PORT in .env and retry." |
| 6 | Volume exists? | Fresh → generate password; existing → leave credentials untouched |
| 7 | Build + up | — |
| 8 | Poll health up to 120 s | Warns and points at `docker compose logs` |

**Idempotency.** On an existing installation the script keeps `.env`, deletes any
stale `initial-admin-password` (the account already exists), never overwrites
the volume, and simply rebuilds and restarts.

**Non-destructive password handling.** The generated password is written to
`./initial-admin-password` (`0600`), bind-mounted into the container, consumed
on first boot, and deleted by the application. A `README`-level note tells the
operator to confirm the file is gone.

**Failure to avoid.** If Docker were to create a *directory* where the password
file is expected (the usual outcome of bind-mounting a missing file), the app
would previously raise. `bootstrap_admin` now uses `is_file()` and treats a
directory as "no bootstrap password", so the app starts and shows first-run
setup instead. See **D-07**.

---

## 5. Data, backup and restore

Everything stateful lives in the `solo-data` volume:

```
/data/app.db          SQLite (WAL)
/data/master.key      Fernet key, 0600
/data/secrets.enc     encrypted API keys
/data/workspaces/     one directory per project
/data/uploads/        transient ZIP staging
```

`backup.sh` archives the whole volume to
`backups/solo-backup-<UTC>.tar.gz` at mode `0600` (it contains the encryption
key) using a throwaway `alpine` container with the volume mounted read-only.

`restore.sh` stops the service, empties the volume, extracts the archive and
restarts — refusing to proceed without the operator typing `restore`, unless
`--yes` is given.

The dependency between `master.key` and `secrets.enc` is documented explicitly:
backing up only the database loses the ability to decrypt stored credentials.

---

## 6. HTTPS guidance

`docs/deployment.md` provides a complete, copy-pasteable nginx + Let's Encrypt
configuration including the `Upgrade`/`Connection` headers and a long
`proxy_read_timeout` required by the application WebSocket.

The documentation states plainly that plain HTTP on a public IP is not safe for
entering API keys, and that `APP_ENV=production` must be set so cookies carry
`Secure`. Caddy, Traefik and tunnel-based options (Cloudflare Tunnel,
Tailscale) are named as alternatives.

---

## 7. Verification of deployment artefacts

| Check | Result |
|---|---|
| `bash -n` on all four scripts | ✅ no syntax errors |
| `docker compose config --quiet` | ✅ valid, resolved configuration |
| `npm ci` against the committed lockfile (Dockerfile stage 1) | ✅ 153 packages, reproducible |
| `npm run build` (Dockerfile stage 1 output) | ✅ 644 kB JS / 139 kB CSS |
| `pip install -r backend/requirements.txt` into a **fresh** venv (stage 2) | ✅ RUNTIME_DEPS_OK |
| App runs on runtime deps alone: `python -m app` (the Docker `CMD`) | ✅ health `ok`, Pi 1.1.0 detected, SPA served, bootstrap password consumed, `Secure` cookie in production mode |
| `docker compose build` (the image itself) | ❌ **not executable here** — see D-08 |

The image build is the one artefact that could not be executed in this
environment. Its constituent commands were each reproduced natively and passed,
which is strong but not identical evidence. The confirming command is:

```bash
docker compose build && docker compose up -d && curl -fsS localhost:8080/api/health
```

---

## 8. Documentation set

| Document | Audience | Contents |
|---|---|---|
| `README.md` | Everyone | What works today (with a phase-status table), quick starts, configuration table, security model, testing, layout, roadmap, troubleshooting table |
| `docs/architecture.md` | Engineers | Request/event diagram, module map, data model rationale, lifecycle state machine, event vocabulary, intent precedence, adapter contract, frontend state rules, extension points |
| `docs/deployment.md` | Operators | Install, config, data, backup/restore, updates, HTTPS, operations, failure modes, non-Docker deployment |
| `docs/development.md` | Contributors | Environment, running, tests, conventions, adapter recipe, four documented regression traps, DB change policy, useful commands |
| `docs/api.md` | Integrators | Every endpoint with payloads, status codes, task statuses, event types, WebSocket protocol, error format |

Each document states what is **not** yet implemented rather than implying
completeness, and every "Test connection" claim in the docs matches a real HTTP
call in `settings_service.py`.
