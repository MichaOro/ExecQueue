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
PID_FILE="${PID_DIR}/telegram_bot.pid"
LOCK_FILE="${LOCK_DIR}/telegram.restart.lock"
LOG_FILE="${LOG_DIR}/telegram_bot.log"
PYTHON_BIN="${EXECQUEUE_PYTHON_BIN:-python3}"
BOT_MODULE="${EXECQUEUE_TELEGRAM_BOT_MODULE:-execqueue.workers.telegram.bot}"
BOT_ENABLED_RAW="${TELEGRAM_BOT_ENABLED:-false}"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"

mkdir -p "${PID_DIR}" "${LOG_DIR}" "${LOCK_DIR}"

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

acquire_lock() {
    # Try to create lock file atomically
    if (set -C; echo $$) > "${LOCK_FILE}" 2>/dev/null; then
        # Set trap to release lock on exit
        trap 'release_lock' EXIT
        return 0
    else
        local existing_pid
        if [[ -f "${LOCK_FILE}" ]]; then
            existing_pid="$(cat "${LOCK_FILE}" 2>/dev/null || echo "unknown")"
        fi
        log "Another restart is in progress (lock held by PID ${existing_pid}). Aborting."
        log_to_file "Another restart is in progress (lock held by PID ${existing_pid}). Aborting."
        return 1
    fi
}

release_lock() {
    rm -f "${LOCK_FILE}"
}

list_matching_pids() {
    local -a found_pids=()
    local pid_text

    # Always check PID file first
    if [[ -f "${PID_FILE}" ]]; then
        pid_text="$(cat "${PID_FILE}")"
        if [[ -n "${pid_text}" ]]; then
            found_pids+=("${pid_text}")
        fi
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
    if [[ -f "${PID_FILE}" ]]; then
        local stale_pid
        stale_pid="$(cat "${PID_FILE}")"
        if [[ -n "${stale_pid}" ]] && ! is_pid_running "${stale_pid}"; then
            rm -f "${PID_FILE}"
            log "Removed stale PID file for ${stale_pid}."
            log_to_file "Removed stale PID file for ${stale_pid}."
        fi
    fi
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
        if [[ ! " ${seen_pids} " =~ " ${pid} " ]] && [[ "${pid}" != "$$" ]]; then
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

    # Wait for graceful shutdown (up to 10 seconds)
    local waited=0
    local all_stopped=0
    while [[ "${waited}" -lt 10 ]]; do
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
        log "Waiting for processes to stop... (${waited}/10s)"
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
    pid="$(cat "${PID_FILE}")"
    sleep 2

    if [[ -z "${pid}" ]] || ! is_pid_running "${pid}"; then
        log "Telegram bot process failed to start."
        log_to_file "Telegram bot process failed to start."
        rm -f "${PID_FILE}"
        return 1
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
