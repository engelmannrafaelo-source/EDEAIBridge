#!/bin/bash

# ===================================================
# Logging Functions für Shell Scripts
# ===================================================
# Version: 2.1 - Multi-Instance Support
# Created: 2025-10-09
# Updated: 2025-10-10
#
# Usage:
#   source scripts/logging_functions.sh
#   log_info "Processing started"
#   log_error "Failed to connect"
#
# Features:
# - Instance identification via INSTANCE_NAME env var
# - Emoji markers for console output
# - Structured logs to file (without emojis)
# - Color-coded console output
# - Log levels: DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL
# ===================================================

# Farben für Terminal-Output
readonly COLOR_RESET='\033[0m'
readonly COLOR_RED='\033[0;31m'
readonly COLOR_YELLOW='\033[1;33m'
readonly COLOR_GREEN='\033[0;32m'
readonly COLOR_BLUE='\033[0;34m'
readonly COLOR_PURPLE='\033[0;35m'

# Log-Level (kann via LOG_LEVEL env variable gesetzt werden)
LOG_LEVEL="${LOG_LEVEL:-INFO}"

# Log-Datei (kann via LOG_FILE env variable gesetzt werden)
LOG_FILE="${LOG_FILE:-logs/startup.log}"

# Instance Identification (für Multi-Instance Deployments)
INSTANCE_NAME="${INSTANCE_NAME:-main}"

# Sicherstellen dass logs/ Verzeichnis existiert
mkdir -p "$(dirname "$LOG_FILE")"

# Hilfsfunktion: Timestamp
get_timestamp() {
    date '+%Y-%m-%d %H:%M:%S'
}

# Hilfsfunktion: Script Name
# When sourced: Use BASH_SOURCE to find the calling script
# BASH_SOURCE[0] = logging_functions.sh
# BASH_SOURCE[1] = format_log_message (the function calling us)
# BASH_SOURCE[2] = the actual script (start-wrappers.sh, stop-wrappers.sh)
get_script_name() {
    # Find first BASH_SOURCE that's not this file
    local i
    for i in "${!BASH_SOURCE[@]}"; do
        local source_file="${BASH_SOURCE[$i]}"
        local source_basename=$(basename "$source_file")

        # Skip this logging functions file and bash builtin
        if [[ "$source_basename" != "logging_functions.sh" && "$source_basename" != "bash" ]]; then
            echo "$source_basename"
            return
        fi
    done

    # Fallback to $0
    basename "$0"
}

# Hilfsfunktion: Formatierte Log-Message
format_log_message() {
    local level="$1"
    local message="$2"
    local color="$3"
    local emoji="$4"

    local timestamp
    timestamp=$(get_timestamp)

    local script_name
    script_name=$(get_script_name)

    # Console: Mit Farbe, Emoji
    echo -e "${color}${emoji} ${message}${COLOR_RESET}"

    # Datei: Ohne Farbe, ohne Emoji, mit Instance-Name
    # Format: timestamp - [instance] - script - level - message
    echo "$timestamp - [$INSTANCE_NAME] - $script_name - $level - $message" >> "$LOG_FILE"
}

# Log-Functions
log_debug() {
    [[ "$LOG_LEVEL" == "DEBUG" ]] || return 0
    format_log_message "DEBUG" "$1" "$COLOR_PURPLE" "🔍"
}

log_info() {
    format_log_message "INFO" "$1" "$COLOR_BLUE" "ℹ️ "
}

log_success() {
    format_log_message "SUCCESS" "$1" "$COLOR_GREEN" "✅"
}

log_warning() {
    format_log_message "WARNING" "$1" "$COLOR_YELLOW" "⚠️ "
}

log_error() {
    format_log_message "ERROR" "$1" "$COLOR_RED" "❌" >&2
}

log_critical() {
    format_log_message "CRITICAL" "$1" "$COLOR_RED" "🚨" >&2
}

# Separator für Log-Readability
log_separator() {
    local separator="=================================================="
    echo "$separator"
    local timestamp
    timestamp=$(get_timestamp)
    local script_name
    script_name=$(get_script_name)
    echo "$timestamp - [$INSTANCE_NAME] - $script_name - INFO - $separator" >> "$LOG_FILE"
}

# Hilfsfunktion: Command mit Logging
run_with_logging() {
    local cmd="$1"
    local description="$2"

    log_info "Running: $description"
    log_debug "Command: $cmd"

    local output
    local exit_code

    # Command ausführen und Output capturen
    if output=$(eval "$cmd" 2>&1); then
        exit_code=0
        log_success "$description completed"
        [[ -n "$output" ]] && log_debug "Output: $output"
    else
        exit_code=$?
        log_error "$description failed (exit code: $exit_code)"
        [[ -n "$output" ]] && log_error "Output: $output"
    fi

    return $exit_code
}

# Error handler mit automatischem Logging und Exit
# LAW 1: Never Silent Failures - ALWAYS show error in console AND file
handle_error() {
    local error_msg="$1"
    local exit_code="${2:-1}"

    # ✅ Console FIRST (garantiert sichtbar, auch wenn logging crashed!)
    {
        echo ""
        echo "╔══════════════════════════════════════════════════════════╗"
        echo "║ ❌ FATAL ERROR                                          ║"
        echo "╠══════════════════════════════════════════════════════════╣"
        # Word wrap long messages
        echo "$error_msg" | fold -w 54 -s | while IFS= read -r line; do
            printf "║ %-56s ║\n" "$line"
        done
        printf "║ %-56s ║\n" ""
        printf "║ %-56s ║\n" "Exit Code: $exit_code"
        echo "╠══════════════════════════════════════════════════════════╣"
        printf "║ %-56s ║\n" "📋 Check logs: ${LOG_FILE:-logs/startup.log}"
        echo "╚══════════════════════════════════════════════════════════╝"
        echo ""
    } >&2

    # ✅ Log to file (mit fallback wenn logging_functions nicht verfügbar)
    if type log_error &>/dev/null; then
        log_error "$error_msg (exit_code: $exit_code)"
    else
        # Fallback: RAW write wenn logging nicht verfügbar
        local log_file="${LOG_FILE:-logs/startup.log}"
        echo "$(date '+%Y-%m-%d %H:%M:%S') - [ERROR] - $error_msg (exit_code: $exit_code)" >> "$log_file" 2>/dev/null || true
    fi

    exit "$exit_code"
}

# Export Functions (für Sub-Shells)
export -f get_timestamp
export -f get_script_name
export -f format_log_message
export -f log_debug
export -f log_info
export -f log_success
export -f log_warning
export -f log_error
export -f log_critical
export -f log_separator
export -f run_with_logging
export -f handle_error
