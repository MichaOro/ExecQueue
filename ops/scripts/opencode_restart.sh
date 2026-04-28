#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${OPS_DIR}/.." && pwd)"

# Load environment variables from .env if present
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    source "${PROJECT_ROOT}/.env"
    set +a
fi

PID_DIR="${OPS_DIR}/pids"
LOG_DIR="${OPS_DIR}/logs"
LOCK_DIR="${OPS_DIR}/locks"
PID_FILE="${PID_DIR}/opencode_serve.pid"
LOCK_FILE="${LOCK_DIR}/opencode.restart.lock"
LOG_FILE="${LOG_DIR}/opencode_serve.log"

HOST="${OPENCODE_HOST:-127.0.0.1}"
PORT="${OPENCODE_PORT:-5000}"
PYTHON_BIN="${OPENCODE_PYTHON_BIN:-python3}"

mkdir -p "${PID_DIR}" "${LOG_DIR}" "${LOCK_DIR}"

log() {
    printf '[opencode_restart] %s\n' "$1"
}

log_to_file() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "${LOG_FILE}"
}

is_pid_running() {
    local pid="$1"
    kill -0 "${pid}" >/dev/null 2>&1
}

acquire_lock() {
    if (set -C; echo $$) > "${LOCK_FILE}" 2>/dev/null; then
        trap 'release_lock' EXIT
        return 0
    else
        local existing_pid=""
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
    # Check PID file first
    if [[ -f "${PID_FILE}" ]]; then
        local pid_text="$(cat "${PID_FILE}")"
        [[ -n "${pid_text}" ]] && found_pids+=("${pid_text}")
    fi
    # Find any opencode serve processes (simple grep on command line)
    if command -v pgrep >/dev/null 2>&1; then
        while IFS= read -r pid_text; do
            [[ -n "${pid_text}" ]] && found_pids+=("${pid_text}")
        done < <(pgrep -f "opencode serve" || true)
    fi
    # Also consider processes listening on the configured port
    if command -v lsof >/dev/null 2>&1; then
        while IFS= read -r pid_text; do
            [[ -n "${pid_text}" ]] && found_pids+=("${pid_text}")
        done < <(lsof -tiTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true)
    fi
    printf '%s\n' "${found_pids[@]}" | awk 'NF { print $1 }' | sort -u
}

stop_existing_process() {
    local -a pids=()
    while IFS= read -r pid; do
        [[ -n "${pid}" ]] && pids+=("${pid}")
    done < <(list_matching_pids)

    if [[ "${#pids[@]}" -eq 0 ]]; then
        rm -f "${PID_FILE}"
        log "No existing OpenCode serve processes found."
        log_to_file "No existing OpenCode serve processes found."
        return 0
    fi

    log "Stopping ${#pids[@]} existing OpenCode serve process(es): ${pids[*]}"
    log_to_file "Stopping ${#pids[@]} existing OpenCode serve process(es): ${pids[*]}"

    for pid in "${pids[@]}"; do
        if is_pid_running "${pid}"; then
            kill "${pid}" >/dev/null 2>&1 || true
        fi
    done

    # Wait up to 5 seconds for graceful stop
    local waited=0
    while [[ "${waited}" -lt 5 ]]; do
        local all_gone=1
        for pid in "${pids[@]}"; do
            if is_pid_running "${pid}"; then
                all_gone=0
                break
            fi
        done
        [[ "${all_gone}" -eq 1 ]] && break
        sleep 1
        waited=$((waited + 1))
    done

    # Force kill any remaining
    for pid in "${pids[@]}"; do
        if is_pid_running "${pid}"; then
            kill -9 "${pid}" >/dev/null 2>&1 || true
        fi
    done

    rm -f "${PID_FILE}"
    log "Existing OpenCode serve processes stopped."
    log_to_file "Existing OpenCode serve processes stopped."
}

start_serve() {
    log "Starting OpenCode serve on ${HOST}:${PORT} (project root: ${PROJECT_ROOT})"
    log_to_file "Starting OpenCode serve on ${HOST}:${PORT} (project root: ${PROJECT_ROOT})"
    # Run in background, redirect stdout+stderr to log file
    ${PYTHON_BIN} -m opencode serve \
        --host "${HOST}" \
        --port "${PORT}" \
        --project-root "${PROJECT_ROOT}" \
        --log-level INFO \
        >> "${LOG_FILE}" 2>&1 &
    local pid=$!
    echo "${pid}" > "${PID_FILE}"
    log "OpenCode serve started with PID ${pid}."
    log_to_file "OpenCode serve started with PID ${pid}."
}

main() {
    if ! acquire_lock; then
        exit 1
    fi
    stop_existing_process
    start_serve
    # Do not release lock here; let trap handle it
    exit 0
}

main "$@"
