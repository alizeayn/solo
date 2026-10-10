# Deployment

Target: a Linux server with Docker and the Compose v2 plugin.

---

## 1. Install

```bash
git clone https://github.com/alizeayn/solo.git
cd solo
./install.sh
```

The installer is idempotent. On an initialised installation it keeps `.env`,
your stored credentials and all workspaces, and only rebuilds and restarts.

Useful flags:

```bash
./install.sh --no-start   # prepare config + password, do not start
```

### What the installer does

1. Verifies Docker and `docker compose`.
2. Creates `.env` from `.env.example` (`chmod 600`) if absent.
3. Fails early if `APP_PORT` is already in use.
4. On a fresh install, generates a 24-character admin password and writes it to
   `./initial-admin-password` (`0600`), printing it once.
5. `docker compose build && docker compose up -d`.
6. Polls `/api/health` and prints the URL.

The password file is bind-mounted to `/data/initial-admin-password`. The
application reads it at startup, creates the `admin` account, and deletes it —
so the plaintext does not survive the first successful boot. Confirm with
`ls initial-admin-password` (should not exist afterwards).

If the file is absent (e.g. you ran `docker compose up` directly), the app skips
bootstrapping and the UI shows the first-run setup screen instead.

---

## 2. Configuration

Edit `.env`, then `docker compose up -d`.

| Variable | Default | Notes |
|---|---|---|
| `APP_PORT` | `8080` | Host port mapped to the container. |
| `SESSION_TTL_HOURS` | `168` | Session lifetime. |
| `MAX_UPLOAD_MB` | `200` | Rejected with HTTP 413 above this. |
| `LOG_LEVEL` | `INFO` | `DEBUG` for diagnosis; secrets stay redacted. |

Do **not** put API keys in `.env`. They are entered in the Settings UI and
stored encrypted inside the data volume.

---

## 3. Data and persistence

Everything stateful lives in the named volume `solo-data`, mounted at `/data`:

```
/data/
├── app.db            SQLite database (WAL mode)
├── master.key        Fernet key, 0600 — needed to decrypt secrets
├── secrets.enc       Encrypted API keys
├── workspaces/       One directory per project
└── uploads/          Transient ZIP upload staging
```

`master.key` and `app.db` are useless apart: losing the key makes stored
credentials undecryptable, and losing the database loses the ciphertext. Back
up the whole volume.

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
| Badge "Pi" grey | `pi` binary unavailable to the process | Expected in the Phase 1 image; relevant from Phase 2. |

### Running without Docker

```bash
python3 -m venv venv
./venv/bin/pip install -r backend/requirements.txt
(cd frontend && npm ci && npm run build)
cd backend
APP_ENV=production APP_DATA_DIR=/var/lib/solo \
  FRONTEND_DIST="$PWD/../frontend/dist" \
  ../venv/bin/python -m app
```

Put this behind systemd (or the reverse proxy above) and run it as an
unprivileged user.
