#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# OpenCode Session Starter + SSE Event Logger + Watchdog Continue
#
# Zweck:
# - Startet oder reused eine lokale OpenCode-Serve-Instanz.
# - Erstellt eine neue Session.
# - Liest den Prompt aus prompt.txt neben diesem Script.
# - Sendet eine initiale Message.
# - Loggt OpenCode-SSE-Events nach ./logs.
# - Überwacht message.updated / message.part.updated für diese Session.
# - Sendet automatisch einen deutschen Continue-Prompt, wenn:
#     1. länger als WATCHDOG_TIMEOUT_SECONDS keine relevanten Events kamen,
#     2. noch kein finish:"stop" erkannt wurde,
#     3. aktuell kein anderer Message-POST für diese Session aktiv ist.
# - Beendet sich bei finish:"stop" oder bei Schutzlimits.
#
# Wichtiger Designpunkt:
# - Es werden keine parallelen POST /message Requests in dieselbe Session geschickt.
#   Das hatte in der Praxis Timeout-/Race-Probleme verursacht.
#
# Voraussetzungen:
# - opencode
# - curl
# - jq
#
# Nutzung:
#   chmod +x opencode-test-message-watchdog.sh
#   ./opencode-test-message-watchdog.sh
#
# Prompt-Quelle:
#   Standard: prompt.txt im gleichen Verzeichnis wie dieses Script.
#   Kompatibilitäts-Fallback: promt.txt im gleichen Verzeichnis, falls prompt.txt fehlt.
#   Optional: PROMPT_FILE=/pfad/zur/datei.txt ./opencode-test-message-watchdog.sh
#   Optionaler CLI-Override: ./opencode-test-message-watchdog.sh "kurzer Prompt"
#
# Optionale ENV Overrides:
#   PROMPT_FILE=/pfad/zur/prompt.txt
#   OPENCODE_HOST=127.0.0.1
#   OPENCODE_PORT=4096
#   WATCHDOG_TIMEOUT_SECONDS=30
#   MAX_CONTINUE_COUNT=20
#   MAX_RUNTIME_SECONDS=3600
#   MIN_CONTINUE_GAP_SECONDS=30
#   MESSAGE_CURL_MAX_TIME_SECONDS=0
#   ACTIVE_REQUEST_LOG_INTERVAL_SECONDS=60
#   OPENCODE_SERVER_USERNAME=opencode
#   OPENCODE_SERVER_PASSWORD=...
#   CONTINUE_PROMPT="..."
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PROMPT_FILE="${SCRIPT_DIR}/prompt.txt"
TYPO_PROMPT_FILE="${SCRIPT_DIR}/promt.txt"
PROMPT_FILE="${PROMPT_FILE:-}"

HOST="${OPENCODE_HOST:-127.0.0.1}"
PORT="${OPENCODE_PORT:-4096}"
BASE_URL="http://${HOST}:${PORT}"

WATCHDOG_TIMEOUT_SECONDS="${WATCHDOG_TIMEOUT_SECONDS:-30}"
MAX_CONTINUE_COUNT="${MAX_CONTINUE_COUNT:-20}"
MAX_RUNTIME_SECONDS="${MAX_RUNTIME_SECONDS:-3600}"
MIN_CONTINUE_GAP_SECONDS="${MIN_CONTINUE_GAP_SECONDS:-30}"
MESSAGE_CURL_MAX_TIME_SECONDS="${MESSAGE_CURL_MAX_TIME_SECONDS:-0}"
ACTIVE_REQUEST_LOG_INTERVAL_SECONDS="${ACTIVE_REQUEST_LOG_INTERVAL_SECONDS:-60}"
CLEANUP_STATE_DIR="${CLEANUP_STATE_DIR:-0}"

CONTINUE_PROMPT="${CONTINUE_PROMPT:-Fahre mit der vorherigen Aufgabe fort. Starte nicht von vorne. Setze exakt beim nächsten offenen Schritt fort. Wiederhole keine bereits erledigten Analysen. Wenn die Aufgabe vollständig erledigt ist, liefere einen finalen Bericht mit: geänderten Dateien, ausgeführten Tests/Checks, Ergebnis der Validierung und verbleibenden Blockern. Beende nur, wenn die Aufgabe erledigt oder konkret blockiert ist.}"

RUN_DIR="$(pwd)"
LOG_DIR="${RUN_DIR}/logs"
TIMESTAMP="$(date '+%Y%m%d-%H%M%S')"

SERVER_LOG_FILE="${LOG_DIR}/opencode-server-${PORT}-${TIMESTAMP}.log"
EVENT_LOG_FILE="${LOG_DIR}/opencode-events-${PORT}-${TIMESTAMP}.log"
WATCHDOG_LOG_FILE="${LOG_DIR}/opencode-watchdog-${PORT}-${TIMESTAMP}.log"
RESPONSE_LOG_FILE="${LOG_DIR}/opencode-response-${PORT}-${TIMESTAMP}.jsonl"
SUMMARY_FILE="${LOG_DIR}/opencode-summary-${PORT}-${TIMESTAMP}.txt"

STATE_DIR="${LOG_DIR}/.opencode-watchdog-${PORT}-${TIMESTAMP}"
SESSION_FILE="${STATE_DIR}/session_id"
LAST_ACTIVITY_FILE="${STATE_DIR}/last_activity_epoch"
LAST_CONTINUE_FILE="${STATE_DIR}/last_continue_epoch"
CONTINUE_COUNT_FILE="${STATE_DIR}/continue_count"
FINISH_FILE="${STATE_DIR}/finish_detected"
STOP_FILE="${STATE_DIR}/stop_requested"
FAIL_FILE="${STATE_DIR}/failed"
ACTIVE_REQUEST_FILE="${STATE_DIR}/active_request"
ACTIVE_REQUEST_STARTED_FILE="${STATE_DIR}/active_request_started_epoch"
ACTIVE_REQUEST_LAST_LOG_FILE="${STATE_DIR}/active_request_last_log_epoch"
SSE_EXIT_FILE="${STATE_DIR}/sse_exit"
SSE_WARNED_FILE="${STATE_DIR}/sse_warned"

mkdir -p "${LOG_DIR}" "${STATE_DIR}"

AUTH_ARGS=()
if [[ -n "${OPENCODE_SERVER_PASSWORD:-}" ]]; then
  AUTH_USER="${OPENCODE_SERVER_USERNAME:-opencode}"
  AUTH_ARGS=(-u "${AUTH_USER}:${OPENCODE_SERVER_PASSWORD}")
fi

log_watchdog() {
  local msg="$1"
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "${msg}" | tee -a "${WATCHDOG_LOG_FILE}" >&2
}

now_epoch() {
  date +%s
}

write_state_file() {
  # Defensive State-Write: Background-Prozesse können beim Shutdown noch kurz laufen.
  # Dadurch entstehen keine sichtbaren "No such file or directory"-Meldungen,
  # falls Cleanup und Event-/Watchdog-Write zeitlich kollidieren.
  local file="$1"
  local value="$2"

  mkdir -p "${STATE_DIR}" 2>/dev/null || return 0
  printf '%s\n' "${value}" > "${file}" 2>/dev/null || true
}

remove_state_files() {
  rm -f "$@" >/dev/null 2>&1 || true
}

write_activity_now() {
  write_state_file "${LAST_ACTIVITY_FILE}" "$(now_epoch)"
}

read_int_file() {
  local file="$1"
  local fallback="$2"

  if [[ -s "${file}" ]]; then
    local value
    value="$(cat "${file}" 2>/dev/null || true)"
    if [[ "${value}" =~ ^[0-9]+$ ]]; then
      echo "${value}"
      return 0
    fi
  fi

  echo "${fallback}"
}

has_server() {
  curl -fsS "${AUTH_ARGS[@]}" "${BASE_URL}/global/health" >/dev/null 2>&1
}

detect_prompt() {
  if [[ $# -gt 0 && -n "${1:-}" ]]; then
    INITIAL_PROMPT="$1"
    PROMPT_SOURCE="cli-argument"
    return 0
  fi

  if [[ -n "${PROMPT_FILE}" ]]; then
    if [[ ! -s "${PROMPT_FILE}" ]]; then
      echo "Fehler: PROMPT_FILE existiert nicht oder ist leer: ${PROMPT_FILE}" >&2
      exit 1
    fi
    INITIAL_PROMPT="$(cat "${PROMPT_FILE}")"
    PROMPT_SOURCE="${PROMPT_FILE}"
    return 0
  fi

  if [[ -s "${DEFAULT_PROMPT_FILE}" ]]; then
    INITIAL_PROMPT="$(cat "${DEFAULT_PROMPT_FILE}")"
    PROMPT_SOURCE="${DEFAULT_PROMPT_FILE}"
    return 0
  fi

  if [[ -s "${TYPO_PROMPT_FILE}" ]]; then
    INITIAL_PROMPT="$(cat "${TYPO_PROMPT_FILE}")"
    PROMPT_SOURCE="${TYPO_PROMPT_FILE}"
    return 0
  fi

  echo "Fehler: Keine Prompt-Datei gefunden." >&2
  echo "Erwartet wird: ${DEFAULT_PROMPT_FILE}" >&2
  echo "Kompatibilitäts-Fallback: ${TYPO_PROMPT_FILE}" >&2
  echo "Alternativ: PROMPT_FILE=/pfad/zur/datei.txt $0" >&2
  exit 1
}

send_message() {
  local session_id="$1"
  local text="$2"
  local label="$3"

  log_watchdog "Sende ${label} an Session ${session_id}."

  write_state_file "${ACTIVE_REQUEST_FILE}" "${label}"
  write_state_file "${ACTIVE_REQUEST_STARTED_FILE}" "$(now_epoch)"

  local curl_args=(-fsS)
  if [[ "${MESSAGE_CURL_MAX_TIME_SECONDS}" != "0" ]]; then
    curl_args+=(--max-time "${MESSAGE_CURL_MAX_TIME_SECONDS}")
  fi

  local response
  local rc=0
  response="$(
    curl "${curl_args[@]}" "${AUTH_ARGS[@]}" \
      -X POST \
      -H "Content-Type: application/json" \
      -d "$(jq -nc --arg text "${text}" '{parts:[{type:"text",text:$text}]}')" \
      "${BASE_URL}/session/${session_id}/message"
  )" || rc=$?

  remove_state_files "${ACTIVE_REQUEST_FILE}" "${ACTIVE_REQUEST_STARTED_FILE}"

  if [[ "${rc}" != "0" ]]; then
    log_watchdog "Fehler beim Senden von ${label}. curl exit code: ${rc}"
    return "${rc}"
  fi

  printf '%s\n' "${response}" >> "${RESPONSE_LOG_FILE}"

  # Fallback: Falls der POST die finale Assistant-Message direkt zurückliefert,
  # erkennen wir finish:"stop" auch ohne SSE-Race.
  local response_finish
  response_finish="$(printf '%s' "${response}" | jq -r '
    .info.finish //
    .properties.info.finish //
    empty
  ' 2>/dev/null || true)"

  local response_role
  response_role="$(printf '%s' "${response}" | jq -r '
    .info.role //
    .properties.info.role //
    empty
  ' 2>/dev/null || true)"

  if [[ "${response_role}" == "assistant" && "${response_finish}" == "stop" ]]; then
    write_state_file "${FINISH_FILE}" "1"
    write_activity_now
    log_watchdog "finish:\"stop\" aus Response erkannt."
  fi

  return 0
}

EVENT_STREAM_PID=""
WATCHDOG_PID=""
INITIAL_MESSAGE_PID=""

cleanup() {
  # Idempotenter Shutdown: erst Stop-Signal setzen, dann bekannte Background-Jobs
  # beenden und warten. Das State-Verzeichnis wird standardmäßig behalten, weil
  # ggf. noch beendende curl/send_message-Subprozesse final schreiben können.
  # Bei Bedarf kann es mit CLEANUP_STATE_DIR=1 nach dem Shutdown gelöscht werden.
  write_state_file "${STOP_FILE}" "1"

  for pid in "${WATCHDOG_PID:-}" "${EVENT_STREAM_PID:-}" "${INITIAL_MESSAGE_PID:-}"; do
    if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
      kill "${pid}" >/dev/null 2>&1 || true
      wait "${pid}" >/dev/null 2>&1 || true
    fi
  done

  sleep 0.2 2>/dev/null || true

  if [[ "${CLEANUP_STATE_DIR}" == "1" && -d "${STATE_DIR}" ]]; then
    rm -rf "${STATE_DIR}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

fail_run() {
  local reason="$1"
  write_state_file "${FAIL_FILE}" "${reason}"
  log_watchdog "FEHLER: ${reason}"
}

require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Fehler: ${cmd} ist erforderlich, aber nicht installiert." >&2
    exit 1
  fi
}

require_cmd jq
require_cmd curl

detect_prompt "$@"

if ! has_server; then
  echo "No OpenCode server on ${BASE_URL}; starting one..."
  nohup opencode serve --hostname "${HOST}" --port "${PORT}" >"${SERVER_LOG_FILE}" 2>&1 &

  for _ in {1..30}; do
    if has_server; then
      break
    fi
    sleep 1
  done
else
  echo "OpenCode server already reachable on ${BASE_URL}."
fi

if ! has_server; then
  echo "OpenCode server did not become healthy. Server log: ${SERVER_LOG_FILE}" >&2
  exit 1
fi

SESSION_JSON="$(
  curl -fsS "${AUTH_ARGS[@]}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{}' \
    "${BASE_URL}/session"
)"

SESSION_ID="$(
  echo "${SESSION_JSON}" | jq -r '.id // .sessionID // .sessionId // empty'
)"

if [[ -z "${SESSION_ID}" ]]; then
  echo "Could not extract session id from response:" >&2
  echo "${SESSION_JSON}" >&2
  exit 1
fi

write_state_file "${SESSION_FILE}" "${SESSION_ID}"
write_activity_now
write_state_file "${LAST_CONTINUE_FILE}" "0"
write_state_file "${CONTINUE_COUNT_FILE}" "0"

RUN_STARTED_AT="$(now_epoch)"

echo "Session: ${SESSION_ID}"
echo "Prompt source: ${PROMPT_SOURCE}"
echo "Event log: ${EVENT_LOG_FILE}"
echo "Watchdog log: ${WATCHDOG_LOG_FILE}"
echo "Response log: ${RESPONSE_LOG_FILE}"
echo "Summary: ${SUMMARY_FILE}"

{
  echo "# OpenCode event stream"
  echo "# Started: $(date --iso-8601=seconds 2>/dev/null || date)"
  echo "# URL: ${BASE_URL}/event"
  echo "# Session: ${SESSION_ID}"
  echo
} > "${EVENT_LOG_FILE}"

{
  echo "# OpenCode watchdog"
  echo "# Started: $(date --iso-8601=seconds 2>/dev/null || date)"
  echo "# Session: ${SESSION_ID}"
  echo "# Prompt source: ${PROMPT_SOURCE}"
  echo "# Timeout seconds: ${WATCHDOG_TIMEOUT_SECONDS}"
  echo "# Max continue count: ${MAX_CONTINUE_COUNT}"
  echo "# Max runtime seconds: ${MAX_RUNTIME_SECONDS}"
  echo "# Min continue gap seconds: ${MIN_CONTINUE_GAP_SECONDS}"
  echo "# Message curl max time seconds: ${MESSAGE_CURL_MAX_TIME_SECONDS}"
  echo "# Active request log interval seconds: ${ACTIVE_REQUEST_LOG_INTERVAL_SECONDS}"
  echo "# Cleanup state dir: ${CLEANUP_STATE_DIR}"
  echo
} > "${WATCHDOG_LOG_FILE}"

# SSE Event Monitor.
# Der Monitor setzt LAST_ACTIVITY für relevante Session-Events und markiert
# finish:"stop". Bricht der SSE-Stream ab, bleibt der Hauptprozess aktiv;
# der Watchdog protokolliert den Ausfall einmalig und nutzt weiter Fallbacks.
(
  set +e
  curl -N -fsS "${AUTH_ARGS[@]}" \
    -H "Accept: text/event-stream" \
    "${BASE_URL}/event" 2>>"${EVENT_LOG_FILE}" \
  | while IFS= read -r line; do
      printf '%s\n' "${line}" >> "${EVENT_LOG_FILE}"

      [[ "${line}" == data:\ * ]] || continue

      json="${line#data: }"

      event_type="$(printf '%s' "${json}" | jq -r '
        .type //
        .event //
        .name //
        empty
      ' 2>/dev/null || true)"

      [[ "${event_type}" == "message.updated" ||
         "${event_type}" == "message.part.updated" ||
         "${event_type}" == "message.part.delta" ]] || continue

      event_session_id="$(printf '%s' "${json}" | jq -r '
        .properties.info.sessionID //
        .properties.info.sessionId //
        .properties.part.sessionID //
        .properties.part.sessionId //
        .properties.sessionID //
        .properties.sessionId //
        .info.sessionID //
        .info.sessionId //
        .part.sessionID //
        .part.sessionId //
        empty
      ' 2>/dev/null || true)"

      [[ "${event_session_id}" == "${SESSION_ID}" ]] || continue

      write_activity_now

      if [[ "${event_type}" == "message.updated" ]]; then
        role="$(printf '%s' "${json}" | jq -r '.properties.info.role // .info.role // empty' 2>/dev/null || true)"
        finish="$(printf '%s' "${json}" | jq -r '.properties.info.finish // .info.finish // empty' 2>/dev/null || true)"

        if [[ "${role}" == "assistant" && "${finish}" == "stop" ]]; then
          write_state_file "${FINISH_FILE}" "1"
          log_watchdog "finish:\"stop\" über SSE erkannt. Watchdog terminiert."
        fi
      fi
    done
  rc=${PIPESTATUS[0]}
  write_state_file "${SSE_EXIT_FILE}" "${rc}"
  printf '[%s] SSE stream exited with curl exit code %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "${rc}" >> "${EVENT_LOG_FILE}"
) &
EVENT_STREAM_PID="$!"

sleep 0.5

(
  send_message "${SESSION_ID}" "${INITIAL_PROMPT}" "initiale Message"
) &
INITIAL_MESSAGE_PID="$!"

# Watchdog Loop.
(
  log_watchdog "Watchdog gestartet."

  local_continue_pid=""

  while true; do
    if [[ -f "${STOP_FILE}" ]]; then
      log_watchdog "Stop requested. Watchdog beendet."
      exit 0
    fi

    if [[ -f "${FINISH_FILE}" ]]; then
      log_watchdog "Finish erkannt. Watchdog beendet."
      exit 0
    fi

    if [[ -f "${SSE_EXIT_FILE}" && ! -f "${SSE_WARNED_FILE}" ]]; then
      sse_rc="$(cat "${SSE_EXIT_FILE}" 2>/dev/null || echo "unknown")"
      log_watchdog "WARNUNG: SSE-Event-Stream wurde beendet. curl exit code: ${sse_rc}. Watchdog nutzt weiterhin Response-/Timeout-Fallbacks."
      write_state_file "${SSE_WARNED_FILE}" "1"
    fi

    current_time="$(now_epoch)"
    runtime_seconds=$((current_time - RUN_STARTED_AT))

    if (( runtime_seconds > MAX_RUNTIME_SECONDS )); then
      fail_run "Maximale Laufzeit überschritten: ${runtime_seconds}s > ${MAX_RUNTIME_SECONDS}s."
      exit 2
    fi

    last_activity="$(read_int_file "${LAST_ACTIVITY_FILE}" "${RUN_STARTED_AT}")"
    last_continue="$(read_int_file "${LAST_CONTINUE_FILE}" "0")"
    continue_count="$(read_int_file "${CONTINUE_COUNT_FILE}" "0")"

    idle_seconds=$((current_time - last_activity))
    continue_gap_seconds=$((current_time - last_continue))

    if (( idle_seconds > WATCHDOG_TIMEOUT_SECONDS )); then
      if [[ -f "${ACTIVE_REQUEST_FILE}" ]]; then
        active_label="$(cat "${ACTIVE_REQUEST_FILE}" 2>/dev/null || echo "unknown")"
        active_started="$(read_int_file "${ACTIVE_REQUEST_STARTED_FILE}" "${current_time}")"
        active_age=$((current_time - active_started))
        last_active_log="$(read_int_file "${ACTIVE_REQUEST_LAST_LOG_FILE}" "0")"
        active_log_gap=$((current_time - last_active_log))

        if (( last_active_log == 0 || active_log_gap >= ACTIVE_REQUEST_LOG_INTERVAL_SECONDS )); then
          log_watchdog "Idle ${idle_seconds}s, aber Request '${active_label}' läuft seit ${active_age}s. Kein paralleler Continue-POST."
          write_state_file "${ACTIVE_REQUEST_LAST_LOG_FILE}" "${current_time}"
        fi

        sleep 2
        continue
      fi

      if (( continue_count >= MAX_CONTINUE_COUNT )); then
        fail_run "Maximale Continue-Anzahl erreicht: ${continue_count}/${MAX_CONTINUE_COUNT}."
        exit 3
      fi

      if (( continue_gap_seconds < MIN_CONTINUE_GAP_SECONDS )); then
        log_watchdog "Idle ${idle_seconds}s, aber letzter Continue erst vor ${continue_gap_seconds}s. Warte bis Mindestabstand erreicht ist."
      elif [[ -n "${local_continue_pid}" ]] && kill -0 "${local_continue_pid}" >/dev/null 2>&1; then
        log_watchdog "Idle ${idle_seconds}s, aber ein Continue-Request läuft bereits."
      else
        if [[ -f "${FINISH_FILE}" ]]; then
          log_watchdog "Finish direkt vor Continue erkannt. Kein Continue nötig."
          exit 0
        fi

        continue_count=$((continue_count + 1))
        write_state_file "${CONTINUE_COUNT_FILE}" "${continue_count}"
        write_state_file "${LAST_CONTINUE_FILE}" "${current_time}"
        write_activity_now

        log_watchdog "Idle ${idle_seconds}s ohne message.updated/message.part.updated und ohne aktiven Request. Sende Continue ${continue_count}/${MAX_CONTINUE_COUNT}."

        (
          send_message "${SESSION_ID}" "${CONTINUE_PROMPT}" "Watchdog-Continue ${continue_count}/${MAX_CONTINUE_COUNT}" || true
        ) &
        local_continue_pid="$!"
      fi
    fi

    sleep 2
  done
) &
WATCHDOG_PID="$!"

wait "${INITIAL_MESSAGE_PID}" >/dev/null 2>&1 || {
  log_watchdog "Initialer Message-Request ist fehlgeschlagen. Details siehe Response-/Watchdog-Log."
}

while true; do
  if [[ -f "${FINISH_FILE}" ]]; then
    RESULT="success"
    EXIT_CODE=0
    break
  fi

  if [[ -f "${FAIL_FILE}" ]]; then
    RESULT="failed"
    EXIT_CODE=2
    break
  fi

  if [[ -f "${STOP_FILE}" ]]; then
    RESULT="stopped"
    EXIT_CODE=130
    break
  fi

  # Falls kein Request mehr aktiv ist, kein Finish erkannt wurde und kein Fail gesetzt ist,
  # bleibt der Watchdog zuständig und sendet nach Timeout einen Continue.
  sleep 1
done

CONTINUE_COUNT_FINAL="$(read_int_file "${CONTINUE_COUNT_FILE}" "0")"
FINISHED_AT="$(date --iso-8601=seconds 2>/dev/null || date)"

{
  echo "result=${RESULT}"
  echo "session_id=${SESSION_ID}"
  echo "base_url=${BASE_URL}"
  echo "prompt_source=${PROMPT_SOURCE}"
  echo "finished_at=${FINISHED_AT}"
  echo "continue_count=${CONTINUE_COUNT_FINAL}"
  echo "watchdog_timeout_seconds=${WATCHDOG_TIMEOUT_SECONDS}"
  echo "max_continue_count=${MAX_CONTINUE_COUNT}"
  echo "max_runtime_seconds=${MAX_RUNTIME_SECONDS}"
  echo "min_continue_gap_seconds=${MIN_CONTINUE_GAP_SECONDS}"
  echo "message_curl_max_time_seconds=${MESSAGE_CURL_MAX_TIME_SECONDS}"
  echo "active_request_log_interval_seconds=${ACTIVE_REQUEST_LOG_INTERVAL_SECONDS}"
  echo "cleanup_state_dir=${CLEANUP_STATE_DIR}"
  echo "state_dir=${STATE_DIR}"
  if [[ -f "${SSE_EXIT_FILE}" ]]; then
    echo "sse_exit_code=$(cat "${SSE_EXIT_FILE}")"
  else
    echo "sse_exit_code="
  fi
  echo "event_log=${EVENT_LOG_FILE}"
  echo "watchdog_log=${WATCHDOG_LOG_FILE}"
  echo "response_log=${RESPONSE_LOG_FILE}"
  if [[ -f "${FAIL_FILE}" ]]; then
    echo "failure_reason=$(cat "${FAIL_FILE}")"
  fi
} > "${SUMMARY_FILE}"

echo
echo "Fertig."
echo "Result: ${RESULT}"
echo "Session: ${SESSION_ID}"
echo "Prompt source: ${PROMPT_SOURCE}"
echo "Continue count: ${CONTINUE_COUNT_FINAL}"
echo "Event log written to: ${EVENT_LOG_FILE}"
echo "Watchdog log written to: ${WATCHDOG_LOG_FILE}"
echo "Response log written to: ${RESPONSE_LOG_FILE}"
echo "Summary written to: ${SUMMARY_FILE}"

exit "${EXIT_CODE}"
