#!/bin/bash
set -e

# Fix permissions for volume directories at runtime
# This must run as root before dropping to claude user
chown -R claude:claude /app/logs /app/instances

# Graceful shutdown handler
shutdown_handler() {
    echo "🛑 Graceful shutdown initiated..."

    # Get uvicorn PID (running as claude user)
    UVICORN_PID=$(pgrep -u claude -f "uvicorn.*main:app" || true)

    if [ -n "$UVICORN_PID" ]; then
        echo "📡 Sending SIGTERM to uvicorn (PID: $UVICORN_PID)..."
        kill -TERM "$UVICORN_PID" 2>/dev/null || true

        # Wait up to 10 seconds for graceful shutdown
        for i in {1..10}; do
            if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
                echo "✅ Uvicorn stopped gracefully"
                break
            fi
            sleep 1
        done

        # Force kill if still running
        if kill -0 "$UVICORN_PID" 2>/dev/null; then
            echo "⚠️  Force killing uvicorn..."
            kill -KILL "$UVICORN_PID" 2>/dev/null || true
        fi
    fi

    echo "✅ Shutdown complete"
    exit 0
}

# Trap SIGTERM and SIGINT (sent by docker stop)
trap shutdown_handler SIGTERM SIGINT

# Drop privileges and execute CMD as claude user in background
gosu claude "$@" &

# Store child PID
CHILD_PID=$!

# Wait for child process (uvicorn)
wait $CHILD_PID