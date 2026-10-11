#!/usr/bin/env bash
#
# End-to-end smoke test against a real running server.
#
# Starts the backend on a throwaway port with a temporary data directory and
# the built frontend, then exercises the full critical path:
#
#   health -> login -> create project -> open project in place -> project
#   state store (tree/memory/config) -> question -> coding task -> live events
#   -> follow-up/steer -> terminal status -> SPA is served
#
# Usage: ./scripts/e2e.sh
# Exit code 0 means every check passed.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT_DIR/venv"
PORT="${E2E_PORT:-8099}"
DATA_DIR="$(mktemp -d)"
# A separate scratch area: the Solo data directory is deliberately blocked as a
# project root, so projects must live outside it.
WORK_DIR="$(mktemp -d)"
BASE="http://127.0.0.1:${PORT}"
COOKIES="${DATA_DIR}/cookies.txt"
SERVER_LOG="${DATA_DIR}/server.log"
ADMIN_USER="admin"
ADMIN_PASS="e2e-admin-password"
SERVER_PID=""

PASS=0
FAIL=0

pass() { printf '  \033[1;32m✓\033[0m %s\n' "$*"; PASS=$((PASS + 1)); }
fail() { printf '  \033[1;31m✗\033[0m %s\n' "$*"; FAIL=$((FAIL + 1)); }
step() { printf '\n\033[1;34m▸ %s\033[0m\n' "$*"; }

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$DATA_DIR" "$WORK_DIR"
}
trap cleanup EXIT

json() { python3 -c "import json,sys;d=json.load(sys.stdin);print(eval('d'+sys.argv[1]))" "$1"; }

[[ -x "$VENV/bin/uvicorn" ]] \
  || { echo "virtualenv missing at $VENV — run: python3 -m venv venv && ./venv/bin/pip install -r backend/requirements-dev.txt" >&2; exit 1; }
[[ -f "$ROOT_DIR/frontend/dist/index.html" ]] \
  || { echo "frontend/dist is missing — run: (cd frontend && npm ci && npm run build)" >&2; exit 1; }

step "Starting the server on port ${PORT}"
(
  cd "$ROOT_DIR/backend"
  APP_ENV=development \
  APP_DATA_DIR="$DATA_DIR" \
  APP_PORT="$PORT" \
  FRONTEND_DIST="$ROOT_DIR/frontend/dist" \
  ADMIN_PASSWORD="$ADMIN_PASS" \
  LOG_LEVEL=WARNING \
  exec "$VENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port "$PORT"
) >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 100); do
  if curl -fsS "${BASE}/api/health" >/dev/null 2>&1; then break; fi
  sleep 0.2
done

# --------------------------------------------------------------------------- #
step "Health endpoint"
HEALTH="$(curl -fsS "${BASE}/api/health" || true)"
if [[ -z "$HEALTH" ]]; then
  fail "health endpoint unreachable"
  echo "--- server log ---"; tail -40 "$SERVER_LOG"
  exit 1
fi
[[ "$(echo "$HEALTH" | json "['status']")" == "ok" ]] && pass "status is ok" || fail "status not ok: $HEALTH"
[[ "$(echo "$HEALTH" | json "['database']")" == "True" ]] && pass "database reachable" || fail "database not reachable"
echo "$HEALTH" | grep -qi "password\|api_key" && fail "health leaks secrets" || pass "health leaks no secrets"

# --------------------------------------------------------------------------- #
step "Authentication is enforced"
CODE="$(curl -s -o /dev/null -w '%{http_code}' "${BASE}/api/projects")"
[[ "$CODE" == "401" ]] && pass "unauthenticated request rejected (401)" || fail "expected 401, got $CODE"

step "Bootstrap admin login"
LOGIN="$(curl -fsS -c "$COOKIES" -b "$COOKIES" -X POST "${BASE}/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${ADMIN_USER}\",\"password\":\"${ADMIN_PASS}\"}")"
[[ "$(echo "$LOGIN" | json "['authenticated']")" == "True" ]] && pass "admin auto-created from installer password" || fail "login failed: $LOGIN"

CODE="$(curl -s -o /dev/null -w '%{http_code}' -b "$COOKIES" "${BASE}/api/projects")"
[[ "$CODE" == "200" ]] && pass "authenticated request accepted" || fail "expected 200, got $CODE"

# --------------------------------------------------------------------------- #
step "Settings are masked"
curl -fsS -b "$COOKIES" -X PUT "${BASE}/api/settings" \
  -H 'Content-Type: application/json' \
  -d '{"openrouter_api_key":"sk-or-v1-e2e-secret-key","openrouter_model":"test/model"}' >/dev/null
SETTINGS="$(curl -fsS -b "$COOKIES" "${BASE}/api/settings")"
echo "$SETTINGS" | grep -q "sk-or-v1-e2e-secret-key" && fail "settings returned the raw API key" || pass "raw API key is never returned"
[[ "$(echo "$SETTINGS" | json "['openrouter_api_key']['configured']")" == "True" ]] && pass "secret reported as configured" || fail "secret not reported configured"
grep -rq "sk-or-v1-e2e-secret-key" "$DATA_DIR/app.db" && fail "secret stored in plaintext in the database" || pass "secret encrypted at rest"

# --------------------------------------------------------------------------- #
step "Project creation"
PROJECT="$(curl -fsS -b "$COOKIES" -X POST "${BASE}/api/projects" \
  -H 'Content-Type: application/json' -d '{"name":"e2e-demo"}')"
PROJECT_ID="$(echo "$PROJECT" | json "['id']")"
[[ -n "$PROJECT_ID" ]] && pass "project created (${PROJECT_ID:0:8}…)" || fail "project creation failed"
[[ "$(echo "$PROJECT" | json "['location']")" == "managed" ]] && pass "created inside the managed workspaces folder" || fail "unexpected location"
[[ "$(echo "$PROJECT" | json "['root']")" == "$DATA_DIR/workspaces/e2e-demo" ]] && pass "project root reported as an absolute path" || fail "unexpected root: $(echo "$PROJECT" | json "['root']")"

# --------------------------------------------------------------------------- #
step "Create Project at a folder of my choosing"
CUSTOM_PARENT="${WORK_DIR}/custom-parent"
mkdir -p "$CUSTOM_PARENT"
CUSTOM="$(curl -fsS -b "$COOKIES" -X POST "${BASE}/api/projects" \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"Custom Spot\",\"parent\":\"${CUSTOM_PARENT}\"}")"
[[ "$(echo "$CUSTOM" | json "['location']")" == "external" ]] && pass "external location recorded" || fail "expected an external project"
[[ -f "${CUSTOM_PARENT}/custom-spot/.solo/project.json" ]] && pass "metadata store created in the chosen folder" || fail "no .solo store created"

# --------------------------------------------------------------------------- #
step "Open Project adopts an existing folder in place"
EXTERNAL_REPO="${WORK_DIR}/external-repo"
mkdir -p "${EXTERNAL_REPO}/src"
printf 'print("hello")\n' >"${EXTERNAL_REPO}/src/main.py"
printf '# existing\n' >"${EXTERNAL_REPO}/README.md"
BEFORE_HASH="$(find "$EXTERNAL_REPO" -type f -exec md5sum {} \; | sort | md5sum)"

OPENED="$(curl -fsS -b "$COOKIES" -X POST "${BASE}/api/projects/open" \
  -H 'Content-Type: application/json' \
  -d "{\"path\":\"${EXTERNAL_REPO}\",\"name\":\"Existing Repo\"}")"
OPENED_ID="$(echo "$OPENED" | json "['id']")"
[[ "$(echo "$OPENED" | json "['location']")" == "external" ]] && pass "opened as an external project" || fail "expected external location"
[[ "$(echo "$OPENED" | json "['root']")" == "$EXTERNAL_REPO" ]] && pass "reads the directory at its existing path" || fail "unexpected root"
[[ -f "${EXTERNAL_REPO}/src/main.py" ]] && pass "user's files left untouched" || fail "project files disappeared"
[[ -f "${EXTERNAL_REPO}/.solo/project.json" ]] && pass "project state store added in place" || fail "no metadata store"
[[ -f "${EXTERNAL_REPO}/.solo/.gitignore" ]] && pass "metadata .gitignore keeps state out of the repo" || fail "no metadata gitignore"

step "Opening the same folder again is idempotent"
AGAIN="$(curl -fsS -b "$COOKIES" -X POST "${BASE}/api/projects/open" \
  -H 'Content-Type: application/json' -d "{\"path\":\"${EXTERNAL_REPO}\"}")"
[[ "$(echo "$AGAIN" | json "['id']")" == "$OPENED_ID" ]] && pass "no duplicate project created" || fail "duplicate project"

step "Opening a disallowed location is refused"
if [[ -d /etc ]]; then
  CODE="$(curl -s -o /dev/null -w '%{http_code}' -b "$COOKIES" -X POST "${BASE}/api/projects/open" \
    -H 'Content-Type: application/json' -d '{"path":"/etc"}')"
  [[ "$CODE" == "400" ]] && pass "blocked system directory rejected (400)" || fail "expected 400, got $CODE"
fi

step "Filesystem browser lists directories only"
BROWSE="$(curl -fsS -b "$COOKIES" "${BASE}/api/fs/list?path=${WORK_DIR}")"
echo "$BROWSE" | grep -q '"path"' && pass "browse endpoint responds" || fail "browse endpoint failed"
echo "$BROWSE" | grep -q '"is_project"' && pass "directories are flagged when they already hold Solo state" || fail "missing is_project flag"

# --------------------------------------------------------------------------- #
step "Project state store: tree, memory and configuration"
TREE="$(curl -fsS -b "$COOKIES" "${BASE}/api/projects/${OPENED_ID}/tree?refresh=true")"
for group in group:files group:tasks group:memory group:sessions; do
  echo "$TREE" | grep -q "$group" && pass "state tree contains ${group}" || fail "missing ${group}"
done
echo "$TREE" | grep -q 'main.py' && pass "file tree lists real project files" || fail "file tree is empty"

MAIN_STATE="${EXTERNAL_REPO}/.solo/state/tree.json"
[[ -f "$MAIN_STATE" ]] && pass "state tree persisted to .solo/state/tree.json" || fail "no state tree file"

MEMORY="$(curl -fsS -b "$COOKIES" -X POST "${BASE}/api/projects/${OPENED_ID}/memory" \
  -H 'Content-Type: application/json' -d '{"text":"Uses SQLite","kind":"decision","tags":["db"]}')"
[[ "$(echo "$MEMORY" | json "['kind']")" == "decision" ]] && pass "memory entry recorded" || fail "memory entry failed"
[[ -f "${EXTERNAL_REPO}/.solo/memory/index.json" ]] && pass "memory persisted to .solo/memory" || fail "no memory index"

curl -fsS -b "$COOKIES" -X PUT "${BASE}/api/projects/${OPENED_ID}/config" \
  -H 'Content-Type: application/json' -d '{"memory":{"auto_capture":false}}' >/dev/null
CONFIG="$(curl -fsS -b "$COOKIES" "${BASE}/api/projects/${OPENED_ID}/config")"
[[ "$(echo "$CONFIG" | json "['memory']['auto_capture']")" == "False" ]] && pass "per-project configuration updated" || fail "config update failed"

SUMMARY="$(curl -fsS -b "$COOKIES" "${BASE}/api/projects/${OPENED_ID}/summary")"
[[ "$(echo "$SUMMARY" | json "['metadata_exists']")" == "True" ]] && pass "summary reports an initialised store" || fail "summary wrong"

step "Zip-slip upload is rejected"
python3 - "$DATA_DIR/evil.zip" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], "w") as z:
    z.writestr("../escaped.txt", "pwned")
PY
CODE="$(curl -s -o /dev/null -w '%{http_code}' -b "$COOKIES" \
  -F "file=@${DATA_DIR}/evil.zip" "${BASE}/api/projects/upload")"
[[ "$CODE" == "400" ]] && pass "malicious archive rejected (400)" || fail "expected 400, got $CODE"
[[ -f "${DATA_DIR}/escaped.txt" ]] && fail "zip slip succeeded — file escaped the workspace" || pass "no file escaped the workspace"

# --------------------------------------------------------------------------- #
step "Question is answered without starting a coding task"
ANSWER="$(curl -fsS -b "$COOKIES" -X POST "${BASE}/api/projects/${PROJECT_ID}/messages" \
  -H 'Content-Type: application/json' -d '{"content":"how many files are there?"}')"
[[ "$(echo "$ANSWER" | json "['intent']")" == "CHAT_OR_EXPLAIN" ]] && pass "question classified as CHAT_OR_EXPLAIN" || fail "unexpected intent: $ANSWER"
echo "$ANSWER" | json "['message']['content']" | grep -q "0 file" && pass "answer derived from the project snapshot" || fail "unexpected answer"

# --------------------------------------------------------------------------- #
step "Coding task runs to completion with normalised events"
TASK="$(curl -fsS -b "$COOKIES" -X POST "${BASE}/api/tasks" \
  -H 'Content-Type: application/json' \
  -d "{\"project_id\":\"${PROJECT_ID}\",\"instruction\":\"add a health endpoint\"}")"
TASK_ID="$(echo "$TASK" | json "['id']")"
pass "task created (${TASK_ID:0:8}…)"

STATUS=""
for _ in $(seq 1 200); do
  STATUS="$(curl -fsS -b "$COOKIES" "${BASE}/api/tasks/${TASK_ID}" | json "['status']")"
  case "$STATUS" in COMPLETED|FAILED|CANCELLED|RECOVERY_REQUIRED) break ;; esac
  sleep 0.25
done
[[ "$STATUS" == "COMPLETED" ]] && pass "task reached COMPLETED" || fail "task ended in ${STATUS}"

EVENTS="$(curl -fsS -b "$COOKIES" "${BASE}/api/tasks/${TASK_ID}/events")"
for expected in run.started file.changed test.result run.finished task.status_changed; do
  echo "$EVENTS" | grep -q "\"${expected}\"" && pass "event present: ${expected}" || fail "missing event: ${expected}"
done

DETAIL="$(curl -fsS -b "$COOKIES" "${BASE}/api/tasks/${TASK_ID}")"
[[ "$(echo "$DETAIL" | json "['result_summary'] is not None")" == "True" ]] && pass "result summary recorded" || fail "no result summary"

# --------------------------------------------------------------------------- #
step "Orchestrator milestones are derived from the run, not from a timer"
MILESTONES="$(curl -fsS -b "$COOKIES" "${BASE}/api/milestones/task/${TASK_ID}")"
MCOUNT="$(echo "$MILESTONES" | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))')"
[[ "$MCOUNT" -gt 0 ]] && pass "${MCOUNT} milestones recorded for the task" || fail "no milestones recorded"

echo "$MILESTONES" | python3 -c '
import json, sys
items = json.load(sys.stdin)
stages = [item["stage"] for item in items]
assert stages[0] == "understanding", f"first stage was {stages[0]}"
assert "implementing" in stages, f"no implementation milestone in {stages}"
assert stages[-1] == "completed", f"last stage was {stages[-1]}"
# Every milestone cites the evidence that justified it.
assert all(item["evidence"] for item in items), "a milestone had no evidence"
# Sequence numbers are monotonic, so the UI can order reliably.
sequences = [item["sequence"] for item in items]
assert sequences == sorted(sequences), f"out of order: {sequences}"
assert len(set(sequences)) == len(sequences), "duplicate sequence numbers"
# Statuses are documented values, and nothing stays active after completion.
allowed = {"pending", "active", "done", "failed"}
assert all(item["status"] in allowed for item in items), "unknown status"
assert all(item["status"] != "active" for item in items), "a milestone stayed active"
print("  stages:", " -> ".join(stages))
' && pass "milestone chain is evidence-backed, ordered and closed" || fail "milestone chain malformed"

# Activity and milestones are separate streams on purpose.
echo "$EVENTS" | grep -q '"milestone"' && fail "milestones leaked into the activity stream" \
  || pass "milestones are a separate stream from agent activity"

step "The milestone snapshot is persisted for later consumers"
STATE="$(curl -fsS -b "$COOKIES" "${BASE}/api/milestones/state")"
echo "$STATE" | grep -q '"version"' && pass "structured snapshot exposed" || fail "snapshot unavailable"
MSTATE="${DATA_DIR}/workspaces/e2e-demo/.solo/state/milestones.json"
[[ -f "$MSTATE" ]] && pass "snapshot written to .solo/state/milestones.json" || fail "snapshot not persisted"

step "Orchestrator distinguishes a saved key from a chosen model"
# The key was saved earlier in this run; no model was chosen. Listing models must
# therefore work — that is the exact bug this change fixes.
# The key saved earlier is deliberately fake, so OpenRouter itself will reject
# it. What matters is *which* layer rejects it: the local "do you have a key"
# check must be passed, and the failure must come from the remote service. A 400
# naming the missing key would be the original bug.
MCODE="$(curl -s -o "$DATA_DIR/mlist.json" -w '%{http_code}' -b "$COOKIES" "${BASE}/api/orchestrator/models")"
MLIST="$(cat "$DATA_DIR/mlist.json")"
case "$MCODE" in
  200) pass "models retrieved from the saved key: $(echo "$MLIST" | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))') model(s)" ;;
  502) pass "the local key check was passed; OpenRouter rejected the fake test key (502)" ;;
  400) echo "$MLIST" | grep -qi 'API key' \
         && fail "model listing still demands a key that is saved (the original bug)" \
         || fail "unexpected 400: $MLIST" ;;
  *)   fail "unexpected status $MCODE: $MLIST" ;;
esac
echo "$MLIST" | grep -q 'sk-or-v1-e2e-secret-key' && fail "the API key leaked into the response" \
  || pass "the key is never returned"
OSTATUS="$(curl -fsS -b "$COOKIES" "${BASE}/api/orchestrator/status")"
[[ "$(echo "$OSTATUS" | json "['has_key']")" == "True" ]] && pass "status reports the key as present" || fail "status hides the key"
[[ "$(echo "$OSTATUS" | json "['model']")" == "test/model" ]] && pass "the selected model is reported by the runtime" || fail "selected model not connected"
[[ "$(echo "$OSTATUS" | json "['configured']")" == "True" ]] && pass "the Orchestrator is configured" || fail "not configured"

# --------------------------------------------------------------------------- #
step "Follow-up steering while a task is running"
STEER_TASK="$(curl -fsS -b "$COOKIES" -X POST "${BASE}/api/tasks" \
  -H 'Content-Type: application/json' \
  -d "{\"project_id\":\"${PROJECT_ID}\",\"instruction\":\"second task\"}")"
FOLLOWUP="$(curl -fsS -b "$COOKIES" -X POST "${BASE}/api/projects/${PROJECT_ID}/messages" \
  -H 'Content-Type: application/json' -d '{"content":"also update the docs"}')"
INTENT="$(echo "$FOLLOWUP" | json "['intent']")"
if [[ "$INTENT" == "STEER_ACTIVE_TASK" || "$INTENT" == "START_CODING_TASK" ]]; then
  pass "follow-up routed sensibly (${INTENT})"
else
  fail "unexpected follow-up intent: ${INTENT}"
fi

# --------------------------------------------------------------------------- #
step "Single-page app is served from the same origin"
INDEX="$(curl -fsS "${BASE}/")"
echo "$INDEX" | grep -q 'id="root"' && pass "index.html served at /" || fail "SPA not served at /"
curl -fsS -o /dev/null "${BASE}/api/docs" && pass "OpenAPI docs available at /api/docs" || fail "docs unavailable"

# --------------------------------------------------------------------------- #
step "Removing an opened project leaves the user's files untouched"
CODE="$(curl -s -o /dev/null -w '%{http_code}' -b "$COOKIES" -X DELETE "${BASE}/api/projects/${OPENED_ID}")"
[[ "$CODE" == "204" ]] && pass "project unregistered (204)" || fail "expected 204, got $CODE"
[[ -f "${EXTERNAL_REPO}/src/main.py" ]] && pass "user's source file still present" || fail "user files were deleted"
[[ -f "${EXTERNAL_REPO}/.solo/project.json" ]] && pass "project state preserved for a future re-open" || fail "state lost"
AFTER_HASH="$(find "$EXTERNAL_REPO" -type f -not -path '*/.solo/*' -exec md5sum {} \; | sort | md5sum)"
[[ "$BEFORE_HASH" == "$AFTER_HASH" ]] && pass "file contents byte-for-byte unchanged" || fail "file contents changed"

# --------------------------------------------------------------------------- #
step "Task state is persisted in SQLite"
python3 - "$DATA_DIR/app.db" "$TASK_ID" <<'PY'
import sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
row = connection.execute("SELECT status, result_summary FROM tasks WHERE id = ?", (sys.argv[2],)).fetchone()
assert row is not None, "task row missing"
assert row[0] == "COMPLETED", f"unexpected persisted status: {row[0]}"
assert row[1], "result summary was not persisted"
print("  persisted status:", row[0])
PY
pass "persisted task state verified"

# --------------------------------------------------------------------------- #
echo
echo "──────────────────────────────────────────────────────────────"
printf ' Result: \033[1;32m%d passed\033[0m, ' "$PASS"
if [[ "$FAIL" -eq 0 ]]; then
  printf '\033[1;32m0 failed\033[0m\n'
else
  printf '\033[1;31m%d failed\033[0m\n' "$FAIL"
  echo
  echo "--- last 60 lines of the server log ---"
  tail -60 "$SERVER_LOG"
fi
echo "──────────────────────────────────────────────────────────────"

[[ "$FAIL" -eq 0 ]]
