#!/bin/bash
# EDEAIBridge - Logs Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ "$1" == "--tail" ]; then
    docker compose -f docker/docker-compose.yml logs --tail=100
else
    docker compose -f docker/docker-compose.yml logs -f
fi
