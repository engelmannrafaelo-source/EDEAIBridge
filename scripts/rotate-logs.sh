#!/bin/bash

# Log Rotation Script for startup.log
# Purpose: Prevent startup.log from growing unbounded
# Rotation: Keep 5 backups, max 10MB per file (same as Python logs)
# Usage: Run manually or via cron

cd "$(dirname "$0")/.."

# Load central logging functions
source scripts/logging_functions.sh

LOG_FILE="logs/startup.log"
MAX_SIZE=$((10 * 1024 * 1024))  # 10MB in bytes
BACKUP_COUNT=5

# Check if log file exists
if [ ! -f "$LOG_FILE" ]; then
    log_warning "No log file to rotate: $LOG_FILE"
    exit 0
fi

# Get file size (cross-platform: macOS and Linux)
if [[ "$OSTYPE" == "darwin"* ]]; then
    FILE_SIZE=$(stat -f%z "$LOG_FILE" 2>/dev/null)
else
    FILE_SIZE=$(stat -c%s "$LOG_FILE" 2>/dev/null)
fi

# Check if rotation needed
if [ "$FILE_SIZE" -lt "$MAX_SIZE" ]; then
    FILE_SIZE_MB=$(( FILE_SIZE / 1024 / 1024 ))
    log_info "Log file size: ${FILE_SIZE_MB}MB (< 10MB) - no rotation needed"
    exit 0
fi

FILE_SIZE_MB=$(( FILE_SIZE / 1024 / 1024 ))
log_separator
log_info "Starting log rotation (file size: ${FILE_SIZE_MB}MB > 10MB)"

# Rotate backups (startup.log.5 -> delete, .4 -> .5, etc.)
for i in $(seq $((BACKUP_COUNT - 1)) -1 1); do
    CURRENT="$LOG_FILE.$i"
    NEXT="$LOG_FILE.$((i + 1))"

    if [ -f "$CURRENT" ]; then
        mv "$CURRENT" "$NEXT"
        log_debug "Rotated: $(basename $CURRENT) -> $(basename $NEXT)"
    fi
done

# Move current log to .1
mv "$LOG_FILE" "$LOG_FILE.1"
log_info "Rotated: startup.log -> startup.log.1"

# Create new empty log file
touch "$LOG_FILE"
log_success "Created new empty log file"

# Log rotation event to new file
log_info "Log rotation completed (rotated ${FILE_SIZE_MB}MB)"

log_separator
log_success "Log rotation complete!"

# Show backup files
echo ""
echo "Backup files:"
ls -lh logs/startup.log* 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
