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
    # Define PROJECT_ROOT
    PROJECT_ROOT="$(cd "${OPS_DIR}/.." && pwd)"

    # Build static restart steps - API, Telegram Bot, OpenCode Serve
    local steps=()
    local names=()

    # API restart
    steps+=("${SCRIPT_DIR}/api_restart.sh")
    names+=("api_restart")

    # Telegram Bot restart
    steps+=("${SCRIPT_DIR}/telegram_restart.sh")
    names+=("telegram_restart")

    # OpenCode Serve restart
    steps+=("${SCRIPT_DIR}/opencode_restart.sh")
    names+=("opencode_restart")

    # If arguments are passed, filter steps to those names
    local selected_steps=()
    local selected_names=()
    if [[ "$#" -gt 0 ]]; then
        for arg in "$@"; do
            for i in "${!names[@]}"; do
                if [[ "${names[$i]}" == "$arg" ]]; then
                    selected_steps+=("${steps[$i]}")
                    selected_names+=("${names[$i]}")
                fi
            done
        done
        # If no matching args, keep empty (will do nothing)
    else
        selected_steps=("${steps[@]}")
        selected_names=("${names[@]}")
    fi

    local i
    for ((i = 0; i < ${#selected_steps[@]}; i++)); do
        if ! run_step "${selected_names[$i]}" "${selected_steps[$i]}"; then
            log "Global restart aborted at step: ${selected_names[$i]}"
            log_to_file "Global restart aborted at step: ${selected_names[$i]}"
            exit 1
        fi
    done

    log "Global restart completed successfully."
    log_to_file "Global restart completed successfully."
    exit 0


main "$@"
