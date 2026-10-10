# Deployment

Solo runs two ways, and `install.sh` picks the right one automatically:

| Path | When | Needs |
|---|---|---|
| **Native** | Docker is unavailable, or `--native` | Python 3.10+, Node 20+, `curl` |
| **Docker** | The Docker daemon is reachable, or `--docker` | Docker Engine + Compose v2 |

Both install into the checkout folder and both are idempotent.

---

## 1. Install

```bash
# Native (personal machine)
./install.sh --native

# Docker (server)
./install.sh --docker

# Let the installer decide
./install.sh
```

### Native install

`install.sh --native` delegates to `solo.sh install`, which:

1. verifies Python 3.10+ and Node 20+,
2. creates `venv/` and installs `backend/requirements.txt`,
3. runs `npm ci && npm run build` to produce `frontend/dist/`,
4. creates `.env` from `.env.example` (mode `600`) when missing,
5. on a fresh install, generates a one-time admin password into
   `data/initial-admin-password` (mode `600`) and prints it,
6. starts the server in the background (`data/solo.pid`, `data/solo.log`),
7. waits for `/api/health` and prints the URL.

The application consumes and deletes the password file on first boot. Confirm
with `ls data/initial-admin-password` (should not exist).

Day-2 operations:

```bash
./solo.sh status | start | stop | restart | logs | update | doctor
```

### Docker install

```bash
./install.sh --docker
```

The installer verifies Docker, creates `.env`, checks that `APP_PORT` is free,
generates the one-time admin password into `./initial-admin-password`
(bind-mounted to `/data/initial-admin-password`, consumed and deleted on first
boot), builds the image, starts the service and waits for the health check.

> If Docker creates a *directory* at the bind-mount path (what happens when the
> source file is missing), Solo treats it as "no bootstrap password" and shows
> the first-run setup screen instead of failing.

---

## 2. Configuration

Edit `.env`, then `docker compose up -d`.

| Variable | Default | Notes |
|---|---|---|
| `APP_PORT` | `8080` | Host port mapped to the container. |
| `SESSION_TTL_HOURS` | `168` | Session lifetime. |
| `SESSION_COOKIE_SECURE` | *(auto)* | `Secure` flag; auto sets it only over HTTPS. |
| `MAX_UPLOAD_MB` | `200` | Rejected with HTTP 413 above this. |
| `LOG_LEVEL` | `INFO` | `DEBUG` for diagnosis; secrets stay redacted. |
| `METADATA_DIR_NAME` | `.solo` | Per-project state folder name. |
| `PROJECT_ROOTS` | *(empty)* | `:`-separated extra roots Open Project may read. |
| `ALLOW_ANY_PROJECT_PATH` | `true` | Set `false` to restrict opening to `PROJECT_ROOTS` + home + managed workspaces. |

Do **not** put API keys in `.env`. They are entered in the Settings UI and
stored encrypted inside the data directory.

### Project path policy on a shared server

The default (`ALLOW_ANY_PROJECT_PATH=true`) is designed for a personal,
local-first install: any readable folder may be opened. On a server that others
can reach, lock it down:

```bash
# .env
ALLOW_ANY_PROJECT_PATH=false
PROJECT_ROOTS=/srv/projects:/opt/repos
```

With that set, Open Project accepts only folders inside those roots (plus the
home directory and Solo's managed workspaces folder). `/proc`, `/sys`, `/dev`,
`/etc`, `/boot`, `/run`, `/root` and the Solo `data/` directory are rejected in
either mode. See [projects.md](projects.md#6-the-path-policy).

---

## 3. Data and persistence

Everything stateful lives in `data/` (native) or the `solo-data` volume mounted
at `/data` (Docker):

```
/data/
├── app.db            SQLite database (WAL mode)
├── master.key        Fernet key, 0600 — needed to decrypt secrets
├── secrets.enc       Encrypted API keys
├── workspaces/       Projects created or imported by Solo
└── uploads/          Transient ZIP upload staging
```

Projects **opened in place** live wherever they already are; only a `.solo/`
folder is added there. `master.key` and `app.db` are useless apart: losing the
key makes stored credentials undecryptable, and losing the database loses the
ciphertext. Back up the whole data directory.

> A backup taken with `./scripts/backup.sh` covers the Docker volume only.
> Projects opened in place outside it are not included — back those up with
your normal file backups.

---

## 4. Backup and restore

```bash
./scripts/backup.sh                       # -> ./backups/solo-backup-<utc>.tar.gz
./scripts/backup.sh /mnt/backups          # custom destination
./scripts/restore.sh backups/solo-backup-20261010T120000Z.tar.gz
./scripts/restore.sh <archive> --yes      # skip the confirmation prompt
```

Restore stops the service, empties the volume, extracts the archive and starts
the service again. It refuses to run without typing `restore` unless `--yes` is
given. Archives are written `0600` because they contain the encryption key.

---

## 5. Updating

```bash
git pull
docker compose up -d --build
```

The volume, and therefore all state, is untouched. If a release changes the
schema, a migration step will be documented here; the MVP creates tables
idempotently and makes additive-only changes.

---

## 6. HTTPS

The app speaks plain HTTP. Credentials and session cookies must not cross a
public network unencrypted, so terminate TLS in front of it.

### Example: nginx + Let's Encrypt

```nginx
server {
    listen 443 ssl http2;
    server_name workspace.example.com;

    ssl_certificate     /etc/letsencrypt/live/workspace.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/workspace.example.com/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # Required for the application WebSocket.
        proxy_set_header   Upgrade    $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}

server {
    listen 80;
    server_name workspace.example.com;
    return 301 https://$host$request_uri;
}
```

Set `APP_ENV=production` in `.env` so session cookies carry `Secure`. Because
the frontend is served from the same origin, no CORS configuration is needed.

Alternatives: Caddy (automatic certificates), Traefik, or a tunnel such as
Cloudflare Tunnel / Tailscale for private access without exposing a port.

---

## 7. Operations

```bash
docker compose logs -f --tail=200     # logs (secrets are redacted)
docker compose ps                     # status + health
docker compose restart                # restart
docker compose down                   # stop (volume kept)
docker compose down -v                # stop and DELETE all data — careful
```

The container has a health check hitting `/api/health`, a restart policy of
`unless-stopped`, a non-root user, and `no-new-privileges`.

### Monitoring

Poll `GET /api/health`. `status: "ok"` means the database and the workspaces
directory are both usable; `"degraded"` means one of them is not.

---

## 8. Failure modes

| Message / symptom | Meaning | Fix |
|---|---|---|
| `Docker is not installed` | No `docker` on `PATH` | Install Docker Engine. |
| `Cannot talk to the Docker daemon` | User not in the `docker` group, or the daemon is down | `sudo usermod -aG docker $USER`, re-login; `sudo systemctl start docker`. |
| `The 'docker compose' plugin (v2) is required` | Compose v1 or missing plugin | Install `docker-compose-plugin`. |
| `Port <n> is already in use` | Something else is listening | Change `APP_PORT`, or stop the other service. |
| Container unhealthy | App failed to start | `docker compose logs --tail=100`. |
| `unable to decrypt stored secret` in logs | `master.key` does not match `secrets.enc` (partial restore) | Re-enter the keys in Settings, or restore a matching backup. |
| `that location is not allowed` when opening a project | A blocked system path, the Solo `data/` directory, or outside `PROJECT_ROOTS` with `ALLOW_ANY_PROJECT_PATH=false` | Choose a folder under an allowed root, or widen `PROJECT_ROOTS`. |
| `cannot write project metadata` | The project folder is not writable by the Solo process | Fix ownership/permissions, or open a different folder. |
| Badge "Pi" grey | `pi` binary unavailable to the process | Expected in the Phase 1 image; relevant from Phase 2. |

### Running without Docker

```bash
./solo.sh install          # or: ./install.sh --native
./solo.sh start
```

Manually:

```bash
cd "$(git rev-parse --show-toplevel)"
python3 -m venv venv
./venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm ci && npm run build)
PYTHONPATH="$PWD/backend" APP_DATA_DIR="$PWD/data" \
  FRONTEND_DIST="$PWD/frontend/dist" ./venv/bin/python -m app
```

Running from the repository **root** matters: the backend reads `.env` from the
working directory and resolves `./data` relative to it.

Put this behind systemd (or the reverse proxy above) and run it as an
unprivileged user. `./solo.sh` already manages the PID file, log and restart.
