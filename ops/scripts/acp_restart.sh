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
PID_FILE="${PID_DIR}/acp.pid"
LOG_FILE="${LOG_DIR}/acp.log"
ACP_ENABLED_RAW="${ACP_ENABLED:-false}"
ACP_ENDPOINT_URL="${ACP_ENDPOINT_URL:-}"

mkdir -p "${PID_DIR}" "${LOG_DIR}"

log() {
    printf '[acp_restart] %s\n' "$1"
}

log_to_file() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "${LOG_FILE}"
}

is_pid_running() {
    local pid="$1"
    kill -0 "${pid}" >/dev/null 2>&1
}

list_matching_pids() {
    local -a found_pids=()
    local pid_text

    if [[ -f "${PID_FILE}" ]]; then
        pid_text="$(cat "${PID_FILE}")"
        if [[ -n "${pid_text}" ]]; then
            found_pids+=("${pid_text}")
        fi
    fi

    # ACP could be a Docker container, external service, or local process
    # Check for common ACP process patterns
    if command -v pgrep >/dev/null 2>&1; then
        while IFS= read -r pid_text; do
            [[ -n "${pid_text}" ]] && found_pids+=("${pid_text}")
        done < <(pgrep -f "acp" || true)
        while IFS= read -r pid_text; do
            [[ -n "${pid_text}" ]] && found_pids+=("${pid_text}")
        done < <(pgrep -f "opencode" || true)
    fi

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

    if [[ "${#pids[@]}" -eq 0 ]]; then
        rm -f "${PID_FILE}"
        log "No ACP process found running."
        return 0
    fi

    for pid in "${pids[@]}"; do
        if ! is_pid_running "${pid}"; then
            log "Found stale PID ${pid}, nothing to stop."
            log_to_file "Found stale PID ${pid}, nothing to stop."
            continue
        fi

        log "Stopping ACP process ${pid}."
        log_to_file "Stopping ACP process ${pid}."
        kill "${pid}" >/dev/null 2>&1 || true
    done

    local waited=0
    local all_stopped=0
    while [[ "${waited}" -lt 20 ]]; do
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
    done

    for pid in "${pids[@]}"; do
        if is_pid_running "${pid}"; then
            log "Process ${pid} did not stop gracefully, sending SIGKILL."
            log_to_file "Process ${pid} did not stop gracefully, sending SIGKILL."
            kill -9 "${pid}" >/dev/null 2>&1 || true
        fi
    done

    sleep 1

    for pid in "${pids[@]}"; do
        if is_pid_running "${pid}"; then
            log "Failed to stop ACP process ${pid}."
            log_to_file "Failed to stop ACP process ${pid}."
            return 1
        fi
    done

    rm -f "${PID_FILE}"
    log "Stopped ACP processes: ${pids[*]}."
    log_to_file "Stopped ACP processes: ${pids[*]}."
    return 0
}

is_acp_enabled() {
    case "${ACP_ENABLED_RAW,,}" in
        1|true|yes|on)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

start_process() {
    if ! is_acp_enabled; then
        log "ACP is disabled. Skipping restart step."
        log_to_file "ACP is disabled. Skipping restart step."
        return 0
    fi

    if [[ -z "${ACP_ENDPOINT_URL}" ]]; then
        log "ACP is enabled but ACP_ENDPOINT_URL is not set."
        log_to_file "ACP is enabled but ACP_ENDPOINT_URL is not set."
        return 1
    fi

    log "ACP endpoint: ${ACP_ENDPOINT_URL}"
    log_to_file "ACP endpoint: ${ACP_ENDPOINT_URL}"

    # Note: ACP may be an external service or Docker container
    # For local processes, define the start command in ACP_START_COMMAND
    if [[ -n "${ACP_START_COMMAND:-}" ]]; then
        log "Starting ACP process with command: ${ACP_START_COMMAND}"
        log_to_file "Starting ACP process with command: ${ACP_START_COMMAND}"

        (
            cd "${PROJECT_ROOT}" || exit 1
            nohup sh -c "${ACP_START_COMMAND}" >> "${LOG_FILE}" 2>&1 &
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
            log "ACP process failed to start."
            log_to_file "ACP process failed to start."
            rm -f "${PID_FILE}"
            return 1
        fi

        log "ACP process started with PID ${pid}."
        log_to_file "ACP process started with PID ${pid}."
    else
        log "ACP_START_COMMAND not set. Assuming ACP is managed externally (Docker/Service)."
        log_to_file "ACP_START_COMMAND not set. Assuming ACP is managed externally."
        log "ACP restart completed (external management)."
        log_to_file "ACP restart completed (external management)."
    fi

    return 0
}

main() {
    cleanup_stale_pid

    if ! stop_existing_process; then
        log "ACP restart aborted while stopping the existing process."
        exit 1
    fi

    if ! start_process; then
        log "ACP restart aborted because the process did not start."
        exit 1
    fi

    log "ACP restart completed successfully."
    exit 0
}

main "$@"
