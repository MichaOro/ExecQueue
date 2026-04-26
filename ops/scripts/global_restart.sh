#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${OPS_DIR}/logs"
GLOBAL_LOG_FILE="${LOG_DIR}/global_restart.log"

mkdir -p "${LOG_DIR}"

log() {
    printf '[global_restart] %s\n' "$1"
}

log_to_file() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$1" >> "${GLOBAL_LOG_FILE}"
}

run_step() {
    local name="$1"
    local script_path="$2"

    log "Running step: ${name}"
    log_to_file "Running step: ${name}"

    "${script_path}"
    local exit_code=$?

    if [[ "${exit_code}" -ne 0 ]]; then
        log "Step failed: ${name} (exit code ${exit_code})"
        log_to_file "Step failed: ${name} (exit code ${exit_code})"
        return "${exit_code}"
    fi

    log "Step completed: ${name}"
    log_to_file "Step completed: ${name}"
    return 0
}

main() {
    # Load environment to check ACP_ENABLED
    if [[ -f "${PROJECT_ROOT}/.env" ]]; then
        set -a
        source "${PROJECT_ROOT}/.env"
        set +a
    fi

    # Build steps dynamically based on ACP configuration
    local steps=()
    local names=()

    # Always restart API
    steps+=("${SCRIPT_DIR}/api_restart.sh")
    names+=("api_restart")

    # Always restart Telegram Bot
    steps+=("${SCRIPT_DIR}/telegram_restart.sh")
    names+=("telegram_restart")

    # Optionally restart ACP if enabled
    case "${ACP_ENABLED:-false}" in
        1|true|yes|on)
            steps+=("${SCRIPT_DIR}/acp_restart.sh")
            names+=("acp_restart")
            log "ACP is enabled, will include ACP restart in global restart."
            ;;
        *)
            log "ACP is disabled, skipping ACP restart in global restart."
            ;;
    esac

    local i
    for ((i = 0; i < ${#steps[@]}; i++)); do
        if ! run_step "${names[$i]}" "${steps[$i]}"; then
            log "Global restart aborted at step: ${names[$i]}"
            log_to_file "Global restart aborted at step: ${names[$i]}"
            exit 1
        fi
    done

    log "Global restart completed successfully."
    log_to_file "Global restart completed successfully."
    exit 0
}

main "$@"
