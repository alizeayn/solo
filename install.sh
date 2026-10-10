#!/usr/bin/env bash
#
# Solo — one-command installer.
#
#   ./install.sh                 auto: Docker when usable, otherwise native
#   ./install.sh --docker        force the Docker Compose install
#   ./install.sh --native        force a native install (Python + Node, no Docker)
#   ./install.sh --no-start      prepare configuration and credentials only
#
# Both paths are idempotent: running the installer again rebuilds and restarts
# without touching existing data, credentials or configuration.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

MODE="auto"
START=1
VOLUME_NAME="solo-data"
PASSWORD_FILE="$ROOT_DIR/initial-admin-password"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --docker)   MODE="docker" ;;
    --native)   MODE="native" ;;
    --no-start) START=0 ;;
    -h|--help)  sed -n '3,10p' "$0"; exit 0 ;;
    *) printf 'unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# Generate a 24-character random password.
#
# Deliberately avoids `tr -dc ... < /dev/urandom | head -c N`: `head` exits
# early, `tr` dies of SIGPIPE, and under `set -o pipefail` that aborts the
# whole script (which is exactly how the first native install failed silently).
generate_password() {
  if have python3; then
    python3 -c 'import secrets,string;a=string.ascii_letters+string.digits;print("".join(secrets.choice(a) for _ in range(24)))'
  elif have openssl; then
    openssl rand -base64 48 | tr -d '\n/+=' | cut -c1-24
  else
    head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n' | cut -c1-24
  fi
}

# True when something is already listening on the given port.
port_in_use() {
  local port="$1"
  local listeners
  if have ss; then
    listeners="$(ss -ltn 2>/dev/null | awk '{print $4}' || true)"
    grep -qE "[:.]${port}$" <<<"$listeners"
  elif have lsof; then
    lsof -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}

# --------------------------------------------------------------------------- #
# Mode selection
# --------------------------------------------------------------------------- #
docker_usable() {
  have docker && docker info >/dev/null 2>&1 && docker compose version >/dev/null 2>&1
}

if [[ "$MODE" == "auto" ]]; then
  if docker_usable; then
    MODE="docker"
  else
    MODE="native"
    if have docker; then
      warn "Docker is installed but the daemon is not reachable — using the native install."
      warn "For Docker: add your user to the 'docker' group, re-login, then ./install.sh --docker"
    fi
  fi
fi

# --------------------------------------------------------------------------- #
# Native install
# --------------------------------------------------------------------------- #
if [[ "$MODE" == "native" ]]; then
  log "Installing Solo natively (Python + Node, no Docker)"
  if [[ "$START" -eq 0 ]]; then
    # Prepare only: build everything, but do not leave a server running.
    ./solo.sh doctor
    log "Preparing the environment without starting the server"
    # shellcheck disable=SC1091
    set -a; [[ -f .env ]] || cp .env.example .env; source .env; set +a
    python3 -m venv venv 2>/dev/null || true
    ./venv/bin/pip install --quiet --upgrade pip
    ./venv/bin/pip install --quiet -r backend/requirements.txt
    (cd frontend && { [[ -f package-lock.json ]] && npm ci --no-audit --no-fund || npm install --no-audit --no-fund; } && npm run build)
    log "Environment ready. Start it later with: ./solo.sh start"
    exit 0
  fi
  exec ./solo.sh install
fi

# --------------------------------------------------------------------------- #
# Docker install
# --------------------------------------------------------------------------- #
have docker || die "Docker is not installed. Install it first (https://docs.docker.com/engine/install/) or use ./install.sh --native"
docker info >/dev/null 2>&1 \
  || die "Cannot talk to the Docker daemon. Start it, or add your user to the 'docker' group and re-login. Use --native to skip Docker."
docker compose version >/dev/null 2>&1 \
  || die "The 'docker compose' plugin (v2) is required. Use --native to skip Docker."

log "Installing Solo with Docker Compose"

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  log "Created .env from .env.example"
else
  log "Keeping the existing .env"
fi

# shellcheck disable=SC1091
set -a; source .env; set +a
PORT="${APP_PORT:-8080}"

if port_in_use "$PORT"; then
  die "Port ${PORT} is already in use. Set a different APP_PORT in .env and retry."
fi

VOLUME_EXISTS=0
if docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
  VOLUME_EXISTS=1
fi

# Docker creates a directory when a bind-mounted file is missing; clean that up.
if [[ -d "$PASSWORD_FILE" ]]; then
  warn "Removing the directory Docker created at ${PASSWORD_FILE}"
  rmdir "$PASSWORD_FILE" 2>/dev/null || true
fi

GENERATED_PASSWORD=""
if [[ "$VOLUME_EXISTS" -eq 0 ]]; then
  GENERATED_PASSWORD="$(generate_password)"
  umask 077
  printf '%s' "$GENERATED_PASSWORD" >"$PASSWORD_FILE"
  chmod 600 "$PASSWORD_FILE"
  log "Generated a one-time admin password"
else
  rm -f "$PASSWORD_FILE" 2>/dev/null || true
  log "Existing installation detected — leaving stored credentials untouched"
fi

if [[ "$START" -eq 0 ]]; then
  log "Skipping start (--no-start). Run 'docker compose up -d --build' when ready."
  exit 0
fi

log "Building the image (this can take a few minutes on the first run)"
docker compose build

log "Starting the service"
docker compose up -d

log "Waiting for the health check"
for _ in $(seq 1 60); do
  docker compose exec -T solo curl -fsS http://127.0.0.1:8080/api/health >/dev/null 2>&1 && break
  sleep 2
done
docker compose exec -T solo curl -fsS http://127.0.0.1:8080/api/health >/dev/null 2>&1 \
  || warn "The service did not report healthy in time. Check: docker compose logs --tail=100"

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
[[ -z "$HOST_IP" ]] && HOST_IP="<server-ip>"

echo
echo "──────────────────────────────────────────────────────────────"
echo " Solo"
echo "──────────────────────────────────────────────────────────────"
echo " URL:      http://${HOST_IP}:${PORT}"
echo " Username: admin"
if [[ -n "$GENERATED_PASSWORD" ]]; then
  echo " Password: ${GENERATED_PASSWORD}"
  echo
  echo " Shown once. It is written to ${PASSWORD_FILE} and is"
  echo " deleted automatically after the first successful start."
else
  echo " Password: unchanged (already configured)"
fi
echo
echo " Next steps"
echo "   1. Open the URL above and sign in."
echo "   2. Open Settings and add your OpenRouter and ElevenLabs credentials."
echo "   3. Create a project, or open a folder you already have."
echo
echo " Manage the service"
echo "   docker compose logs -f        follow logs"
echo "   docker compose restart        restart"
echo "   docker compose down           stop"
echo "   docker compose up -d --build  update after 'git pull'"
echo "   ./scripts/backup.sh           back up all data"
echo
warn "Before exposing this on the public internet, put it behind HTTPS"
warn "(a reverse proxy or a secure tunnel). Plain HTTP on a public IP is not"
warn "safe for entering API keys or passwords."
echo "──────────────────────────────────────────────────────────────"
