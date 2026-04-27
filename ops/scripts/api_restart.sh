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
PID_FILE="${PID_DIR}/api.pid"
LOCK_FILE="${LOCK_DIR}/api.restart.lock"
LOG_FILE="${LOG_DIR}/api.log"
HOST="${EXECQUEUE_API_HOST:-0.0.0.0}"
PORT="${EXECQUEUE_API_PORT:-8000}"
APP_MODULE="${EXECQUEUE_API_APP:-execqueue.main:app}"
PYTHON_BIN="${EXECQUEUE_PYTHON_BIN:-python3}"

mkdir -p "${PID_DIR}" "${LOG_DIR}" "${LOCK_DIR}"

log() {
    printf '[api_restart] %s\n' "$1"
}

log_to_file() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "${LOG_FILE}"
}

is_pid_running() {
    local pid="$1"
    kill -0 "${pid}" >/dev/null 2>&1
}

is_protected_pid() {
    local pid="$1"
    [[ -z "${pid}" ]] && return 0
    [[ "${pid}" == "$$" ]] && return 0
    [[ "${pid}" == "${PPID:-}" ]] && return 0
    [[ -n "${BASHPID:-}" && "${pid}" == "${BASHPID}" ]] && return 0
    return 1
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

    # Find all uvicorn processes for this app module
    if command -v pgrep >/dev/null 2>&1; then
        while IFS= read -r pid_text; do
            [[ -n "${pid_text}" ]] && found_pids+=("${pid_text}")
        done < <(pgrep -f "uvicorn ${APP_MODULE}" || true)
    fi

    # Check for processes listening on the port
    if command -v lsof >/dev/null 2>&1; then
        while IFS= read -r pid_text; do
            [[ -n "${pid_text}" ]] && found_pids+=("${pid_text}")
        done < <(lsof -tiTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true)
    elif command -v fuser >/dev/null 2>&1; then
        for pid_text in $(fuser "${PORT}/tcp" 2>/dev/null || true); do
            [[ -n "${pid_text}" ]] && found_pids+=("${pid_text}")
        done
    elif command -v ss >/dev/null 2>&1; then
        while IFS= read -r pid_text; do
            [[ -n "${pid_text}" ]] && found_pids+=("${pid_text}")
        done < <(
            ss -lptn "sport = :${PORT}" 2>/dev/null \
            | sed -n 's/.*pid=\([0-9]\+\).*/\1/p' \
            || true
        )
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
        log "No existing API processes found."
        log_to_file "No existing API processes found."
        return 0
    fi

    log "Found ${#pids[@]} existing API process(es): ${pids[*]}."
    log_to_file "Found ${#pids[@]} existing API process(es): ${pids[*]}."

    # First pass: graceful SIGTERM to all
    for pid in "${pids[@]}"; do
        if ! is_pid_running "${pid}"; then
            log "Process ${pid} is already stopped (stale). Removing from list."
            continue
        fi

        log "Sending SIGTERM to API process ${pid}."
        log_to_file "Sending SIGTERM to API process ${pid}."
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

    # Final verification: port should be free
    local port_still_in_use=0
    if command -v lsof >/dev/null 2>&1; then
        if lsof -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
            port_still_in_use=1
        fi
    elif command -v ss >/dev/null 2>&1; then
        if ss -lptn "sport = :${PORT}" 2>/dev/null | grep -q .; then
            port_still_in_use=1
        fi
    fi

    if [[ "${port_still_in_use}" -eq 1 ]]; then
        log "WARNING: Port ${PORT} is still in use after killing processes."
        log_to_file "WARNING: Port ${PORT} is still in use after killing processes."
        # Try one more aggressive cleanup
        if command -v fuser >/dev/null 2>&1; then
            fuser -k "${PORT}/tcp" 2>/dev/null || true
            sleep 1
        fi
    fi

    rm -f "${PID_FILE}"
    log "Stopped existing API processes: ${pids[*]}."
    log_to_file "Stopped existing API processes: ${pids[*]}."
    return 0
}

start_process() {
    log "Starting API service on ${HOST}:${PORT}."
    log_to_file "Starting API service on ${HOST}:${PORT}."

    (
        cd "${PROJECT_ROOT}" || exit 1
        nohup "${PYTHON_BIN}" -m uvicorn "${APP_MODULE}" --host "${HOST}" --port "${PORT}" >> "${LOG_FILE}" 2>&1 &
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
        log "API process failed to start."
        log_to_file "API process failed to start."
        rm -f "${PID_FILE}"
        return 1
    fi

    log "API service started with PID ${pid}."
    log_to_file "API service started with PID ${pid}."
    return 0
}

main() {
    # Acquire lock to prevent concurrent restarts
    if ! acquire_lock; then
        exit 1
    fi

    cleanup_stale_pid

    if ! stop_existing_process; then
        log "Restart aborted while stopping the existing process."
        exit 1
    fi

    if ! start_process; then
        log "Restart aborted because the new process did not start."
        exit 1
    fi

    log "API restart completed successfully."
    exit 0
}

main "$@"
