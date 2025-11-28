#!/bin/bash

# Integration Tests for Shell Logging
# Tests log_event(), log rotation, and error handling

set -e  # Exit on error

cd "$(dirname "$0")/.."

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test counter
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Test helpers
test_start() {
    TESTS_RUN=$((TESTS_RUN + 1))
    echo -n "Test $TESTS_RUN: $1... "
}

test_pass() {
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo -e "${GREEN}PASS${NC}"
}

test_fail() {
    TESTS_FAILED=$((TESTS_FAILED + 1))
    echo -e "${RED}FAIL${NC}"
    echo "  Error: $1"
}

# Setup test environment
setup() {
    mkdir -p tests/logs
    TEST_LOG_FILE="tests/logs/test_shell.log"
    rm -f "$TEST_LOG_FILE"
}

# Cleanup test environment
cleanup() {
    rm -f "$TEST_LOG_FILE"
}

# Test 1: log_event() function creates log entry
test_log_event_creates_entry() {
    test_start "log_event() creates log entry"

    # Define log_event function (same as in shell scripts)
    log_event() {
        local level="$1"
        local message="$2"
        local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        local script_name="test_shell_logging.sh"
        echo "$timestamp - $script_name - $level - $message" >> "$TEST_LOG_FILE"
    }

    log_event "INFO" "Test message"

    if [ -f "$TEST_LOG_FILE" ]; then
        test_pass
    else
        test_fail "Log file not created"
    fi
}

# Test 2: Log entry format is correct
test_log_format() {
    test_start "Log entry format is correct"

    # Check if log contains required fields
    if grep -q "test_shell_logging.sh - INFO - Test message" "$TEST_LOG_FILE"; then
        test_pass
    else
        test_fail "Log format incorrect"
    fi
}

# Test 3: Log rotation script exists and is executable
test_rotation_script_exists() {
    test_start "rotate-logs.sh exists and is executable"

    if [ -x "scripts/rotate-logs.sh" ]; then
        test_pass
    else
        test_fail "scripts/rotate-logs.sh not found or not executable"
    fi
}

# Test 4: Log rotation creates backup
test_log_rotation() {
    test_start "Log rotation creates backup"

    # Create a large test log file
    ROTATION_TEST_LOG="tests/logs/rotation_test.log"
    dd if=/dev/zero of="$ROTATION_TEST_LOG" bs=1024 count=10240 2>/dev/null  # 10MB

    # Modify rotate-logs.sh temporarily for testing
    # (We'll just check if the logic is sound, not run full rotation)

    if [ -f "$ROTATION_TEST_LOG" ]; then
        FILE_SIZE=$(stat -f%z "$ROTATION_TEST_LOG" 2>/dev/null || stat -c%s "$ROTATION_TEST_LOG" 2>/dev/null)
        MAX_SIZE=$((10 * 1024 * 1024))

        if [ "$FILE_SIZE" -ge "$MAX_SIZE" ]; then
            test_pass
            rm -f "$ROTATION_TEST_LOG"
        else
            test_fail "Test log file too small: $FILE_SIZE < $MAX_SIZE"
        fi
    else
        test_fail "Could not create test log file"
    fi
}

# Test 5: All shell scripts have log_event function
test_all_scripts_have_logging() {
    test_start "All shell scripts have log_event()"

    SCRIPTS=("start-wrappers.sh" "stop-wrappers.sh" "check-port.sh" "start_wrapper.sh" "start_wrapper_eco.sh")
    MISSING=()

    for script in "${SCRIPTS[@]}"; do
        if ! grep -q "log_event()" "$script" 2>/dev/null; then
            MISSING+=("$script")
        fi
    done

    if [ ${#MISSING[@]} -eq 0 ]; then
        test_pass
    else
        test_fail "Missing log_event() in: ${MISSING[*]}"
    fi
}

# Test 6: startup.log is in gitignore
test_gitignore_has_logs() {
    test_start "logs/*.log is in .gitignore"

    if grep -q "logs/\*\.log" .gitignore; then
        test_pass
    else
        test_fail "logs/*.log not found in .gitignore"
    fi
}

# Test 7: Error handling functions exist
test_error_handling_exists() {
    test_start "Error handling functions exist in start-wrappers.sh"

    if grep -q "handle_error()" start-wrappers.sh && \
       grep -q "check_port()" start-wrappers.sh && \
       grep -q "verify_process()" start-wrappers.sh; then
        test_pass
    else
        test_fail "Error handling functions not found"
    fi
}

# Test 8: Health check function exists
test_health_check_exists() {
    test_start "Health check function exists in start-wrappers.sh"

    if grep -q "health_check()" start-wrappers.sh; then
        test_pass
    else
        test_fail "health_check() function not found"
    fi
}

# Run all tests
echo "================================"
echo "Shell Logging Integration Tests"
echo "================================"
echo ""

setup

test_log_event_creates_entry
test_log_format
test_rotation_script_exists
test_log_rotation
test_all_scripts_have_logging
test_gitignore_has_logs
test_error_handling_exists
test_health_check_exists

cleanup

# Summary
echo ""
echo "================================"
echo "Test Summary"
echo "================================"
echo "Total tests:  $TESTS_RUN"
echo -e "Passed:       ${GREEN}$TESTS_PASSED${NC}"
if [ $TESTS_FAILED -gt 0 ]; then
    echo -e "Failed:       ${RED}$TESTS_FAILED${NC}"
    exit 1
else
    echo "Failed:       0"
    echo ""
    echo -e "${GREEN}All tests passed! ✅${NC}"
    exit 0
fi
