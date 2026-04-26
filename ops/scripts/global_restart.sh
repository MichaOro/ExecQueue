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
    local steps=(
        "${SCRIPT_DIR}/api_restart.sh"
        "${SCRIPT_DIR}/telegram_restart.sh"
    )

    local names=(
        "api_restart"
        "telegram_restart"
    )

    local i
    for ((i = 0; i < ${#steps[@]}; i++)); do
        if ! run_step "${names[$i]}" "${steps[$i]}"; then
            log "Global restart aborted."
            log_to_file "Global restart aborted."
            exit 1
        fi
    done

    log "Global restart completed successfully."
    log_to_file "Global restart completed successfully."
    exit 0
}

main "$@"
