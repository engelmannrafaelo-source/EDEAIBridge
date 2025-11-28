#!/bin/bash
# EDEAIBridge - Restart Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔄 Restarting EDEAIBridge..."

docker compose -f docker/docker-compose.yml restart

echo "✅ EDEAIBridge restarted"
