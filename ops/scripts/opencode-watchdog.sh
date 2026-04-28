#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:4096}"
SESSION_ID="${1:?Usage: ./opencode-watchdog.sh ses_22a1c0e74ffeSru7r1WZ5tB65T}"
LOG_FILE="${LOG_FILE:-/home/ubuntu/workspace/IdeaProjects/ExecQueue/opencode-events.log}"
IDLE_SECONDS="${IDLE_SECONDS:-90}"
MAX_CONTINUES="${MAX_CONTINUES:-50}"

CONTINUE_PROMPT='Continue the previous task. Do not restart from scratch. Continue with the next unfinished step. If all work is done, provide a final report with modified files, tests/checks run, and remaining blockers. Stop only when done or concretely blocked.'

send_continue() {
  curl -sS -X POST "$BASE_URL/session/$SESSION_ID/message" \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg text "$CONTINUE_PROMPT" '{parts:[{type:"text", text:$text}]}')" >/dev/null
}

last_activity_epoch() {
  grep -a "$SESSION_ID" "$LOG_FILE" \
    | grep -aE '"type":"message.part.updated"|"type":"message.part.delta"|"tool":"bash"|"tool":"read"|"tool":"edit"|"tool":"write"' \
    | tail -1 \
    | xargs -r stat --format=%Y "$LOG_FILE" 2>/dev/null || date +%s
}

continues=0

while true; do
  now="$(date +%s)"
  last="$(last_activity_epoch)"
  idle=$((now - last))

  if (( idle >= IDLE_SECONDS )); then
    if (( continues >= MAX_CONTINUES )); then
      echo "Max continues reached; stopping watchdog."
      exit 1
    fi

    echo "$(date -Is) idle=${idle}s -> sending continue #$((continues + 1))"
    send_continue
    continues=$((continues + 1))
    sleep "$IDLE_SECONDS"
  else
    sleep 10
  fi
done
