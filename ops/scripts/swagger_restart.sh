#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${OPS_DIR}/.." && pwd)"
PID_DIR="${OPS_DIR}/pids"
LOG_DIR="${OPS_DIR}/logs"
PID_FILE="${PID_DIR}/swagger.pid"
LOG_FILE="${LOG_DIR}/swagger.log"
HOST="${EXECQUEUE_API_HOST:-0.0.0.0}"
PORT="${EXECQUEUE_API_PORT:-8000}"
APP_MODULE="${EXECQUEUE_API_APP:-execqueue.main:app}"
PYTHON_BIN="${EXECQUEUE_PYTHON_BIN:-python3}"

mkdir -p "${PID_DIR}" "${LOG_DIR}"

log() {
    printf '[swagger_restart] %s\n' "$1"
}

log_to_file() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "${LOG_FILE}"
}

is_pid_running() {
    local pid="$1"
    kill -0 "${pid}" >/dev/null 2>&1
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
    if [[ ! -f "${PID_FILE}" ]]; then
        return 0
    fi

    local pid
    pid="$(cat "${PID_FILE}")"

    if [[ -z "${pid}" ]]; then
        rm -f "${PID_FILE}"
        return 0
    fi

    if ! is_pid_running "${pid}"; then
        rm -f "${PID_FILE}"
        log "Found stale PID ${pid}, nothing to stop."
        log_to_file "Found stale PID ${pid}, nothing to stop."
        return 0
    fi

    log "Stopping existing Swagger/API process ${pid}."
    log_to_file "Stopping existing Swagger/API process ${pid}."
    kill "${pid}" >/dev/null 2>&1 || true

    local waited=0
    while is_pid_running "${pid}" && [[ "${waited}" -lt 20 ]]; do
        sleep 1
        waited=$((waited + 1))
    done

    if is_pid_running "${pid}"; then
        log "Process ${pid} did not stop gracefully, sending SIGKILL."
        log_to_file "Process ${pid} did not stop gracefully, sending SIGKILL."
        kill -9 "${pid}" >/dev/null 2>&1 || true
        sleep 1
    fi

    if is_pid_running "${pid}"; then
        log "Failed to stop process ${pid}."
        log_to_file "Failed to stop process ${pid}."
        return 1
    fi

    rm -f "${PID_FILE}"
    log "Stopped existing process ${pid}."
    log_to_file "Stopped existing process ${pid}."
    return 0
}

start_process() {
    log "Starting Swagger/API service on ${HOST}:${PORT}."
    log_to_file "Starting Swagger/API service on ${HOST}:${PORT}."

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
        log "Swagger/API process failed to start."
        log_to_file "Swagger/API process failed to start."
        rm -f "${PID_FILE}"
        return 1
    fi

    log "Swagger/API service started with PID ${pid}."
    log_to_file "Swagger/API service started with PID ${pid}."
    return 0
}

main() {
    cleanup_stale_pid

    if ! stop_existing_process; then
        log "Restart aborted while stopping the existing process."
        exit 1
    fi

    if ! start_process; then
        log "Restart aborted because the new process did not start."
        exit 1
    fi

    log "Swagger/API restart completed successfully."
    exit 0
}

main "$@"
