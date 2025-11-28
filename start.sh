#!/bin/bash
# EDEAIBridge - Start Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Starting EDEAIBridge..."

# Check for secrets
if [ ! -f "secrets/claude_token.txt" ]; then
    echo "❌ Error: secrets/claude_token.txt not found!"
    echo "   Run: claude login"
    echo "   Then copy your token to secrets/claude_token.txt"
    exit 1
fi

# Check for .env
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env not found, using defaults"
    echo "   Copy .env.example to .env and configure TAVILY_API_KEY"
fi

# Build and start
docker compose -f docker/docker-compose.yml up -d --build

echo ""
echo "✅ EDEAIBridge started!"
echo ""
echo "📡 Endpoints:"
echo "   Health:  http://localhost:8000/health"
echo "   Chat:    http://localhost:8000/v1/chat/completions"
echo "   Research: http://localhost:8000/v1/research"
echo "   Docs:    http://localhost:8000/docs"
echo ""
echo "📋 Commands:"
echo "   Logs:    ./logs.sh"
echo "   Stop:    ./stop.sh"
echo "   Restart: ./restart.sh"
