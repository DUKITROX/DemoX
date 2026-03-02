#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== DemoX Startup ===${NC}"

# --- 1. Check .env ---
if [ ! -f .env ]; then
    echo -e "${RED}ERROR: .env file not found.${NC}"
    echo "Create a .env file with required API keys (see plan.md)"
    exit 1
fi

set -a
source .env
set +a

for var in ANTHROPIC_API_KEY LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET DEEPGRAM_API_KEY ELEVENLABS_API_KEY; do
    if [ -z "${!var}" ]; then
        echo -e "${RED}ERROR: $var is not set in .env${NC}"
        exit 1
    fi
done
echo -e "${GREEN}[OK]${NC} .env loaded — all keys present"

# --- 2. Virtual environment ---
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate
echo -e "${GREEN}[OK]${NC} Virtual environment activated"

# --- 3. Install Python dependencies ---
pip install -q -r backend/requirements.txt -r presenter_agent/requirements.txt -r researcher_agent/requirements.txt 2>/dev/null
echo -e "${GREEN}[OK]${NC} Python dependencies installed"

# --- 4. Playwright browsers ---
python -m playwright install chromium 2>/dev/null || true
echo -e "${GREEN}[OK]${NC} Playwright browsers ready"

# --- 5. Check Redis ---
if ! command -v redis-cli &>/dev/null || ! redis-cli ping &>/dev/null; then
    echo -e "${YELLOW}[WARN]${NC} Redis not running. Starting with Docker..."
    docker run -d --name demox-redis -p 6379:6379 redis:7-alpine 2>/dev/null || true
    sleep 1
fi
echo -e "${GREEN}[OK]${NC} Redis ready"

# --- 6. Build frontend ---
echo "Building frontend..."
cd frontend
npm install --silent 2>/dev/null
npm run build 2>/dev/null
cd "$SCRIPT_DIR"
echo -e "${GREEN}[OK]${NC} Frontend built"

# --- 7. Start all services ---
echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Starting DemoX services...${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo "  Backend API:       http://localhost:8000"
echo "  Frontend:          http://localhost:3000"
echo "  Presenter Agent:   LiveKit worker (auto-dispatched)"
echo ""
echo "Press Ctrl+C to stop all services."
echo ""

# Trap to kill all background processes
trap 'echo "Shutting down..."; kill $(jobs -p) 2>/dev/null; exit 0' INT TERM

# Start backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
echo -e "${GREEN}[OK]${NC} Backend started on :8000"

# Kill any orphaned presenter agent processes from previous runs
pkill -f "presenter_agent.agent" 2>/dev/null || true
sleep 1

# Start presenter agent worker
.venv/bin/python -m presenter_agent.agent dev &
echo -e "${GREEN}[OK]${NC} Presenter agent worker started"

# Start frontend
cd frontend && npm run dev &
cd "$SCRIPT_DIR"
echo -e "${GREEN}[OK]${NC} Frontend dev server started on :3000"

# Open browser
sleep 3
(open "http://localhost:3000" 2>/dev/null || xdg-open "http://localhost:3000" 2>/dev/null || true)

# Wait for all background processes
wait
