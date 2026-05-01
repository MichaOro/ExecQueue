#!/usr/bin/env bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${OPS_DIR}/logs"
LOCK_DIR="${OPS_DIR}/locks"
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

    log "Starting step (detached): ${name}"
    log_to_file "Starting step (detached): ${name}"

    # Skript asynchron starten mit setsid für vollständige Entkopplung
    # Damit wird verhindert, dass das Skript sich selbst terminiert, wenn es Prozesse tötet
    setsid "${script_path}" >> "${LOG_DIR}/${name}.log" 2>&1 &
    local pid=$!

    log "Step ${name} started with PID ${pid} (detached)."
    log_to_file "Step ${name} started with PID ${pid} (detached)."

    return 0
}

main() {
    # Define PROJECT_ROOT
    PROJECT_ROOT="$(cd "${OPS_DIR}/.." && pwd)"

    # Lock-Mechanismus: Verhindert parallele global_restart Instanzen
    local LOCK_FILE="${LOCK_DIR}/global_restart.lock"
    if (set -C; echo $$) > "${LOCK_FILE}" 2>/dev/null; then
        trap 'rm -f "${LOCK_FILE}"' EXIT
    else
        local existing_pid
        if [[ -f "${LOCK_FILE}" ]]; then
            existing_pid="$(tr -d '[:space:]' < "${LOCK_FILE}" 2>/dev/null || echo "unknown")"
        fi
        log "Another global_restart is already running (lock by PID ${existing_pid}). Aborting."
        log_to_file "Another global_restart is already running (lock by PID ${existing_pid}). Aborting."
        exit 1
    fi

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
        run_step "${selected_names[$i]}" "${selected_steps[$i]}"
        # Nicht auf Exit-Code warten - alle Skripte laufen asynchron
        log "Step ${selected_names[$i]} launched (checking later)."
        log_to_file "Step ${selected_names[$i]} launched (checking later)."
    done

    log "Global restart launched all steps (detached)."
    log_to_file "Global restart launched all steps (detached)."
    exit 0
}

main "$@"
