#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${OPS_DIR}/.." && pwd)"

# Load environment variables from .env file if it exists
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi
PID_DIR="${OPS_DIR}/pids"
LOG_DIR="${OPS_DIR}/logs"
LOCK_DIR="${OPS_DIR}/locks"
HEALTH_DIR="${OPS_DIR}/health"
PID_FILE="${PID_DIR}/telegram_bot.pid"
LOCK_FILE="${LOCK_DIR}/telegram.restart.lock"
LOG_FILE="${LOG_DIR}/telegram_bot.log"
HEALTH_FILE="${HEALTH_DIR}/telegram_bot.json"
PYTHON_BIN="${EXECQUEUE_PYTHON_BIN:-python3}"
BOT_MODULE="${EXECQUEUE_TELEGRAM_BOT_MODULE:-execqueue.workers.telegram.bot}"
BOT_ENABLED_RAW="${TELEGRAM_BOT_ENABLED:-false}"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
SHUTDOWN_TIMEOUT="${TELEGRAM_SHUTDOWN_TIMEOUT:-8}"

mkdir -p "${PID_DIR}" "${LOG_DIR}" "${LOCK_DIR}" "${HEALTH_DIR}"

log() {
    printf '[telegram_restart] %s\n' "$1"
}

log_to_file() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "${LOG_FILE}"
}

is_pid_running() {
    local pid="$1"
    kill -0 "${pid}" >/dev/null 2>&1
}

is_numeric_pid() {
    [[ "$1" =~ ^[0-9]+$ ]]
}

is_protected_pid() {
    local pid="$1"
    [[ -z "${pid}" ]] && return 0
    [[ "${pid}" == "$$" ]] && return 0
    [[ "${pid}" == "${PPID:-}" ]] && return 0
    [[ -n "${BASHPID:-}" && "${pid}" == "${BASHPID}" ]] && return 0
    return 1
}

read_pid_file_value() {
    local pid_text

    [[ -f "${PID_FILE}" ]] || return 1
    pid_text="$(tr -d '[:space:]' < "${PID_FILE}" 2>/dev/null || true)"
    [[ -n "${pid_text}" ]] || return 1

    if ! is_numeric_pid "${pid_text}"; then
        log "PID file contained an invalid PID (${pid_text}). Removing stale file."
        log_to_file "PID file contained an invalid PID (${pid_text}). Removing stale file."
        rm -f "${PID_FILE}"
        return 1
    fi

    printf '%s\n' "${pid_text}"
}

acquire_lock() {
    local existing_pid
    local attempts=0

    while [[ "${attempts}" -lt 2 ]]; do
        if (set -C; echo $$) > "${LOCK_FILE}" 2>/dev/null; then
            trap 'release_lock' EXIT
            return 0
        fi

        existing_pid=""
        if [[ -f "${LOCK_FILE}" ]]; then
            existing_pid="$(tr -d '[:space:]' < "${LOCK_FILE}" 2>/dev/null || true)"
        fi

        if [[ -n "${existing_pid}" ]] && is_numeric_pid "${existing_pid}" && is_pid_running "${existing_pid}"; then
            log "Another restart is in progress (lock held by PID ${existing_pid}). Aborting."
            log_to_file "Another restart is in progress (lock held by PID ${existing_pid}). Aborting."
            return 1
        fi

        log "Found stale restart lock. Cleaning up ${LOCK_FILE}."
        log_to_file "Found stale restart lock. Cleaning up ${LOCK_FILE}."
        rm -f "${LOCK_FILE}"
        attempts=$((attempts + 1))
    done

    log "Failed to acquire restart lock after cleaning stale lock file."
    log_to_file "Failed to acquire restart lock after cleaning stale lock file."
    return 1
}

release_lock() {
    rm -f "${LOCK_FILE}"
}

list_matching_pids() {
    local -a found_pids=()
    local pid_text

    # Always check PID file first
    if pid_text="$(read_pid_file_value)"; then
        found_pids+=("${pid_text}")
    fi

    # Find all python processes for this bot module
    if command -v pgrep >/dev/null 2>&1; then
        while IFS= read -r pid_text; do
            [[ -n "${pid_text}" ]] && found_pids+=("${pid_text}")
        done < <(pgrep -f "python.*-m ${BOT_MODULE}" || true)

        while IFS= read -r pid_text; do
            [[ -n "${pid_text}" ]] && found_pids+=("${pid_text}")
        done < <(pgrep -f "${BOT_MODULE}" || true)
    fi

    # Return unique PIDs only
    printf '%s\n' "${found_pids[@]}" | awk 'NF { print $1 }' | sort -u
}

cleanup_stale_pid() {
    local stale_pid

    if stale_pid="$(read_pid_file_value)"; then
        if ! is_pid_running "${stale_pid}"; then
            rm -f "${PID_FILE}"
            log "Removed stale PID file for ${stale_pid}."
            log_to_file "Removed stale PID file for ${stale_pid}."
        fi
    fi
}

health_file_reports_running() {
    [[ -f "${HEALTH_FILE}" ]] || return 1

    "${PYTHON_BIN}" - "${HEALTH_FILE}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    health_data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(1)

status = str(health_data.get("status", "")).lower()
detail = str(health_data.get("detail", "")).lower()

if status in {"ok", "starting"} or "polling" in detail or "running" in detail:
    raise SystemExit(0)

raise SystemExit(1)
PY
}

mark_health_file_stopped() {
    local detail="$1"

    "${PYTHON_BIN}" - "${HEALTH_FILE}" "${detail}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
detail = sys.argv[2]
health_data = {
    "component": "telegram_bot",
    "status": "not_ok",
    "detail": detail,
    "last_check": datetime.now(timezone.utc).isoformat(),
}

if path.exists():
    try:
        existing_data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        existing_data = {}

    if isinstance(existing_data, dict) and "pid" in existing_data:
        health_data["pid"] = existing_data["pid"]

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(health_data, indent=2), encoding="utf-8")
PY
}

verify_no_remaining_processes() {
    local -a remaining_pids=()
    local pid

    while IFS= read -r pid; do
        if [[ -n "${pid}" ]] && is_pid_running "${pid}"; then
            remaining_pids+=("${pid}")
        fi
    done < <(list_matching_pids)

    if [[ "${#remaining_pids[@]}" -gt 0 ]]; then
        log "Restart aborted because Telegram bot process(es) are still alive: ${remaining_pids[*]}."
        log_to_file "Restart aborted because Telegram bot process(es) are still alive: ${remaining_pids[*]}."
        return 1
    fi

    return 0
}

reconcile_health_after_stop() {
    if ! verify_no_remaining_processes; then
        return 1
    fi

    if health_file_reports_running; then
        log "Health file still reports the bot as running after stop. Marking stale state as stopped."
        log_to_file "Health file still reports the bot as running after stop. Marking stale state as stopped."
        mark_health_file_stopped "Telegram bot was stopped by restart script."
    fi

    return 0
}

validate_pid_file_for_start() {
    local existing_pid

    if existing_pid="$(read_pid_file_value)"; then
        if is_pid_running "${existing_pid}"; then
            log "Refusing to start a new Telegram bot process because PID file points to running process ${existing_pid}."
            log_to_file "Refusing to start a new Telegram bot process because PID file points to running process ${existing_pid}."
            return 1
        fi

        rm -f "${PID_FILE}"
        log "Removed stale PID file before start (${existing_pid})."
        log_to_file "Removed stale PID file before start (${existing_pid})."
    fi

    return 0
}

stop_existing_process() {
    local -a pids=()
    local pid

    while IFS= read -r pid; do
        [[ -n "${pid}" ]] && pids+=("${pid}")
    done < <(list_matching_pids)

    # Remove duplicates and filter out current shell process
    local -a unique_pids=()
    local seen_pids=""
    for pid in "${pids[@]}"; do
        if is_protected_pid "${pid}"; then
            continue
        fi
        if [[ ! " ${seen_pids} " =~ " ${pid} " ]]; then
            unique_pids+=("${pid}")
            seen_pids="${seen_pids} ${pid}"
        fi
    done
    pids=("${unique_pids[@]}")

    if [[ "${#pids[@]}" -eq 0 ]]; then
        rm -f "${PID_FILE}"
        log "No existing Telegram bot processes found."
        log_to_file "No existing Telegram bot processes found."
        return 0
    fi

    log "Found ${#pids[@]} existing Telegram bot process(es): ${pids[*]}."
    log_to_file "Found ${#pids[@]} existing Telegram bot process(es): ${pids[*]}."

    # First pass: graceful SIGTERM to all
    for pid in "${pids[@]}"; do
        if ! is_pid_running "${pid}"; then
            log "Process ${pid} is already stopped (stale). Removing from list."
            continue
        fi

        log "Sending SIGTERM to Telegram bot process ${pid}."
        log_to_file "Sending SIGTERM to Telegram bot process ${pid}."
        kill "${pid}" >/dev/null 2>&1 || true
    done

    # Wait for graceful shutdown (bounded by TELEGRAM_SHUTDOWN_TIMEOUT)
    local waited=0
    local all_stopped=0
    while [[ "${waited}" -lt "${SHUTDOWN_TIMEOUT}" ]]; do
        all_stopped=1
        for pid in "${pids[@]}"; do
            if is_pid_running "${pid}"; then
                all_stopped=0
                break
            fi
        done
        if [[ "${all_stopped}" -eq 1 ]]; then
            break
        fi
        sleep 1
        waited=$((waited + 1))
        log "Waiting for processes to stop... (${waited}/${SHUTDOWN_TIMEOUT}s)"
    done

    # Second pass: force SIGKILL to any remaining
    local force_killed=0
    for pid in "${pids[@]}"; do
        if is_pid_running "${pid}"; then
            log "Process ${pid} did not stop gracefully, sending SIGKILL."
            log_to_file "Process ${pid} did not stop gracefully, sending SIGKILL."
            kill -9 "${pid}" >/dev/null 2>&1 || true
            force_killed=1
        fi
    done

    if [[ "${force_killed}" -eq 1 ]]; then
        sleep 1
    fi

    # Final verification
    for pid in "${pids[@]}"; do
        if is_pid_running "${pid}"; then
            log "WARNING: Failed to stop process ${pid}."
            log_to_file "WARNING: Failed to stop process ${pid}."
        fi
    done

    rm -f "${PID_FILE}"

    if ! reconcile_health_after_stop; then
        return 1
    fi

    log "Stopped existing Telegram bot processes: ${pids[*]}."
    log_to_file "Stopped existing Telegram bot processes: ${pids[*]}."
    return 0
}

is_bot_enabled() {
    case "${BOT_ENABLED_RAW,,}" in
        1|true|yes|on)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

start_process() {
    if ! is_bot_enabled; then
        log "Telegram bot is disabled. Skipping restart step."
        log_to_file "Telegram bot is disabled. Skipping restart step."
        return 0
    fi

    if [[ -z "${BOT_TOKEN}" ]]; then
        log "Telegram bot is enabled but TELEGRAM_BOT_TOKEN is not set."
        log_to_file "Telegram bot is enabled but TELEGRAM_BOT_TOKEN is not set."
        return 1
    fi

    if ! validate_pid_file_for_start; then
        return 1
    fi

    if ! verify_no_remaining_processes; then
        return 1
    fi

    if health_file_reports_running; then
        log "Health file still indicated a running bot before start. Clearing stale state first."
        log_to_file "Health file still indicated a running bot before start. Clearing stale state first."
        mark_health_file_stopped "Telegram bot restart cleared stale running state before start."
    fi

    log "Starting Telegram bot process."
    log_to_file "Starting Telegram bot process."

    (
        cd "${PROJECT_ROOT}" || exit 1
        nohup "${PYTHON_BIN}" -m "${BOT_MODULE}" >> "${LOG_FILE}" 2>&1 &
        echo $! > "${PID_FILE}"
    )

    if [[ ! -f "${PID_FILE}" ]]; then
        log "PID file was not created."
        log_to_file "PID file was not created."
        return 1
    fi

    local pid
    pid="$(tr -d '[:space:]' < "${PID_FILE}" 2>/dev/null || true)"

    if [[ -z "${pid}" ]] || ! is_numeric_pid "${pid}"; then
        log "PID file did not contain a valid numeric PID after start."
        log_to_file "PID file did not contain a valid numeric PID after start."
        rm -f "${PID_FILE}"
        return 1
    fi

    sleep 2

    if [[ -z "${pid}" ]] || ! is_pid_running "${pid}"; then
        log "Telegram bot process failed to start."
        log_to_file "Telegram bot process failed to start."
        rm -f "${PID_FILE}"
        return 1
    fi

    if ! health_file_reports_running; then
        log "Health file has not reported the bot as running yet. Continuing because process ${pid} is alive."
        log_to_file "Health file has not reported the bot as running yet. Continuing because process ${pid} is alive."
    fi

    log "Telegram bot process started with PID ${pid}."
    log_to_file "Telegram bot process started with PID ${pid}."
    return 0
}

main() {
    # Acquire lock to prevent concurrent restarts
    if ! acquire_lock; then
        exit 1
    fi

    cleanup_stale_pid

    if ! stop_existing_process; then
        log "Restart aborted while stopping the existing Telegram bot process."
        exit 1
    fi

    if ! start_process; then
        log "Restart aborted because the Telegram bot process did not start."
        exit 1
    fi

    log "Telegram bot restart completed successfully."
    exit 0
}

main "$@"
