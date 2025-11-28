# EDEAIBridge

**OpenAI-compatible API Gateway for Claude Code**

A production-ready FastAPI wrapper that provides OpenAI-compatible endpoints for Claude AI, enabling seamless integration with applications expecting OpenAI API format.

## Features

- **OpenAI-Compatible API**: Drop-in replacement for OpenAI API calls
- **Research Endpoint**: Deep research capabilities via `/v1/research`
- **Free Access**: Uses Claude OAuth (no API costs!)
- **Docker Ready**: Production deployment with health checks
- **Privacy/DSGVO**: Built-in PII anonymization with Presidio

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Claude OAuth Token (free via `claude login`)
- Tavily API Key (for research - get at [tavily.com](https://tavily.com))

### Installation

```bash
# 1. Clone repository
git clone https://github.com/yourusername/EDEAIBridge.git
cd EDEAIBridge

# 2. Setup Claude OAuth token
claude login
# Copy the token to secrets/claude_token.txt

# 3. Configure environment
cp .env.example .env
# Edit .env and add your TAVILY_API_KEY

# 4. Start the service
./start.sh
```

### Verify Installation

```bash
# Health check
curl http://localhost:8000/health

# Test completion
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-key" \
  -d '{
    "model": "claude-sonnet-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## API Endpoints

### Chat Completions (OpenAI-compatible)
```
POST /v1/chat/completions
```

### Research (SuperClaude)
```
POST /v1/research
```

### Models List
```
GET /v1/models
```

### Health Check
```
GET /health
```

## Usage Examples

### Python (OpenAI SDK)
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="any-key"  # Auth handled by Claude OAuth
)

response = client.chat.completions.create(
    model="claude-sonnet-4",
    messages=[{"role": "user", "content": "Explain quantum computing"}]
)
print(response.choices[0].message.content)
```

### Research Endpoint
```python
import requests

response = requests.post(
    "http://localhost:8000/v1/research",
    headers={"Authorization": "Bearer test-key"},
    json={
        "query": "Latest AI developments in 2025",
        "depth": "deep",
        "output_path": "/app/research_output/ai_report.md"
    }
)
print(response.json())
```

### JavaScript/TypeScript
```typescript
const response = await fetch('http://localhost:8000/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer test-key'
  },
  body: JSON.stringify({
    model: 'claude-sonnet-4',
    messages: [{ role: 'user', content: 'Hello!' }]
  })
});
```

## Management Commands

```bash
# Start service
./start.sh

# Stop service
./stop.sh

# View logs
./logs.sh

# Restart
./restart.sh

# Check status
docker ps
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | `8000` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `MAX_TIMEOUT` | Max request timeout (ms) | `2400000` (40 min) |
| `TAVILY_API_KEY` | Tavily API key for research | Required |
| `PRIVACY_ENABLED` | Enable PII anonymization | `true` |

### Secrets

Place your Claude OAuth token in `secrets/claude_token.txt`:
```bash
echo "sk-ant-oat01-..." > secrets/claude_token.txt
```

## Cloud Deployment (Hetzner)

See [DEPLOYMENT.md](DEPLOYMENT.md) for Hetzner Cloud setup instructions.

## Architecture

```
┌─────────────────┐      HTTP       ┌─────────────────┐
│  Your App       │ ──────────────▶ │   EDEAIBridge   │
│  (Report Studio)│                 │   (Port 8000)   │
└─────────────────┘                 └────────┬────────┘
                                             │ OAuth
                                             ▼
                                    ┌─────────────────┐
                                    │   Claude API    │
                                    └─────────────────┘
```

## License

MIT

## Author

Rafael Rengelmann
