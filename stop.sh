#!/bin/bash
# EDEAIBridge - Stop Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🛑 Stopping EDEAIBridge..."

docker compose -f docker/docker-compose.yml down

echo "✅ EDEAIBridge stopped"
