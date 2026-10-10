#!/usr/bin/env bash
#
# Voice-First AI Workspace — first-time installer.
#
# Idempotent: running it again on an initialised installation will not overwrite
# user data, configuration or the admin password. It only rebuilds and restarts.
#
# Usage:
#   ./install.sh              interactive install / update
#   ./install.sh --no-start   prepare config and credentials only

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PASSWORD_FILE="$ROOT_DIR/initial-admin-password"
VOLUME_NAME="solo-data"
START=1

for arg in "$@"; do
  case "$arg" in
    --no-start) START=0 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# 1. Pre-flight checks
# --------------------------------------------------------------------------- #
log "Checking prerequisites"
command -v docker >/dev/null 2>&1 \
  || die "Docker is not installed. Install it first: https://docs.docker.com/engine/install/"
docker info >/dev/null 2>&1 \
  || die "Cannot talk to the Docker daemon. Is it running, and is your user in the 'docker' group?"
docker compose version >/dev/null 2>&1 \
  || die "The 'docker compose' plugin (v2) is required."

# --------------------------------------------------------------------------- #
# 2. Operational configuration
# --------------------------------------------------------------------------- #
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

# --------------------------------------------------------------------------- #
# 3. Port conflict check
# --------------------------------------------------------------------------- #
if command -v ss >/dev/null 2>&1; then
  if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${PORT}$"; then
    die "Port ${PORT} is already in use. Set a different APP_PORT in .env and retry."
  fi
elif command -v lsof >/dev/null 2>&1; then
  lsof -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1 \
    && die "Port ${PORT} is already in use. Set a different APP_PORT in .env and retry."
fi

# --------------------------------------------------------------------------- #
# 4. Admin password bootstrap (first run only)
# --------------------------------------------------------------------------- #
VOLUME_EXISTS=0
if docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
  VOLUME_EXISTS=1
fi

# Docker creates a directory if a bind-mount source file is missing; clean that.
if [[ -d "$PASSWORD_FILE" ]]; then
  warn "Removing the directory that Docker created at ${PASSWORD_FILE}"
  rmdir "$PASSWORD_FILE" 2>/dev/null || true
fi

GENERATED_PASSWORD=""
if [[ "$VOLUME_EXISTS" -eq 0 ]]; then
  GENERATED_PASSWORD="$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 24)"
  umask 077
  printf '%s' "$GENERATED_PASSWORD" > "$PASSWORD_FILE"
  chmod 600 "$PASSWORD_FILE"
  log "Generated a one-time admin password"
else
  rm -f "$PASSWORD_FILE" 2>/dev/null || true
  log "Existing installation detected — leaving stored credentials untouched"
fi

# --------------------------------------------------------------------------- #
# 5. Build and start
# --------------------------------------------------------------------------- #
if [[ "$START" -eq 0 ]]; then
  log "Skipping start (--no-start). Run 'docker compose up -d --build' when ready."
else
  log "Building the image (this can take a few minutes on the first run)"
  docker compose build

  log "Starting the service"
  docker compose up -d

  log "Waiting for the health check"
  for _ in $(seq 1 60); do
    if docker compose exec -T solo curl -fsS http://127.0.0.1:8080/api/health >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done

  if ! docker compose exec -T solo curl -fsS http://127.0.0.1:8080/api/health >/dev/null 2>&1; then
    warn "The service did not report healthy in time."
    warn "Inspect the logs with:  docker compose logs --tail=100"
  fi
fi

# --------------------------------------------------------------------------- #
# 6. Summary
# --------------------------------------------------------------------------- #
HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
[[ -z "$HOST_IP" ]] && HOST_IP="<server-ip>"

echo
echo "──────────────────────────────────────────────────────────────"
echo " Voice-First AI Workspace"
echo "──────────────────────────────────────────────────────────────"
echo " URL:      http://${HOST_IP}:${PORT}"
echo " Username: admin"
if [[ -n "$GENERATED_PASSWORD" ]]; then
  echo " Password: ${GENERATED_PASSWORD}"
  echo
  echo " This password is shown once. It is written to"
  echo "   ${PASSWORD_FILE}"
  echo " and is deleted automatically after the first successful start."
else
  echo " Password: unchanged (already configured)"
fi
echo
echo " Next steps"
echo "   1. Open the URL above and sign in."
echo "   2. Open Settings and add your OpenRouter and ElevenLabs credentials."
echo "   3. Create or upload a project."
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
