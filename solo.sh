#!/usr/bin/env bash
#
# Solo — native (non-Docker) lifecycle manager.
#
#   ./solo.sh install    set up Python + Node, build the UI, seed the password, start
#   ./solo.sh start      start the server in the background
#   ./solo.sh stop       stop the server
#   ./solo.sh restart    restart the server
#   ./solo.sh status     show whether it is running and healthy
#   ./solo.sh logs       follow the server log
#   ./solo.sh update     pull, reinstall dependencies, rebuild the UI, restart
#   ./solo.sh doctor     check prerequisites without changing anything
#
# Everything lives inside this repository: the virtualenv in ./venv, the built
# UI in ./frontend/dist and all state in ./data.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/venv"
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
DATA_DIR="$ROOT_DIR/data"
PID_FILE="$DATA_DIR/solo.pid"
LOG_FILE="$DATA_DIR/solo.log"
PASSWORD_FILE="$DATA_DIR/initial-admin-password"
MIN_PYTHON="3.10"
MIN_NODE_MAJOR=20

# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #
log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

# Generate a 24-character random password.
#
# Deliberately avoids `tr -dc ... < /dev/urandom | head -c N`: `head` exits
# early, `tr` dies of SIGPIPE, and under `set -o pipefail` that aborts the
# whole script. `head -c` on /dev/urandom is safe because there is no writer
# process to kill, and `od`/`cut` consume their entire input.
generate_password() {
  if have python3; then
    python3 -c 'import secrets,string;a=string.ascii_letters+string.digits;print("".join(secrets.choice(a) for _ in range(24)))'
  else
    head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n' | cut -c1-24
  fi
}

# --------------------------------------------------------------------------- #
# Prerequisite checks
# --------------------------------------------------------------------------- #
require_python() {
  have python3 || die "python3 is required. Install Python ${MIN_PYTHON}+ and retry."
  python3 - "$MIN_PYTHON" <<'PY' || die "Python ${MIN_PYTHON}+ is required (found $(python3 -V 2>&1))."
import sys
want = tuple(int(part) for part in sys.argv[1].split("."))
sys.exit(0 if sys.version_info[: len(want)] >= want else 1)
PY
}

require_node() {
  if ! have node || ! have npm; then
    die "Node.js ${MIN_NODE_MAJOR}+ and npm are required to build the web UI.
     Install Node from https://nodejs.org or your package manager, then retry.
     (Docker avoids this: ./install.sh --docker)"
  fi
  local major
  major="$(node -p 'process.versions.node.split(".")[0]')"
  [[ "$major" -ge "$MIN_NODE_MAJOR" ]] \
    || die "Node ${MIN_NODE_MAJOR}+ is required (found $(node -v))."
}

require_curl() {
  have curl || die "curl is required. Install it and retry."
}

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
load_env() {
  if [[ ! -f "$ROOT_DIR/.env" ]]; then
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
    chmod 600 "$ROOT_DIR/.env"
    log "Created .env from .env.example"
  fi
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
  APP_PORT="${APP_PORT:-8080}"
  BASE_URL="http://127.0.0.1:${APP_PORT}"
}

# --------------------------------------------------------------------------- #
# Build steps
# --------------------------------------------------------------------------- #
ensure_venv() {
  if [[ ! -x "$PYTHON" ]]; then
    log "Creating the Python virtual environment"
    python3 -m venv "$VENV_DIR"
  fi
  log "Installing backend dependencies"
  "$PIP" install --quiet --upgrade pip
  "$PIP" install --quiet -r "$ROOT_DIR/backend/requirements.txt"
  ok "Backend dependencies ready"
}

ensure_frontend() {
  require_node
  log "Installing and building the web UI"
  (
    cd "$ROOT_DIR/frontend"
    if [[ -f package-lock.json ]]; then
      npm ci --no-audit --no-fund
    else
      npm install --no-audit --no-fund
    fi
    npm run build
  )
  ok "Web UI built into frontend/dist"
}

ensure_password() {
  mkdir -p "$DATA_DIR"
  chmod 700 "$DATA_DIR" 2>/dev/null || true
  # Only bootstrap on a genuinely fresh install: once the database exists the
  # admin account is already configured and the password must not be replaced.
  if [[ -f "$DATA_DIR/app.db" ]]; then
    return 0
  fi
  if [[ -f "$PASSWORD_FILE" ]]; then
    return 0
  fi
  local password
  password="$(generate_password)"
  umask 077
  printf '%s' "$password" >"$PASSWORD_FILE"
  chmod 600 "$PASSWORD_FILE"
  GENERATED_PASSWORD="$password"
}

# --------------------------------------------------------------------------- #
# Process control
# --------------------------------------------------------------------------- #
is_running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

wait_for_health() {
  local attempts="${1:-60}"
  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "${BASE_URL}/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

# True when something is already listening on APP_PORT.
#
# Avoids `... | grep -q`: grep exits on the first match, the upstream command
# dies of SIGPIPE, and `set -o pipefail` then reports failure — which would
# silently turn a real port conflict into a false negative.
port_in_use() {
  local listeners
  if have ss; then
    listeners="$(ss -ltn 2>/dev/null | awk '{print $4}' || true)"
    grep -qE "[:.]${APP_PORT}$" <<<"$listeners"
  elif have lsof; then
    lsof -iTCP:"$APP_PORT" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}

start_solo() {
  load_env
  is_running && { ok "Already running (pid $(cat "$PID_FILE"))."; return 0; }

  [[ -x "$PYTHON" ]] || die "Virtualenv missing. Run: ./solo.sh install"
  [[ -f "$ROOT_DIR/frontend/dist/index.html" ]] \
    || die "The web UI is not built. Run: ./solo.sh install"

  if port_in_use; then
    die "Port ${APP_PORT} is already in use. Set a different APP_PORT in .env."
  fi

  ensure_password

  mkdir -p "$DATA_DIR"
  log "Starting Solo on ${BASE_URL}"
  (
    cd "$ROOT_DIR"
    export PYTHONPATH="$ROOT_DIR/backend"
    export FRONTEND_DIST="$ROOT_DIR/frontend/dist"
    export APP_DATA_DIR="${APP_DATA_DIR:-$DATA_DIR}"
    nohup "$PYTHON" -m app >>"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
  )

  if wait_for_health; then
    ok "Server is healthy"
  else
    warn "The server did not report healthy within 30 seconds."
    warn "Inspect the log: ./solo.sh logs"
  fi
  print_access
}

stop_solo() {
  if ! is_running; then
    ok "Not running."
    rm -f "$PID_FILE"
    return 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  log "Stopping Solo (pid ${pid})"
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 40); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  ok "Stopped"
}

status_solo() {
  load_env
  if is_running; then
    ok "Running (pid $(cat "$PID_FILE")) on ${BASE_URL}"
    if curl -fsS "${BASE_URL}/api/health" 2>/dev/null; then
      echo
    else
      warn "Process alive but /api/health is not responding."
    fi
  else
    warn "Not running."
  fi
}

print_access() {
  local ip
  ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  echo
  echo "──────────────────────────────────────────────────────────────"
  echo " Solo is running"
  echo "──────────────────────────────────────────────────────────────"
  echo " Local:  ${BASE_URL}"
  [[ -n "$ip" ]] && echo " LAN:    http://${ip}:${APP_PORT}"
  echo " User:   admin"
  if [[ -n "${GENERATED_PASSWORD:-}" ]]; then
    echo " Pass:   ${GENERATED_PASSWORD}"
    echo
    echo " Shown once. It is stored at ${PASSWORD_FILE} and is deleted"
    echo " automatically after the first successful start."
  else
    echo " Pass:   unchanged (already configured)"
  fi
  echo
  echo " Logs:   ./solo.sh logs"
  echo " Stop:   ./solo.sh stop"
  echo "──────────────────────────────────────────────────────────────"
}

# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
cmd_doctor() {
  log "Checking prerequisites"
  require_python && ok "python3 $(python3 -V 2>&1 | awk '{print $2}')"
  if have node; then ok "node $(node -v)"; else warn "node not found (no Docker fallback configured)"; fi
  if have curl; then ok "curl available"; else warn "curl not found"; fi
  if have docker && docker info >/dev/null 2>&1; then
    ok "docker daemon reachable (you could use ./install.sh --docker)"
  else
    warn "docker not usable here — the native install will be used"
  fi
  [[ -d "$VENV_DIR" ]] && ok "virtualenv present" || warn "virtualenv missing (run ./solo.sh install)"
  [[ -f "$ROOT_DIR/frontend/dist/index.html" ]] && ok "web UI built" || warn "web UI not built"
  [[ -f "$ROOT_DIR/.env" ]] && ok ".env present" || warn ".env missing (will be created)"
}

cmd_install() {
  log "Installing Solo (native)"
  require_python
  require_curl
  load_env
  ensure_venv
  ensure_frontend
  start_solo
}

cmd_update() {
  log "Updating Solo"
  load_env
  if [[ -d "$ROOT_DIR/.git" ]]; then
    git -C "$ROOT_DIR" pull --ff-only
  else
    warn "Not a git checkout; skipping 'git pull'."
  fi
  ensure_venv
  ensure_frontend
  stop_solo || true
  start_solo
}

cmd_logs() {
  [[ -f "$LOG_FILE" ]] || die "No log yet at ${LOG_FILE}. Start the server first."
  tail -n 200 -f "$LOG_FILE"
}

usage() {
  sed -n '3,16p' "$0"
}

case "${1:-}" in
  install) cmd_install ;;
  start)   start_solo ;;
  stop)    stop_solo ;;
  restart) stop_solo; start_solo ;;
  status)  status_solo ;;
  logs)    cmd_logs ;;
  update)  cmd_update ;;
  doctor)  cmd_doctor ;;
  ""|-h|--help|help) usage ;;
  *) die "Unknown command: $1 (try ./solo.sh help)" ;;
esac
