#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# --- Cleanup from previous runs ---
echo -e "${CYAN}=== DemoX Startup ===${NC}"

# Kill any orphaned processes from previous runs
for pattern in "uvicorn backend.main:app" "presenter_agent.agent" "next-router-worker\|next dev"; do
    pkill -f "$pattern" 2>/dev/null || true
done
sleep 0.5

# --- 1. Check .env ---
if [ ! -f .env ]; then
    echo -e "${RED}ERROR: .env file not found.${NC}"
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
echo -e "${GREEN}[OK]${NC} .env loaded"

# --- 2. Virtual environment ---
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate
echo -e "${GREEN}[OK]${NC} venv activated"

# --- 3. Install deps (skip if node_modules and pip packages exist) ---
if [ "$1" = "--full" ]; then
    pip install -q -r backend/requirements.txt -r presenter_agent/requirements.txt -r researcher_agent/requirements.txt 2>/dev/null
    python -m playwright install chromium 2>/dev/null || true
    cd frontend && npm install --silent 2>/dev/null && cd "$SCRIPT_DIR"
    echo -e "${GREEN}[OK]${NC} Full dependency install done"
else
    echo -e "${YELLOW}[SKIP]${NC} Dependency install (use ${CYAN}./run.sh --full${NC} to reinstall)"
fi

# --- 4. Check Redis ---
if ! command -v redis-cli &>/dev/null || ! redis-cli ping &>/dev/null; then
    echo -e "${YELLOW}[WARN]${NC} Redis not running. Starting with Docker..."
    docker run -d --name demox-redis -p 6379:6379 redis:7-alpine 2>/dev/null || true
    sleep 1
fi
echo -e "${GREEN}[OK]${NC} Redis ready"

# --- 5. Track child PIDs for clean shutdown ---
PIDS=()

cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down all services...${NC}"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    # Also kill by pattern in case PIDs were missed
    for pattern in "uvicorn backend.main:app" "presenter_agent.agent"; do
        pkill -f "$pattern" 2>/dev/null || true
    done
    wait 2>/dev/null
    echo -e "${GREEN}All services stopped.${NC}"
    exit 0
}

trap cleanup INT TERM

# --- 6. Start all services ---
echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Starting DemoX services...${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""

# Backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
PIDS+=($!)
echo -e "${GREEN}[OK]${NC} Backend          → http://localhost:8000"

sleep 1

# Presenter agent
.venv/bin/python -m presenter_agent.agent dev &
PIDS+=($!)
echo -e "${GREEN}[OK]${NC} Presenter agent  → LiveKit worker"

# Frontend
cd frontend && npm run dev &
PIDS+=($!)
cd "$SCRIPT_DIR"
echo -e "${GREEN}[OK]${NC} Frontend         → http://localhost:3000"

echo ""
echo -e "${CYAN}Press Ctrl+C to stop all services and restart.${NC}"
echo ""

# Open browser (only on first run, not restarts)
sleep 3
(open "http://localhost:3000" 2>/dev/null || xdg-open "http://localhost:3000" 2>/dev/null || true)

# Wait for any child to exit
wait
