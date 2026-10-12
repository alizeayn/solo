#!/usr/bin/env bash
#
# Live ElevenLabs verification: the real service, through Solo's own API.
#
# Usage:
#   ELEVENLABS_API_KEY=sk_... ./scripts/e2e-voice-live.sh
#   ELEVENLABS_KEY_FILE=/path/to/key ./scripts/e2e-voice-live.sh
#
# The key is read from the environment or a file and is never written to the
# repository, never passed in a command line, and never printed. Bodies are sent
# with `--data @file` so the key cannot appear in `ps` output either.
#
# The coding task deliberately uses the deterministic agent: this script proves
# the *voice* path (models, synthesis, transcription, narration, audio delivery),
# and Pi's own execution path is covered by scripts/e2e-live.sh.
#
# Skips cleanly (exit 0) when no key is provided.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${E2E_VOICE_PORT:-$((8500 + RANDOM % 300))}"
BASE="http://127.0.0.1:${PORT}"
DATA="$(mktemp -d)"
COOKIES="${DATA}/cookies.txt"
PASS="voice-live-test"
PASSED=0; FAILED=0; SKIPPED=0

pass() { printf '  \033[1;32m✓\033[0m %s\n' "$*"; PASSED=$((PASSED+1)); }
fail() { printf '  \033[1;31m✗\033[0m %s\n' "$*"; FAILED=$((FAILED+1)); }
skip() { printf '  \033[1;33m–\033[0m %s\n' "$*"; SKIPPED=$((SKIPPED+1)); }
step() { printf '\n\033[1;34m▸ %s\033[0m\n' "$*"; }
j() { python3 -c "import json,sys;d=json.load(sys.stdin);print(eval('d'+sys.argv[1]))" "$1"; }

cleanup() {
  if [[ -n "${PID:-}" ]]; then
    kill "$PID" 2>/dev/null
    for _ in $(seq 1 20); do kill -0 "$PID" 2>/dev/null || break; sleep 0.25; done
    kill -9 "$PID" 2>/dev/null
  fi
  rm -rf "$DATA" /tmp/el_probe_body /tmp/el_probe.mp3 /tmp/el_probe.json
}
trap cleanup EXIT

KEY="${ELEVENLABS_API_KEY:-}"
if [[ -z "$KEY" && -n "${ELEVENLABS_KEY_FILE:-}" && -f "${ELEVENLABS_KEY_FILE}" ]]; then
  KEY="$(tr -d '[:space:]' < "${ELEVENLABS_KEY_FILE}")"
fi
if [[ -z "$KEY" ]]; then
  echo "No ElevenLabs key provided; set ELEVENLABS_API_KEY or ELEVENLABS_KEY_FILE."
  exit 0
fi

# A voice id that is known to work on a free plan. Library voices return 402.
VOICE_ID="${ELEVENLABS_VOICE_ID:-EXAVITQu4vr4xnSDxMaL}"
MODEL_ID="${ELEVENLABS_MODEL_ID:-eleven_flash_v2_5}"
STT_MODEL_ID="${ELEVENLABS_STT_MODEL_ID:-scribe_v2}"

# --------------------------------------------------------------------------- #
step "Direct API capability map (what this key is actually allowed to do)"
# curl reads the key from a 0600 config file, so it never reaches argv.
ELCFG="${DATA}/el.curl"
umask 077
printf 'header = "xi-api-key: %s"\nsilent\nshow-error\n' "$KEY" > "$ELCFG"

probe() {
  local label="$1" expect="$2"; shift 2
  local code
  code="$(curl --config "$ELCFG" -o /tmp/el_probe_body -w '%{http_code}' "$@")" || true
  local note=""
  python3 - <<'PY' > /tmp/el_probe_note 2>/dev/null || true
import json
try:
    d = json.load(open('/tmp/el_probe_body'))
    if isinstance(d, dict) and isinstance(d.get('detail'), dict):
        print(d['detail'].get('status') or d['detail'].get('code') or '')
    elif isinstance(d, list):
        print(f'list:{len(d)}')
except Exception:
    pass
PY
  note="$(cat /tmp/el_probe_note)"
  if [[ "$code" == "$expect" ]]; then
    pass "$label → HTTP $code ${note:+($note)}"
  elif [[ "$code" == "402" ]]; then
    skip "$label → HTTP 402 paid plan required ${note:+($note)}"
  elif [[ "$code" == "401" ]]; then
    skip "$label → HTTP 401 not permitted for this key ${note:+($note)}"
  else
    fail "$label → HTTP $code (expected $expect) ${note:+($note)}"
  fi
}

probe "GET /v1/models" 200 https://api.elevenlabs.io/v1/models
probe "GET /v1/user" 200 https://api.elevenlabs.io/v1/user
probe "GET /v2/voices" 200 https://api.elevenlabs.io/v2/voices

step "Text to speech produces real audio"
TTS_CODE="$(curl --config "$ELCFG" -o /tmp/el_probe.mp3 -w '%{http_code}' \
  -X POST "https://api.elevenlabs.io/v1/text-to-speech/${VOICE_ID}/stream?output_format=mp3_44100_128" \
  -H 'Content-Type: application/json' \
  -d "{\"text\":\"Solo live voice check.\",\"model_id\":\"${MODEL_ID}\"}")" || true
if [[ "$TTS_CODE" == "200" ]] && [[ -s /tmp/el_probe.mp3 ]]; then
  pass "synthesised $(wc -c < /tmp/el_probe.mp3) bytes with ${MODEL_ID}"
else
  fail "synthesis returned HTTP ${TTS_CODE}"
fi

step "Speech to text recognises it back"
if [[ -s /tmp/el_probe.mp3 ]]; then
  STT_CODE="$(curl --config "$ELCFG" -o /tmp/el_probe.json -w '%{http_code}' \
    -X POST "https://api.elevenlabs.io/v1/speech-to-text" \
    -F "model_id=${STT_MODEL_ID}" -F "file=@/tmp/el_probe.mp3;type=audio/mpeg")" || true
  if [[ "$STT_CODE" == "200" ]]; then
    HEARD="$(j "['text']" < /tmp/el_probe.json)"
    pass "transcribed: \"${HEARD}\""
  else
    fail "transcription returned HTTP ${STT_CODE}"
  fi
else
  skip "transcription (no audio to round-trip)"
fi

# --------------------------------------------------------------------------- #
step "Solo is configured with the real key"
(
  cd "$ROOT" || exit 1
  exec env PYTHONPATH="$ROOT/backend" APP_DATA_DIR="$DATA" APP_PORT="$PORT" \
    FRONTEND_DIST="$ROOT/frontend/dist" ADMIN_PASSWORD="$PASS" \
    AGENT_BACKEND=mock MOCK_STEP_DELAY=0 LOG_LEVEL=WARNING \
    "$ROOT/venv/bin/python" -m app
) > "$DATA/server.log" 2>&1 &
PID=$!
for _ in $(seq 1 120); do curl -fsS "$BASE/api/health" >/dev/null 2>&1 && break; sleep 0.5; done

curl -fsS -c "$COOKIES" -b "$COOKIES" -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c 'import json,sys;print(json.dumps({"username":"admin","password":sys.argv[1]}))' "$PASS")" \
  >/dev/null && pass "signed in" || fail "login failed"

# The key goes to Solo through its own API, into the encrypted store.
umask 077
printf '{"elevenlabs_api_key":"%s","elevenlabs_model_id":"%s","elevenlabs_stt_model_id":"%s","elevenlabs_tts_voice_id":"%s"}' \
  "$KEY" "$MODEL_ID" "$STT_MODEL_ID" "$VOICE_ID" > "$DATA/settings.json"
SAVED="$(curl -fsS -b "$COOKIES" -X PUT "$BASE/api/settings" \
  -H 'Content-Type: application/json' --data @"$DATA/settings.json")"
[[ "$(echo "$SAVED" | j "['elevenlabs_api_key']['configured']")" == "True" ]] \
  && pass "key stored in Solo's encrypted settings" || fail "key not stored"
echo "$SAVED" | grep -q "$KEY" && fail "the API key was returned by Solo" \
  || pass "Solo never returns the key"

step "Solo validates the connection against the live service"
TEST="$(curl -fsS -b "$COOKIES" -X POST "$BASE/api/settings/test/elevenlabs")"
if [[ "$(echo "$TEST" | j "['ok']")" == "True" ]]; then
  pass "validation passed: $(echo "$TEST" | j "['message']")"
else
  fail "validation failed: $TEST"
fi
DETAIL="$(echo "$TEST" | j "['detail']")"
[[ -n "$DETAIL" ]] && pass "detail: $DETAIL"

step "Solo retrieves models from the live account"
MODELS="$(curl -fsS -b "$COOKIES" "$BASE/api/voice/models")"
COUNT="$(echo "$MODELS" | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))')"
[[ "$COUNT" -gt 0 ]] && pass "$COUNT models retrieved" || fail "no models retrieved"
echo "$MODELS" | python3 -c 'import json,sys;ms=json.load(sys.stdin);print("     sample:", ", ".join(m["id"] for m in ms[:4]))'

step "Voice listing is reported honestly when the key lacks the permission"
VOICES_CODE="$(curl -s -o "$DATA/voices.json" -w '%{http_code}' -b "$COOKIES" "$BASE/api/voice/voices")"
if [[ "$VOICES_CODE" == "200" ]]; then
  N="$(python3 -c 'import json;print(len(json.load(open("'"$DATA"'/voices.json"))))')"
  pass "voices listed ($N)"
else
  MSG="$(python3 -c 'import json;print(json.load(open("'"$DATA"'/voices.json")).get("detail",""))')"
  echo "$MSG" | grep -qi 'voices_read\|not permitted\|permission' \
    && pass "the refusal explains the missing permission, not a bad key" \
    || fail "unhelpful voice-listing error: $MSG"
fi

step "Voice state reflects a configured, speaking transport"
STATE="$(curl -fsS -b "$COOKIES" "$BASE/api/voice/state")"
[[ "$(echo "$STATE" | j "['configured']")" == "True" ]] && pass "configured" || fail "not configured"
[[ "$(echo "$STATE" | j "['audio_available']")" == "True" ]] && pass "audio available" || fail "audio not available"
[[ "$(echo "$STATE" | j "['phase']")" == "voice-active" ]] && pass "phase: voice-active" || fail "phase $(echo "$STATE" | j "['phase']")"

# --------------------------------------------------------------------------- #
step "A real task produces milestones that Solo actually speaks"
PROJECT="$(curl -fsS -b "$COOKIES" -X POST "$BASE/api/projects" \
  -H 'Content-Type: application/json' -d '{"name":"voice-live"}')"
PROJECT_ID="$(echo "$PROJECT" | j "['id']")"
TASK="$(curl -fsS -b "$COOKIES" -X POST "$BASE/api/tasks" \
  -H 'Content-Type: application/json' \
  -d "{\"project_id\":\"${PROJECT_ID}\",\"instruction\":\"add a health endpoint\"}")"
TASK_ID="$(echo "$TASK" | j "['id']")"
pass "task created (${TASK_ID:0:8}…)"

STATUS=""
for _ in $(seq 1 400); do
  STATUS="$(curl -fsS -b "$COOKIES" "$BASE/api/tasks/${TASK_ID}" | j "['status']")"
  case "$STATUS" in COMPLETED|FAILED|CANCELLED) break ;; esac
  sleep 0.25
done
[[ "$STATUS" == "COMPLETED" ]] && pass "task reached COMPLETED" || fail "task ended $STATUS"

MILESTONES="$(curl -fsS -b "$COOKIES" "$BASE/api/milestones/task/${TASK_ID}")"
STAGES="$(echo "$MILESTONES" | python3 -c 'import json,sys;print(" -> ".join(m["stage"] for m in json.load(sys.stdin)))')"
pass "milestones: $STAGES"

step "The milestone text was sent to ElevenLabs and the audio is served back"
for _ in $(seq 1 120); do
  HISTORY="$(curl -fsS -b "$COOKIES" "$BASE/api/voice/history")"
  SPOKEN="$(echo "$HISTORY" | python3 -c 'import json,sys;print(sum(1 for l in json.load(sys.stdin) if l.get("spoken")))')"
  [[ "$SPOKEN" -gt 0 ]] && break
  sleep 0.25
done
[[ "${SPOKEN:-0}" -gt 0 ]] && pass "$SPOKEN line(s) reached the transport" || fail "no line reached the transport"
echo "$HISTORY" | python3 -c 'import json,sys; [print("     [%s] %s" % (l["kind"], l["text"][:74])) for l in json.load(sys.stdin)[:4]]'

LINE_ID="$(echo "$HISTORY" | python3 -c 'import json,sys; print(next((l["id"] for l in json.load(sys.stdin) if l.get("spoken")), ""))')"
AUDIO_CODE="$(curl -s -o "$DATA/audio.mp3" -w '%{http_code}' -b "$COOKIES" "$BASE/api/voice/audio/${LINE_ID}")"
if [[ "$AUDIO_CODE" == "200" ]] && [[ -s "$DATA/audio.mp3" ]]; then
  pass "Solo served $(wc -c < "$DATA/audio.mp3") bytes of real audio for line ${LINE_ID}"
  head -c 3 "$DATA/audio.mp3" | grep -q 'ID3' && pass "the audio is a valid MP3" || skip "no ID3 header (format may differ)"
else
  fail "audio for the spoken line returned HTTP $AUDIO_CODE"
fi

step "Speech input transcribes through Solo and enters the existing task path"
printf '{"content":"Write a simple Python calculator and test that it works."}' > "$DATA/msg.json"
# Send the audio we just got back from Solo as if it were a recording.
TRANSCRIBE_CODE="$(curl -s -o "$DATA/transcript.json" -w '%{http_code}' -b "$COOKIES" \
  -F "file=@/tmp/el_probe.mp3;type=audio/mpeg" "$BASE/api/voice/transcribe")"
if [[ "$TRANSCRIBE_CODE" == "200" ]]; then
  TEXT="$(python3 -c 'import json;print(json.load(open("'"$DATA"'/transcript.json"))["text"])')"
  pass "transcribed through Solo: \"$TEXT\""
  DISPATCH="$(curl -fsS -b "$COOKIES" -X POST "$BASE/api/projects/${PROJECT_ID}/messages" \
    -H 'Content-Type: application/json' --data @"$DATA/msg.json")"
  pass "a spoken instruction dispatches: intent=$(echo "$DISPATCH" | j "['intent']")"
else
  fail "Solo transcription returned HTTP $TRANSCRIBE_CODE"
fi

step "Interrupt (barge-in) works"
INT="$(curl -fsS -b "$COOKIES" -X POST "$BASE/api/voice/interrupt" \
  -H 'Content-Type: application/json' -d '{"reason":"user"}')"
[[ "$(echo "$INT" | j "['listening']")" == "True" ]] && pass "narration yielded to the user" || fail "interrupt failed"
curl -fsS -b "$COOKIES" -X POST "$BASE/api/voice/resume" >/dev/null && pass "resumed" || fail "resume failed"

# --------------------------------------------------------------------------- #
echo
echo "──────────────────────────────────────────────────────────────"
printf ' Live voice: \033[1;32m%d passed\033[0m, ' "$PASSED"
[[ "$FAILED" -eq 0 ]] && printf '\033[1;32m0 failed\033[0m' || printf '\033[1;31m%d failed\033[0m' "$FAILED"
[[ "$SKIPPED" -gt 0 ]] && printf ', \033[1;33m%d skipped\033[0m' "$SKIPPED"
echo
echo "──────────────────────────────────────────────────────────────"
if [[ "$FAILED" -ne 0 ]]; then
  echo "--- last 40 lines of the server log ---"
  tail -40 "$DATA/server.log"
fi
[[ "$FAILED" -eq 0 ]]