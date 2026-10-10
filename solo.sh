#!/usr/bin/env bash
#
# Solo — native lifecycle manager: install, run, and update in place.
#
#   ./solo.sh install     set up Python + Node + Solo's own Pi Agent, then start
#   ./solo.sh start       start the server in the background
#   ./solo.sh stop        stop the server
#   ./solo.sh restart     restart the server
#   ./solo.sh status      show whether it is running and healthy
#   ./solo.sh logs        follow the server log
#   ./solo.sh update      pull the latest version and update incrementally
#   ./solo.sh version     show the installed and available versions
#   ./solo.sh doctor      check prerequisites without changing anything
#
# Everything lives inside this repository: the virtualenv in ./venv, the built
# UI in ./frontend/dist, Solo's own Pi Agent in ./data/pi-runtime and all state
# in ./data. Nothing outside is modified — in particular the desktop Pi Agent
# installation and its configuration are never read or written.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/venv"
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
DATA_DIR="$ROOT_DIR/data"
PID_FILE="$DATA_DIR/solo.pid"
LOG_FILE="$DATA_DIR/solo.log"
PASSWORD_FILE="$DATA_DIR/initial-admin-password"
INSTALL_MANIFEST="$DATA_DIR/install.json"
BACKUP_DIR="$DATA_DIR/backups"
MIN_PYTHON="3.10"
MIN_NODE_MAJOR=20
DEFAULT_BRANCH="main"

# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #
log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ✓\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
step() { printf '\n\033[1;34m▸ %s\033[0m\n' "$*"; }

# Generate a 24-character random password.
#
# Deliberately avoids `tr -dc ... < /dev/urandom | head -c N`: `head` exits
# early, `tr` dies of SIGPIPE, and under `set -o pipefail` that aborts the
# whole script. `head -c` on /dev/urandom is safe because there is no writer
# process to kill, and `od`/`cut` consume their entire input.
generate_password() {
  if have python3; then
    python3 -c 'import secrets,string;a=string.ascii_letters+string.digits;print("".join(secrets.choice(a) for _ in range(24)))'
  elif have openssl; then
    openssl rand -base64 48 | tr -d '\n/+=' | cut -c1-24
  else
    head -c 48 /dev/urandom | od -An -tx1 | tr -d ' \n' | cut -c1-24
  fi
}

sha256_of() {
  [[ -f "$1" ]] || { echo "missing"; return 0; }
  if have sha256sum; then sha256sum "$1" | awk '{print $1}'
  else shasum -a 256 "$1" | awk '{print $1}'; fi
}

# Hash of the frontend sources, so a UI change triggers a rebuild and nothing
# else does.
frontend_fingerprint() {
  [[ -d "$ROOT_DIR/frontend/src" ]] || { echo "missing"; return 0; }
  { find "$ROOT_DIR/frontend/src" -type f -print0 | sort -z | xargs -0 cat 2>/dev/null
    cat "$ROOT_DIR/frontend/package.json" \
        "$ROOT_DIR/frontend/vite.config.ts" \
        "$ROOT_DIR/frontend/tsconfig.json" 2>/dev/null
  } | { if have sha256sum; then sha256sum | awk '{print $1}'; else shasum -a 256 | awk '{print $1}'; fi; }
}

repo_version() {
  [[ -f "$ROOT_DIR/VERSION" ]] && tr -d '[:space:]' < "$ROOT_DIR/VERSION" || echo "unknown"
}

git_commit() {
  git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown"
}

manifest_get() {
  [[ -f "$INSTALL_MANIFEST" ]] || { echo ""; return 0; }
  python3 - "$INSTALL_MANIFEST" "$1" <<'PY' 2>/dev/null || echo ""
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    print(""); raise SystemExit
value = data
for part in sys.argv[2].split("."):
    value = value.get(part) if isinstance(value, dict) else None
print("" if value is None else value)
PY
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
    die "Node.js ${MIN_NODE_MAJOR}+ and npm are required to build the web UI and to
     install Solo's own Pi Agent.
     Install Node from https://nodejs.org or your package manager, then retry."
  fi
  local major
  major="$(node -p 'process.versions.node.split(".")[0]')"
  [[ "$major" -ge "$MIN_NODE_MAJOR" ]] \
    || die "Node ${MIN_NODE_MAJOR}+ is required (found $(node -v))."
}

require_curl() { have curl || die "curl is required. Install it and retry."; }

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

env_get() {
  [[ -f "$ROOT_DIR/.env" ]] || { echo ""; return 0; }
  awk -F= -v key="$1" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$ROOT_DIR/.env"
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

# --------------------------------------------------------------------------- #
# Solo's own, isolated Pi Agent runtime
# --------------------------------------------------------------------------- #
# Everything happens through `python -m app.pi_install`, so the shell and the
# Settings UI share one implementation. Pi is installed into
# <data>/pi-runtime and configured in <data>/pi/agent — never into the user's
# global npm tree and never using ~/.pi/agent.
ensure_pi() {
  local args=(--verify)
  env_get PI_EXECUTABLE >/dev/null 2>&1 || true

  log "Ensuring Solo's own isolated Pi Agent runtime"
  (
    cd "$ROOT_DIR"
    export PYTHONPATH="$ROOT_DIR/backend"
    export APP_DATA_DIR="${APP_DATA_DIR:-$DATA_DIR}"
    "$PYTHON" -m app.pi_install "${args[@]}"
  ) && ok "Solo's Pi Agent runtime is installed and verified" \
    || warn "Solo's Pi Agent could not be installed or verified; coding tasks will use the built-in simulator until it is."
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
  write_install_manifest "$(manifest_get version)"
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
  echo " Solo is running  (version $(repo_version))"
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
  echo " Update: ./solo.sh update"
  echo "──────────────────────────────────────────────────────────────"
}

# --------------------------------------------------------------------------- #
# Install / update bookkeeping
# --------------------------------------------------------------------------- #
write_install_manifest() {
  # $1 (optional) is the version being replaced. Passing it explicitly avoids
  # recording the new version as its own predecessor.
  local previous_version="${1:-}"
  mkdir -p "$DATA_DIR"
  APP_DATA_DIR="$DATA_DIR" ROOT_DIR="$ROOT_DIR" \
  VERSION="$(repo_version)" COMMIT="$(git_commit)" \
  SOLO_PREVIOUS_VERSION="$previous_version" \
  REQ_HASH="$(sha256_of "$ROOT_DIR/backend/requirements.txt")" \
  LOCK_HASH="$(sha256_of "$ROOT_DIR/frontend/package-lock.json")" \
  FE_HASH="$(frontend_fingerprint)" \
  "$PYTHON" - <<'PY' 2>/dev/null || true
import json, os, pathlib
from datetime import datetime, timezone

path = pathlib.Path(os.environ["APP_DATA_DIR"]) / "install.json"
previous = {}
if path.exists():
    try:
        previous = json.loads(path.read_text())
    except Exception:
        previous = {}
now = datetime.now(timezone.utc).isoformat()
payload = {
    "version": os.environ["VERSION"],
    "commit": os.environ["COMMIT"],
    # The caller knows the version it started from; otherwise fall back to what
    # was recorded, which is correct for a plain install or restart.
    "previous_version": os.environ.get("SOLO_PREVIOUS_VERSION") or previous.get("version"),
    "requirements_hash": os.environ["REQ_HASH"],
    "package_lock_hash": os.environ["LOCK_HASH"],
    "frontend_hash": os.environ["FE_HASH"],
    "installed_at": previous.get("installed_at", now),
    "updated_at": now,
    "updated_by": os.environ.get("SOLO_UPDATED_BY", "solo.sh"),
}
path.write_text(json.dumps(payload, indent=2) + "\n")
PY
}

# --------------------------------------------------------------------------- #
# Update
# --------------------------------------------------------------------------- #
backup_critical_data() {
  local stamp="$1"
  local destination="$BACKUP_DIR/pre-update-$stamp"
  mkdir -p "$destination"
  chmod 700 "$BACKUP_DIR" "$destination" 2>/dev/null || true

  local copied=0
  for name in app.db master.key secrets.enc; do
    if [[ -f "$DATA_DIR/$name" ]]; then
      cp -p "$DATA_DIR/$name" "$destination/$name"
      copied=$((copied + 1))
    fi
  done
  # The database may be in WAL mode with a sidecar file.
  for name in app.db-wal app.db-shm; do
    [[ -f "$DATA_DIR/$name" ]] && cp -p "$DATA_DIR/$name" "$destination/$name"
  done
  for name in .env; do
    [[ -f "$ROOT_DIR/$name" ]] && cp -p "$ROOT_DIR/$name" "$destination/env.backup"
  done
  [[ -f "$INSTALL_MANIFEST" ]] && cp -p "$INSTALL_MANIFEST" "$destination/install.json"

  echo "$destination"
}

restore_critical_data() {
  local source="$1"
  [[ -d "$source" ]] || return 0
  for name in app.db master.key secrets.enc app.db-wal app.db-shm; do
    [[ -f "$source/$name" ]] && cp -p "$source/$name" "$DATA_DIR/$name"
  done
  [[ -f "$source/env.backup" ]] && cp -p "$source/env.backup" "$ROOT_DIR/.env"
  [[ -f "$source/install.json" ]] && cp -p "$source/install.json" "$INSTALL_MANIFEST"
}

cmd_version() {
  load_env
  local installed available
  installed="$(manifest_get version)"
  available="$(repo_version)"
  echo
  echo "  Installed version : ${installed:-unknown (not recorded yet)}"
  echo "  Checkout version  : ${available}"
  echo "  Commit            : $(git_commit)"
  echo "  Pi Agent runtime  : $(manifest_get runtime || echo "see ./solo.sh doctor")"
  if [[ -d "$ROOT_DIR/.git" ]]; then
    local behind
    behind="$(git -C "$ROOT_DIR" rev-list --count "HEAD..origin/${DEFAULT_BRANCH}" 2>/dev/null || echo "?")"
    echo "  Commits behind    : ${behind}"
  fi
  echo
}

update_impl() {
  local force=0 skip_restart=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --force|-f) force=1 ;;
      --no-restart) skip_restart=1 ;;
      *) die "unknown update option: $1" ;;
    esac
    shift
  done

  load_env
  local branch="${SOLO_BRANCH:-$DEFAULT_BRANCH}"

  step "Checking the update source"
  [[ -d "$ROOT_DIR/.git" ]] || die "Solo was not installed from a git checkout, so 'update' cannot pull changes.
     Re-clone the repository and move your data directory across, or use 'git pull' manually."
  git -C "$ROOT_DIR" remote get-url origin >/dev/null 2>&1 \
    || die "No 'origin' remote is configured. Add one with:
     git -C '$ROOT_DIR' remote add origin <url>"
  ok "origin = $(git -C "$ROOT_DIR" remote get-url origin)"

  local previous_version previous_commit
  previous_version="$(repo_version)"
  previous_commit="$(git -C "$ROOT_DIR" rev-parse HEAD)"
  ok "current version ${previous_version} (${previous_commit:0:7})"

  git -C "$ROOT_DIR" fetch --quiet origin "$branch" \
    || die "Could not fetch from origin. Check your network connection and git credentials."

  local target_commit
  target_commit="$(git -C "$ROOT_DIR" rev-parse "origin/${branch}")"
  if [[ "$previous_commit" == "$target_commit" ]]; then
    ok "Already up to date — nothing to do."
    cmd_version
    return 0
  fi

  # Refuse to overwrite uncommitted work unless told to.
  local dirty
  dirty="$(git -C "$ROOT_DIR" status --porcelain -- . \
    ':(exclude)data' ':(exclude).env' ':(exclude).tools' ':(exclude)frontend/dist' ':(exclude)venv' 2>/dev/null || true)"
  if [[ -n "$dirty" && "$force" -eq 0 ]]; then
    printf '%s\n' "$dirty" | head -20
    die "Local changes would be overwritten. Commit or stash them, or re-run with --force."
  fi

  local new_version
  new_version="$(git -C "$ROOT_DIR" show "origin/${branch}:VERSION" 2>/dev/null | tr -d '[:space:]' || true)"
  new_version="${new_version:-unknown}"
  ok "updating ${previous_version} → ${new_version}"

  step "Backing up configuration and data"
  local stamp destination
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  destination="$(backup_critical_data "$stamp")"
  ok "backup written to ${destination#"$ROOT_DIR"/}"
  echo "     (database, encryption key, secrets and .env — workspaces are untouched)"

  step "Applying the update"
  stop_solo >/dev/null 2>&1 || true
  if ! git -C "$ROOT_DIR" merge --ff-only --quiet "origin/${branch}"; then
    warn "Fast-forward failed."
    if [[ "$force" -eq 1 ]]; then
      warn "--force given: resetting the checkout to origin/${branch}."
      git -C "$ROOT_DIR" reset --hard --quiet "origin/${branch}"
    else
      die "The checkout cannot be fast-forwarded (diverged history). Re-run with --force to reset to origin/${branch}."
    fi
  fi
  ok "code updated to $(git_commit)"

  # Decide what actually needs rebuilding by comparing recorded fingerprints.
  local stored_req stored_lock stored_fe stored_pi
  stored_req="$(manifest_get requirements_hash)"
  stored_lock="$(manifest_get package_lock_hash)"
  stored_fe="$(manifest_get frontend_hash)"
  stored_pi="$(manifest_get pi_runtime_version)"

  local changed=()
  local need_venv=0 need_frontend=0 need_pi=0

  [[ "$(sha256_of "$ROOT_DIR/backend/requirements.txt")" != "$stored_req" ]] && { need_venv=1; changed+=("backend dependencies"); }
  [[ "$(sha256_of "$ROOT_DIR/frontend/package-lock.json")" != "$stored_lock" ]] && { need_frontend=1; changed+=("frontend dependencies"); }
  [[ "$(frontend_fingerprint)" != "$stored_fe" ]] && { need_frontend=1; changed+=("web UI"); }
  [[ "${need_venv}" -eq 0 && ! -x "$PYTHON" ]] && { need_venv=1; changed+=("virtualenv missing"); }
  [[ "${need_frontend}" -eq 0 && ! -f "$ROOT_DIR/frontend/dist/index.html" ]] && { need_frontend=1; changed+=("web UI missing"); }

  # A change to the pinned Pi Agent version must reinstall Solo's runtime.
  local pinned_pi
  pinned_pi="$(grep -oE 'PI_PACKAGE_VERSION = "[^"]+"' "$ROOT_DIR/backend/app/services/pi_runtime.py" 2>/dev/null | head -1 | cut -d'"' -f2)"
  if [[ -n "$pinned_pi" && "$pinned_pi" != "$stored_pi" ]]; then
    need_pi=1; changed+=("Pi Agent runtime (${stored_pi:-none} → ${pinned_pi})")
  fi

  if [[ "${#changed[@]}" -eq 0 ]]; then
    ok "No dependency or build changes detected — restarting only."
  else
    ok "Changes detected: $(IFS=', '; echo "${changed[*]}")"
  fi

  if [[ "$need_venv" -eq 1 ]]; then
    step "Updating backend dependencies"
    ensure_venv || { rollback_update "$previous_commit" "$destination"; exit 1; }
  fi

  if [[ "$need_frontend" -eq 1 ]]; then
    step "Updating the web UI"
    ensure_frontend || { rollback_update "$previous_commit" "$destination"; exit 1; }
  fi

  if [[ "$need_pi" -eq 1 || "$force" -eq 1 ]]; then
    step "Updating Solo's Pi Agent runtime"
    (
      cd "$ROOT_DIR"
      export PYTHONPATH="$ROOT_DIR/backend"
      export APP_DATA_DIR="${APP_DATA_DIR:-$DATA_DIR}"
      "$PYTHON" -m app.pi_install --force --verify
    ) || warn "The Pi Agent runtime could not be updated; coding tasks will use the simulator until it is."
  fi

  step "Applying database migrations"
  (
    cd "$ROOT_DIR"
    export PYTHONPATH="$ROOT_DIR/backend"
    export APP_DATA_DIR="${APP_DATA_DIR:-$DATA_DIR}"
    # Migrations run at application start; this reports the resulting version
    # without leaving a server behind.
    "$PYTHON" - <<'PY'
import asyncio, os, sys
from app.config import get_settings
from app.db import create_engine
from app.migrations import migrate

async def main() -> int:
    settings = get_settings()
    engine = create_engine(settings.db_path)
    report = await migrate(engine)
    await engine.dispose()
    print(f"  schema {report['from']} → {report['to']}"
          + (f" (applied {report['applied']})" if report["applied"] else " (no changes)"))
    return 0

sys.exit(asyncio.run(main()))
PY
  ) || { rollback_update "$previous_commit" "$destination"; exit 1; }
  ok "Database is up to date"

  step "Restarting Solo"
  if [[ "$skip_restart" -eq 0 ]]; then
    SOLO_UPDATED_BY="solo.sh update" start_solo || {
      rollback_update "$previous_commit" "$destination"
      exit 1
    }
    if ! wait_for_health 120; then
      rollback_update "$previous_commit" "$destination"
      exit 1
    fi
  else
    ok "Skipping restart (--no-restart)"
  fi

  SOLO_UPDATED_BY="solo.sh update" write_install_manifest "$previous_version"
  # Record the pinned Pi version so the next update can detect a change.
  local final_pi
  final_pi="$(grep -oE 'PI_PACKAGE_VERSION = "[^"]+"' "$ROOT_DIR/backend/app/services/pi_runtime.py" 2>/dev/null | head -1 | cut -d'"' -f2)"
  "$PYTHON" - "$INSTALL_MANIFEST" "${final_pi:-}" <<'PY' 2>/dev/null || true
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text()) if path.exists() else {}
data["pi_runtime_version"] = sys.argv[2]
path.write_text(json.dumps(data, indent=2) + "\n")
PY

  if [[ "$skip_restart" -eq 0 ]]; then
    step "Update complete"
    echo "  ${previous_version} → ${new_version}   (${previous_commit:0:7} → $(git_commit))"
    echo "  applied: $(IFS=', '; echo "${changed[*]:-code only}")"
    echo "  backup : ${destination#"$ROOT_DIR"/}"
    echo
  fi
}

rollback_update() {
  local previous_commit="$1" backup="$2"
  warn "The update failed — rolling back to ${previous_commit:0:7}."
  stop_solo >/dev/null 2>&1 || true
  git -C "$ROOT_DIR" reset --hard --quiet "$previous_commit" 2>/dev/null || warn "Could not reset the checkout."
  restore_critical_data "$backup"
  # Dependencies may now match the old version; reinstalling keeps the tree
  # consistent with the rolled-back code.
  ( cd "$ROOT_DIR" && "$PIP" install --quiet -r backend/requirements.txt ) 2>/dev/null || true
  start_solo >/dev/null 2>&1 || true
  die "Rolled back to ${previous_commit:0:7}. Your data was restored from ${backup#"$ROOT_DIR"/}.
     The server is running the previous version; see ./solo.sh logs for the failure."
}

# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
cmd_doctor() {
  log "Checking prerequisites"
  require_python && ok "python3 $(python3 -V 2>&1 | awk '{print $2}')"
  if have node; then ok "node $(node -v)"; else warn "node not found — the web UI cannot be built"; fi
  if have curl; then ok "curl available"; else warn "curl not found"; fi
  if have docker && docker info >/dev/null 2>&1; then
    ok "docker daemon reachable (you could use ./install.sh --docker)"
  else
    warn "docker not usable here — the native install is used"
  fi
  [[ -d "$VENV_DIR" ]] && ok "virtualenv present" || warn "virtualenv missing (run ./solo.sh install)"
  [[ -f "$ROOT_DIR/frontend/dist/index.html" ]] && ok "web UI built" || warn "web UI not built"
  [[ -f "$ROOT_DIR/.env" ]] && ok ".env present" || warn ".env missing (will be created)"
  if [[ -x "$VENV_DIR/bin/pyright" ]]; then
    ok "pyright available for static checks"
  else
    warn "pyright not installed — static checks will be skipped"
  fi

  if [[ -x "$PYTHON" ]]; then
    log "Solo's isolated Pi Agent runtime"
    (
      cd "$ROOT_DIR"
      export PYTHONPATH="$ROOT_DIR/backend"
      export APP_DATA_DIR="${APP_DATA_DIR:-$DATA_DIR}"
      "$PYTHON" - <<'PY' || true
import asyncio
from app.config import get_settings
from app.services.pi_runtime import PiRuntime

async def main() -> None:
    runtime = PiRuntime(get_settings())
    status = await runtime.status()
    print(f"  runtime dir : {status.runtime_dir}")
    print(f"  agent dir   : {status.agent_dir}")
    print(f"  executable  : {status.executable or '(not installed)'}")
    print(f"  source      : {status.source}")
    print(f"  version     : {status.version or 'unknown'}")
    print(f"  node        : {status.node or 'not found'}")
    print(f"  isolated    : {'yes' if status.source == 'managed' else 'no'}")
    print(f"  detail      : {status.detail}")

asyncio.run(main())
PY
    )
    if have pi; then
      warn "A separate Pi Agent is also installed globally at $(command -v pi)."
      warn "Solo does not use it; its own runtime is listed above."
    fi
  fi
}

cmd_install() {
  log "Installing Solo (native)"
  require_python
  require_curl
  load_env
  ensure_venv
  # Solo's own Pi Agent runtime (isolated; never the host's installation).
  ensure_pi
  ensure_frontend
  start_solo
}

cmd_logs() {
  [[ -f "$LOG_FILE" ]] || die "No log yet at ${LOG_FILE}. Start the server first."
  tail -n 200 -f "$LOG_FILE"
}

usage() {
  sed -n '3,16p' "$0"
}

# `update` is the canonical command; `--update` is accepted because that is the
# form the documentation and the request use.
case "${1:-}" in
  install) cmd_install ;;
  start)   start_solo ;;
  stop)    stop_solo ;;
  restart) stop_solo; start_solo ;;
  status)  status_solo ;;
  logs)    cmd_logs ;;
  version) cmd_version ;;
  doctor)  cmd_doctor ;;
  update|--update|-u) shift || true; update_impl "$@" ;;
  ""|-h|--help|help) usage ;;
  *) die "Unknown command: $1 (try ./solo.sh help)" ;;
esac
