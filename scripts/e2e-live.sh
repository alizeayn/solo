#!/usr/bin/env bash
#
# Live Phase 2 acceptance test: a coding task submitted through Chat, executed by
# the real Pi Agent, producing a real file in the opened project, with progress
# recorded and projected into the workspace.
#
# Unlike scripts/e2e.sh (which uses the deterministic simulator and needs no
# credentials), this script drives a real model. It therefore:
#
#   * requires the `pi` CLI and a working provider credential;
#   * selects the provider/model through Solo's own Settings API;
#   * costs a small amount of provider credit;
#   * is skipped automatically when Pi or a credential is unavailable.
#
# Usage:
#   ./scripts/e2e-live.sh
#   E2E_LIVE_PORT=8300 PI_TEST_PROVIDER=opencode-go PI_TEST_MODEL=claude-haiku-5-5 ./scripts/e2e-live.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${E2E_LIVE_PORT:-$((8200 + RANDOM % 300))}"
DATA=$(mktemp -d)
PROJ=$(mktemp -d)
B="http://127.0.0.1:${PORT}"
C="${DATA}/cookies.txt"
PASS="phase2-live-test"
PASSED=0; FAILED=0

pass() { printf '  \033[1;32m✓\033[0m %s\n' "$*"; PASSED=$((PASSED+1)); }
fail() { printf '  \033[1;31m✗\033[0m %s\n' "$*"; FAILED=$((FAILED+1)); }
step() { printf '\n\033[1;34m▸ %s\033[0m\n' "$*"; }
j() { python3 -c "import json,sys;d=json.load(sys.stdin);print(eval('d'+sys.argv[1]))" "$1"; }

cleanup() {
  if [[ -n "${PID:-}" ]]; then
    kill "$PID" 2>/dev/null
    for _ in $(seq 1 20); do kill -0 "$PID" 2>/dev/null || break; sleep 0.25; done
    kill -9 "$PID" 2>/dev/null
  fi
  rm -rf "$DATA" "$PROJ"
}
trap cleanup EXIT

step "Starting Solo with the real Pi backend"
(
  cd "$ROOT" || exit 1
  exec env PYTHONPATH="$ROOT/backend" APP_DATA_DIR="$DATA" APP_PORT="$PORT" \
    FRONTEND_DIST="$ROOT/frontend/dist" ADMIN_PASSWORD="$PASS" \
    AGENT_BACKEND=pi PI_EXECUTABLE="${PI_EXECUTABLE:-pi}" CHECKS_ENABLED=true LOG_LEVEL=WARNING \
    "$ROOT/venv/bin/python" -m app
) > "$DATA/server.log" 2>&1 &
PID=$!
for _ in $(seq 1 120); do curl -fsS "$B/api/health" >/dev/null 2>&1 && break; sleep 0.5; done

HEALTH=$(curl -fsS "$B/api/health")
[[ "$(echo "$HEALTH" | j "['coding_agent']")" == "pi" ]] && pass "backend is pi" || fail "backend is not pi"
[[ -n "$(echo "$HEALTH" | j "['pi_version']")" ]] && pass "Pi version: $(echo "$HEALTH" | j "['pi_version']")" || fail "Pi not detected"

step "Sign in"
curl -fsS -c "$C" -b "$C" -X POST "$B/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"$PASS\"}" >/dev/null && pass "signed in" || fail "login failed"

PROVIDER="${PI_TEST_PROVIDER:-opencode-go}"
MODEL="${PI_TEST_MODEL:-claude-haiku-5-5}"

step "Pre-flight: Pi and a usable credential"
if ! command -v "${PI_EXECUTABLE:-pi}" >/dev/null 2>&1; then
  echo "  Pi is not installed; skipping the live test."
  trap - EXIT; cleanup; exit 0
fi
if [[ "$(curl -fsS -b "$C" "$B/api/pi/status" | j "['runtime']['available']")" != "True" ]]; then
  echo "  Pi is not available to Solo; skipping the live test."
  trap - EXIT; cleanup; exit 0
fi

step "Configure Pi provider and model from Settings"
PROVIDERS=$(curl -fsS -b "$C" "$B/api/pi/providers")
echo "$PROVIDERS" | grep -q "\"$PROVIDER\"" && pass "provider list includes $PROVIDER" || fail "provider missing"

curl -fsS -b "$C" -X PUT "$B/api/settings" -H 'Content-Type: application/json' \
  -d "$(python3 -c 'import json,sys;print(json.dumps({"pi_provider":sys.argv[1],"pi_model":sys.argv[2]}))' "$PROVIDER" "$MODEL")" >/dev/null
STATUS=$(curl -fsS -b "$C" "$B/api/pi/status")
[[ "$(echo "$STATUS" | j "['provider']")" == "$PROVIDER" ]] && pass "provider saved ($PROVIDER)" || fail "provider not saved"
[[ "$(echo "$STATUS" | j "['model']")" == "$MODEL" ]] && pass "model saved ($MODEL)" || fail "model not saved"

step "Discover models through Pi"
MODELS=$(curl -fsS -b "$C" "$B/api/pi/models?provider=$PROVIDER")
COUNT=$(echo "$MODELS" | python3 -c "import json,sys;print(len(json.load(sys.stdin)))")
[[ "$COUNT" -gt 0 ]] && pass "$COUNT models discovered for $PROVIDER" || fail "no models discovered"

step "Validate the provider against the real service"
T1=$(curl -fsS -b "$C" -X POST "$B/api/pi/providers/$PROVIDER/test")
[[ "$(echo "$T1" | j "['ok']")" == "True" ]] && pass "credential check: $(echo "$T1" | j "['state']")" || fail "credential check failed"

step "Open an existing project in place"
printf 'def main():\n    print("existing")\n' > "$PROJ/main.py"
OPENED=$(curl -fsS -b "$C" -X POST "$B/api/projects/open" -H 'Content-Type: application/json' \
  -d "{\"path\":\"$PROJ\",\"name\":\"Live Test\"}")
P_ID=$(echo "$OPENED" | j "['id']")
[[ -n "$P_ID" ]] && pass "project opened: $PROJ" || fail "open failed"

step "Submit a coding task through Chat"
MSG='Create a file named hello_world.py in this folder. It must define a main() function that prints "Hello World from Pi", and an if __name__ == "__main__" guard. Use the write tool, then run it with python3 and report the output.'
DISPATCH=$(curl -fsS -b "$C" -X POST "$B/api/projects/$P_ID/messages" \
  -H 'Content-Type: application/json' -d "$(python3 -c 'import json,sys;print(json.dumps({"content":sys.argv[1]}))' "$MSG")")
INTENT=$(echo "$DISPATCH" | j "['intent']")
TASK_ID=$(echo "$DISPATCH" | j "['task_id']")
pass "intent=$(echo "$DISPATCH" | j "['classified_by']") → $INTENT"
[[ -n "$TASK_ID" && "$TASK_ID" != "None" ]] && pass "task created: ${TASK_ID:0:8}…" || fail "no task created"

step "Wait for Pi to finish"
FINAL=""
for _ in $(seq 1 300); do
  FINAL=$(curl -fsS -b "$C" "$B/api/tasks/$TASK_ID")
  S=$(echo "$FINAL" | j "['status']")
  case "$S" in COMPLETED|FAILED|CANCELLED) break;; esac
  sleep 1
done
S=$(echo "$FINAL" | j "['status']")
[[ "$S" == "COMPLETED" ]] && pass "task reached COMPLETED" || fail "task ended as $S"
echo "     summary: $(echo "$FINAL" | j "['result_summary']" | head -c 220)"

step "Verify the file was really created"
if [[ -f "$PROJ/hello_world.py" ]]; then
  pass "hello_world.py exists ($(wc -c < "$PROJ/hello_world.py") bytes)"
  grep -q "Hello World from Pi" "$PROJ/hello_world.py" && pass "contains the requested text" || fail "text missing"
  grep -q "__main__" "$PROJ/hello_world.py" && pass "has the __main__ guard" || fail "guard missing"
  echo "     --- file content ---"
  sed 's/^/     /' "$PROJ/hello_world.py"
else
  fail "hello_world.py was NOT created"
fi
[[ -f "$PROJ/main.py" ]] && pass "pre-existing file untouched" || fail "existing file was lost"

step "Verify progress was recorded and projected into the workspace"
EVENTS=$(curl -fsS -b "$C" "$B/api/tasks/$TASK_ID/events")
for t in run.started file.changed tool.started assistant.message run.finished; do
  echo "$EVENTS" | grep -q "\"$t\"" && pass "event: $t" || fail "missing event: $t"
done
echo "$EVENTS" | grep -q '"path": *"hello_world.py"' && pass "file.changed names the real path" || fail "file path not reported"

step "Project state store reflects the run"
TREE=$(curl -fsS -b "$C" "$B/api/projects/$P_ID/tree?refresh=true")
echo "$TREE" | grep -q "hello_world.py" && pass "state tree lists the new file" || fail "state tree missing the file"
[[ -f "$PROJ/.solo/tasks/$TASK_ID.json" ]] && pass "task record written to .solo/" || fail "no task record"
[[ -f "$PROJ/.solo/state/orchestration.json" ]] && pass "orchestration state persisted" || fail "no orchestration state"

step "Orchestration state is available through the API"
ORCH=$(curl -fsS -b "$C" "$B/api/projects/$P_ID/orchestration")
echo "$ORCH" | grep -q '"project_id"' && pass "orchestration endpoint responds" || fail "orchestration endpoint failed"

echo
echo "──────────────────────────────────────────────────────────────"
printf ' Live result: \033[1;32m%d passed\033[0m, ' "$PASSED"
[[ "$FAILED" -eq 0 ]] && printf '\033[1;32m0 failed\033[0m\n' || printf '\033[1;31m%d failed\033[0m\n' "$FAILED"
echo "──────────────────────────────────────────────────────────────"
[[ "$FAILED" -eq 0 ]]
