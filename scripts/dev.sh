#!/usr/bin/env bash
#
# Non-Docker development workflow.
#
# Starts the FastAPI backend (with autoreload) and the Vite dev server, which
# proxies /api to the backend. The browser only ever talks to Vite.
#
# Usage:
#   ./scripts/dev.sh            run backend and frontend together
#   ./scripts/dev.sh backend    backend only
#   ./scripts/dev.sh frontend   frontend only

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-all}"
VENV="$ROOT_DIR/venv"
PY="$VENV/bin/python"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

[[ -x "$PY" ]] || die "Virtualenv not found at ${VENV}. Create it with: python3 -m venv venv"

run_backend() {
  [[ -f "$ROOT_DIR/.env" ]] || cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
  log "Backend:  http://127.0.0.1:${APP_PORT:-8080}  (docs at /api/docs)"
  # Run from the repository root so `.env`, `./data` and the SQLite database
  # resolve to the same places as the native install.
  cd "$ROOT_DIR"
  export PYTHONPATH="$ROOT_DIR/backend"
  export FRONTEND_DIST="${FRONTEND_DIST:-$ROOT_DIR/frontend/dist}"
  exec "$VENV/bin/uvicorn" app.main:app \
    --host "${APP_HOST:-127.0.0.1}" \
    --port "${APP_PORT:-8080}" \
    --reload \
    --reload-dir "$ROOT_DIR/backend"
}

run_frontend() {
  log "Frontend: http://127.0.0.1:5173"
  cd "$ROOT_DIR/frontend"
  [[ -d node_modules ]] || npm install
  exec npm run dev
}

case "$TARGET" in
  backend) run_backend ;;
  frontend) run_frontend ;;
  all)
    run_backend &
    BACKEND_PID=$!
    trap 'kill ${BACKEND_PID} 2>/dev/null || true' EXIT INT TERM
    run_frontend
    ;;
  *) die "Unknown target: $TARGET (expected all|backend|frontend)" ;;
esac
