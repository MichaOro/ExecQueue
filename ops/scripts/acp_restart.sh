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
PID_FILE="${PID_DIR}/acp.pid"
LOCK_FILE="${LOCK_DIR}/acp.restart.lock"
LOG_FILE="${LOG_DIR}/acp.log"
ACP_ENABLED_RAW="${ACP_ENABLED:-false}"
ACP_ENDPOINT_URL="${ACP_ENDPOINT_URL:-}"

mkdir -p "${PID_DIR}" "${LOG_DIR}" "${LOCK_DIR}"

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

    # Only check for explicit ACP process patterns from PID file
    # Avoid matching unrelated processes
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
        log "No ACP process found running."
        log_to_file "No ACP process found running."
        return 0
    fi

    log "Found ${#pids[@]} existing ACP process(es): ${pids[*]}."
    log_to_file "Found ${#pids[@]} existing ACP process(es): ${pids[*]}."

    # First pass: graceful SIGTERM to all
    for pid in "${pids[@]}"; do
        if ! is_pid_running "${pid}"; then
            log "Process ${pid} is already stopped (stale). Removing from list."
            continue
        fi

        log "Sending SIGTERM to ACP process ${pid}."
        log_to_file "Sending SIGTERM to ACP process ${pid}."
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
        log "ACP will be in DEGRADED state (externally managed or not running)."
        log_to_file "ACP will be in DEGRADED state (externally managed or not running)."
        # Don't fail - ACP may be managed externally or intentionally disabled
        return 0
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
    # Acquire lock to prevent concurrent restarts
    if ! acquire_lock; then
        exit 1
    fi

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
