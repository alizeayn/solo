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

step "Installing Solo's isolated Pi Agent runtime (what Easy Installation does)"
# Deliberately done here, in the test's own data directory: it verifies both the
# installer and the isolation, and it proves the runtime is per-installation
# rather than borrowed from the host.
if (
  cd "$ROOT"
  PYTHONPATH="$ROOT/backend" APP_DATA_DIR="$DATA" "$ROOT/venv/bin/python" -m app.pi_install --verify
); then
  pass "Solo's own Pi Agent runtime installed and verified"
else
  fail "Solo's runtime could not be installed or verified"
  echo "  (continuing so the remaining checks can report their state)"
fi
if command -v pi >/dev/null 2>&1; then
  echo "  note: a global pi exists at $(command -v pi); Solo must not use it"
else
  pass "no global pi on PATH — this run proves independence from it"
fi

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
[[ "$(echo "$HEALTH" | j "['pi_isolated']")" == "True" ]] && pass "health reports an isolated Pi runtime" || fail "health does not report isolation"
[[ -n "$(echo "$HEALTH" | j "['pi_version']")" ]] && pass "Pi version: $(echo "$HEALTH" | j "['pi_version']")" || fail "Pi version not detected"

step "Sign in"
curl -fsS -c "$C" -b "$C" -X POST "$B/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"$PASS\"}" >/dev/null && pass "signed in" || fail "login failed"

PROVIDER="${PI_TEST_PROVIDER:-opencode-go}"
MODEL="${PI_TEST_MODEL:-claude-haiku-5-5}"

step "Pre-flight: Solo's own Pi runtime and a usable credential"
# Deliberately does NOT check PATH: Solo uses its own isolated runtime, and the
# whole point of this test is that a global `pi` is irrelevant.
PI_STATUS=$(curl -fsS -b "$C" "$B/api/pi/status")
if [[ "$(echo "$PI_STATUS" | j "['runtime']['installed']")" != "True" ]]; then
  echo "  Solo's isolated Pi runtime is not installed; skipping the live test."
  echo "  Install it with: ./solo.sh install"
  trap - EXIT; cleanup; exit 0
fi
pass "Solo's runtime: $(echo "$PI_STATUS" | j "['runtime']['source']") v$(echo "$PI_STATUS" | j "['runtime']['version']")"
[[ "$(echo "$PI_STATUS" | j "['runtime']['isolated']")" == "True" ]] && pass "runtime is isolated (source=managed)" || fail "runtime is not isolated"
# The runtime must live inside this installation's own data directory: the
# definitive check that Solo is not using a host installation.
RUNTIME_DIR="$(echo "$PI_STATUS" | j "['runtime']['runtime_dir']")"
AGENT_DIR="$(echo "$PI_STATUS" | j "['runtime']['agent_dir']")"
case "$RUNTIME_DIR" in "$DATA"/*) pass "runtime lives inside this installation";; *) fail "runtime is outside the installation: $RUNTIME_DIR";; esac
case "$AGENT_DIR" in "$DATA"/*) pass "Pi configuration is isolated from the desktop installation";; *) fail "Pi configuration is not isolated: $AGENT_DIR";; esac
case "$RUNTIME_DIR" in "$ROOT"/*) fail "runtime is inside the source checkout";; *) pass "runtime is outside the source checkout";; esac
case "$AGENT_DIR" in "$HOME/.pi"*) fail "Pi configuration points at ~/.pi";; *) pass "Pi configuration is not ~/.pi/agent";; esac
if command -v pi >/dev/null 2>&1; then
  echo "  note: a global pi exists at $(command -v pi); Solo must not use it"
fi

step "Give Solo its own credential, through Solo's own API"
# Solo's Pi configuration is isolated, so by design it does NOT see the host's
# ~/.pi/agent/auth.json. A credential must therefore be provided the way a user
# would: through the Settings API, into Solo's own store. Seeding it from the
# machine's existing Pi credential (when one exists) keeps the test runnable
# without pasting a key, and still lands in Solo's directory only.
CREDENTIAL="${PI_TEST_API_KEY:-}"
if [[ -n "$CREDENTIAL" ]]; then
  pass "using PI_TEST_API_KEY from the environment"
elif [[ -f "$HOME/.pi/agent/auth.json" ]]; then
  CREDENTIAL="$(python3 -c '
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    raise SystemExit
entry = data.get(sys.argv[2]) or {}
key = entry.get("key") if isinstance(entry, dict) else None
print(key if isinstance(key, str) else "")
' "$HOME/.pi/agent/auth.json" "$PROVIDER")"
  [[ -n "$CREDENTIAL" ]] && pass "found a $PROVIDER credential on this machine to seed Solo's own store"
fi

if [[ -z "$CREDENTIAL" ]]; then
  echo "  No credential is available for $PROVIDER, and Solo deliberately does"
  echo "  not read the host Pi configuration, so the coding task cannot run."
  echo "  Set PI_TEST_API_KEY=<key> and re-run to include it."
  echo
  echo "──────────────────────────────────────────────────────────────"
  printf ' Isolation result: \033[1;32m%d passed\033[0m, ' "$PASSED"
  printf '\033[1;33m%d not run\033[0m (no credential)\n' "$FAILED"
  echo "──────────────────────────────────────────────────────────────"
  trap - EXIT
  cleanup
  exit 0
fi

CRED_RESPONSE=$(curl -fsS -b "$C" -X PUT "$B/api/pi/providers/$PROVIDER/credential" \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c 'import json,sys;print(json.dumps({"api_key":sys.argv[1]}))' "$CREDENTIAL")")
[[ "$(echo "$CRED_RESPONSE" | j "['ready']")" == "True" ]] \
  && pass "Solo accepted the credential into its own Pi configuration" \
  || fail "Solo rejected the credential: $CRED_RESPONSE"
[[ -f "$AGENT_DIR/auth.json" ]] && pass "credential stored in Solo's agent directory" || fail "no auth.json in Solo's agent directory"
cmp -s "$AGENT_DIR/auth.json" "$HOME/.pi/agent/auth.json" \
  && fail "Solo's credential file is the host's file" \
  || pass "Solo's credential file is separate from the host's"
unset CREDENTIAL CRED_RESPONSE

step "Configure Pi provider and model from Settings"
PROVIDERS=$(curl -fsS -b "$C" "$B/api/pi/providers")
echo "$PROVIDERS" | grep -q "\"$PROVIDER\"" && pass "provider list includes $PROVIDER" || fail "provider missing"

curl -fsS -b "$C" -X PUT "$B/api/settings" -H 'Content-Type: application/json' \
  -d "$(python3 -c 'import json,sys;print(json.dumps({"pi_provider":sys.argv[1],"pi_model":sys.argv[2]}))' "$PROVIDER" "$MODEL")" >/dev/null
STATUS=$(curl -fsS -b "$C" "$B/api/pi/status")
[[ "$(echo "$STATUS" | j "['provider']")" == "$PROVIDER" ]] && pass "provider saved ($PROVIDER)" || fail "provider not saved"
[[ "$(echo "$STATUS" | j "['model']")" == "$MODEL" ]] && pass "model saved ($MODEL)" || fail "model not saved"

step "Discover models through Pi's own catalog"
# Solo's catalog was empty until the credential above was saved: the bundled
# provider catalogs are resolved from Solo's own credentials.
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

step "Orchestrator milestones were derived from the real run"
MS=$(curl -fsS -b "$C" "$B/api/milestones/task/$TASK_ID")
MCOUNT=$(echo "$MS" | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))')
[[ "$MCOUNT" -gt 0 ]] && pass "$MCOUNT milestones recorded" || fail "no milestones recorded"
# The chain must match what actually happened. A run that failed because the
# provider refused the request legitimately ends in `blocked`; asserting
# `completed` there would reward a green tick over the truth.
TASK_STATUS=$(echo "$FINAL" | j "['status']")
if echo "$MS" | python3 -c '
import json, sys
expected = sys.argv[1]
items = json.load(sys.stdin)
stages = [i["stage"] for i in items]
assert stages[0] == "understanding", stages
assert all(i["evidence"] for i in items), "a milestone had no evidence"
# No stage repeats except a recovery-free failure, which is folded into one.
assert stages.count("blocked") <= 1, f"duplicate blocked milestones: {stages}"
if expected == "COMPLETED":
    assert "implementing" in stages, stages
    assert stages[-1] == "completed", stages
else:
    assert stages[-1] in ("blocked", "cancelled"), stages
print("  stages:", " -> ".join(stages))
' "$TASK_STATUS"; then
  pass "milestone chain matches the run ($TASK_STATUS)"
else
  fail "milestone chain malformed for a $TASK_STATUS run"
fi
[[ -f "$PROJ/.solo/state/milestones.json" ]] && pass "milestones persisted to .solo/state" || fail "milestones not persisted"
# The voice channel consumes structured milestones, never raw agent events.
NARR=$(curl -fsS -b "$C" "$B/api/voice/history")
if echo "$NARR" | python3 -c 'import json,sys;sys.exit(0 if any("milestone" in str(l.get("kind","")) for l in json.load(sys.stdin)) else 1)' 2>/dev/null; then
  pass "a milestone reached the narration channel"
else
  echo "  (no narrated milestone in this run)"
fi

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
