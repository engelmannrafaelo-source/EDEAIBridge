#!/bin/bash
#
# Quick Start Script für Research Integration Tests
#
# Usage:
#   ./run_research_tests.sh              # Alle Tests (außer slow)
#   ./run_research_tests.sh --all        # Alle Tests (inkl. slow)
#   ./run_research_tests.sh --fast       # Nur health check
#   ./run_research_tests.sh --help       # Hilfe
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$SCRIPT_DIR/../.."

echo -e "${BLUE}===========================================\n${NC}"
echo -e "${BLUE}🔬 Research Integration Tests${NC}\n"
echo -e "${BLUE}===========================================\n${NC}"

# Parse arguments
RUN_MODE="standard"
case "${1:-}" in
    --all)
        RUN_MODE="all"
        ;;
    --fast)
        RUN_MODE="fast"
        ;;
    --help|-h)
        echo "Usage:"
        echo "  $0              Run standard tests (exclude slow)"
        echo "  $0 --all        Run all tests (include slow)"
        echo "  $0 --fast       Run only health check"
        echo "  $0 --help       Show this help"
        exit 0
        ;;
esac

# Check prerequisites
echo -e "${YELLOW}📋 Checking Prerequisites...${NC}\n"

# 1. Check Wrapper is running
echo -n "  🔍 Checking wrapper health... "
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Running${NC}"
else
    echo -e "${RED}✗ Not running${NC}"
    echo -e "\n${YELLOW}Start wrapper with:${NC}"
    echo -e "  cd $PROJECT_ROOT"
    echo -e "  ./start-wrappers.sh"
    exit 1
fi

# 2. Check Claude CLI
echo -n "  🔍 Checking Claude CLI... "
if command -v claude &> /dev/null; then
    echo -e "${GREEN}✓ Installed${NC}"
else
    echo -e "${RED}✗ Not found${NC}"
    echo -e "\n${YELLOW}Install with:${NC}"
    echo -e "  npm install -g @anthropic-ai/claude-code"
    exit 1
fi

# 3. Check Authentication
echo -n "  🔍 Checking authentication... "
if claude --print "test" &> /dev/null; then
    echo -e "${GREEN}✓ Authenticated${NC}"
else
    echo -e "${RED}✗ Not authenticated${NC}"
    echo -e "\n${YELLOW}Login with:${NC}"
    echo -e "  claude login"
    exit 1
fi

# 4. Check venv
echo -n "  🔍 Checking virtual environment... "
if [ -d "$PROJECT_ROOT/venv" ]; then
    echo -e "${GREEN}✓ Found${NC}"
else
    echo -e "${RED}✗ Not found${NC}"
    echo -e "\n${YELLOW}Create with:${NC}"
    echo -e "  cd $PROJECT_ROOT"
    echo -e "  python3 -m venv venv"
    echo -e "  source venv/bin/activate"
    echo -e "  pip install pytest pytest-asyncio httpx"
    exit 1
fi

echo ""

# Activate venv
source "$PROJECT_ROOT/venv/bin/activate"

# Set environment variables
export RUN_RESEARCH_TESTS=1
export WRAPPER_URL="http://localhost:8000"
export WRAPPER_API_KEY="${WRAPPER_API_KEY:-}"

# Run tests based on mode
cd "$PROJECT_ROOT"

case "$RUN_MODE" in
    all)
        echo -e "${GREEN}🚀 Running ALL tests (including slow)...${NC}\n"
        pytest tests/integration/test_research_integration.py -v -s
        ;;
    fast)
        echo -e "${GREEN}🚀 Running FAST tests only...${NC}\n"
        pytest tests/integration/test_research_integration.py::TestBasicResearch::test_wrapper_is_running -v -s
        ;;
    standard)
        echo -e "${GREEN}🚀 Running STANDARD tests (excluding slow)...${NC}\n"
        pytest tests/integration/test_research_integration.py -v -s -m "not slow"
        ;;
esac

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}===========================================\n${NC}"
    echo -e "${GREEN}✅ All tests passed!${NC}\n"
    echo -e "${GREEN}===========================================\n${NC}"
    echo -e "\n${BLUE}📂 Check outputs:${NC}"
    echo -e "  Test outputs:     tests/integration/research_outputs/"
    echo -e "  Research reports: $PROJECT_ROOT/claudedocs/"
else
    echo -e "${RED}===========================================\n${NC}"
    echo -e "${RED}❌ Some tests failed${NC}\n"
    echo -e "${RED}===========================================\n${NC}"
fi

exit $EXIT_CODE
