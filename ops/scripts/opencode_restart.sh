#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${OPS_DIR}/.." && pwd)"

# Load environment variables from .env if present
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
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
PORT="${OPENCODE_PORT:-4096}"
OPENCODE_BIN="${OPENCODE_BIN:-opencode}"
STARTUP_TIMEOUT_SECONDS="${OPENCODE_STARTUP_TIMEOUT_SECONDS:-10}"
HEALTH_PATH="${OPENCODE_HEALTH_PATH:-/opencode/health}"

mkdir -p "${PID_DIR}" "${LOG_DIR}" "${LOCK_DIR}"

log() {
    printf '[opencode_restart] %s\n' "$1"
}

log_to_file() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "${LOG_FILE}"
}

is_pid_running() {
    local pid="$1"
    [[ "${pid}" =~ ^[0-9]+$ ]] && kill -0 "${pid}" >/dev/null 2>&1
}

acquire_lock() {
    if (set -C; echo $$) > "${LOCK_FILE}" 2>/dev/null; then
        trap 'release_lock' EXIT
        return 0
    fi

    local existing_pid="unknown"
    if [[ -f "${LOCK_FILE}" ]]; then
        existing_pid="$(cat "${LOCK_FILE}" 2>/dev/null || echo "unknown")"
    fi

    if [[ "${existing_pid}" =~ ^[0-9]+$ ]] && ! kill -0 "${existing_pid}" >/dev/null 2>&1; then
        rm -f "${LOCK_FILE}"
        if (set -C; echo $$) > "${LOCK_FILE}" 2>/dev/null; then
            trap 'release_lock' EXIT
            return 0
        fi
    fi

    log "Another restart is in progress (lock held by PID ${existing_pid}). Aborting."
    log_to_file "Another restart is in progress (lock held by PID ${existing_pid}). Aborting."
    return 1
}

release_lock() {
    rm -f "${LOCK_FILE}"
}

list_matching_pids() {
    local -a found_pids=()

    if [[ -f "${PID_FILE}" ]]; then
        local pid_text
        pid_text="$(cat "${PID_FILE}" 2>/dev/null || true)"
        [[ "${pid_text}" =~ ^[0-9]+$ ]] && found_pids+=("${pid_text}")
    fi

    # Match OpenCode serve processes only. Do not kill interactive "opencode" sessions.
    if command -v pgrep >/dev/null 2>&1; then
        while IFS= read -r pid_text; do
            [[ "${pid_text}" =~ ^[0-9]+$ ]] && found_pids+=("${pid_text}")
        done < <(pgrep -f 'opencode[[:space:]]+serve' || true)
    fi

    # Also stop whatever currently owns the configured serve port.
    if command -v lsof >/dev/null 2>&1; then
        while IFS= read -r pid_text; do
            [[ "${pid_text}" =~ ^[0-9]+$ ]] && found_pids+=("${pid_text}")
        done < <(lsof -tiTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null || true)
    fi

    printf '%s\n' "${found_pids[@]}" | awk 'NF { print $1 }' | sort -u
}

stop_existing_process() {
    local -a pids=()
    local pid

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

    for pid in "${pids[@]}"; do
        if is_pid_running "${pid}"; then
            kill -9 "${pid}" >/dev/null 2>&1 || true
        fi
    done

    rm -f "${PID_FILE}"
    log "Existing OpenCode serve processes stopped."
    log_to_file "Existing OpenCode serve processes stopped."
}

port_is_listening() {
    if command -v ss >/dev/null 2>&1; then
        ss -ltnp 2>/dev/null | awk -v port=":${PORT}" '$4 ~ port"$" { found=1 } END { exit found ? 0 : 1 }'
        return $?
    fi

    if command -v lsof >/dev/null 2>&1; then
        lsof -tiTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1
        return $?
    fi

    return 1
}

healthcheck_ok() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsS --max-time 2 "http://${HOST}:${PORT}${HEALTH_PATH}" >/dev/null 2>&1
        return $?
    fi

    port_is_listening
}

start_serve() {
    if ! command -v "${OPENCODE_BIN}" >/dev/null 2>&1; then
        log "OpenCode binary not found: ${OPENCODE_BIN}"
        log_to_file "OpenCode binary not found: ${OPENCODE_BIN}"
        return 1
    fi

    log "Starting OpenCode serve on ${HOST}:${PORT} (project root: ${PROJECT_ROOT})"
    log_to_file "Starting OpenCode serve on ${HOST}:${PORT} (project root: ${PROJECT_ROOT})"

    {
        printf '\n[%s] --- starting opencode serve ---\n' "$(date '+%Y-%m-%d %H:%M:%S')"
        printf '[%s] command: %s serve --hostname %s --port %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "${OPENCODE_BIN}" "${HOST}" "${PORT}"
    } >> "${LOG_FILE}"

    (
        cd "${PROJECT_ROOT}" || exit 1
        exec "${OPENCODE_BIN}" serve \
            --hostname "${HOST}" \
            --port "${PORT}"
    ) >> "${LOG_FILE}" 2>&1 &

    local pid=$!
    echo "${pid}" > "${PID_FILE}"
    log "OpenCode serve started with PID ${pid}. Waiting for readiness..."
    log_to_file "OpenCode serve started with PID ${pid}. Waiting for readiness..."

    local waited=0
    while [[ "${waited}" -lt "${STARTUP_TIMEOUT_SECONDS}" ]]; do
        if ! is_pid_running "${pid}"; then
            log "OpenCode serve process exited before becoming ready. See log: ${LOG_FILE}"
            log_to_file "OpenCode serve process exited before becoming ready."
            tail -n 40 "${LOG_FILE}" >&2 || true
            rm -f "${PID_FILE}"
            return 1
        fi

        if healthcheck_ok || port_is_listening; then
            log "OpenCode serve is ready on ${HOST}:${PORT}."
            log_to_file "OpenCode serve is ready on ${HOST}:${PORT}."
            return 0
        fi

        sleep 1
        waited=$((waited + 1))
    done

    log "OpenCode serve did not become ready within ${STARTUP_TIMEOUT_SECONDS}s. See log: ${LOG_FILE}"
    log_to_file "OpenCode serve did not become ready within ${STARTUP_TIMEOUT_SECONDS}s."
    tail -n 40 "${LOG_FILE}" >&2 || true
    return 1
}

main() {
    if ! acquire_lock; then
        exit 1
    fi

    stop_existing_process

    if ! start_serve; then
        exit 1
    fi

    exit 0
}

main "$@"
