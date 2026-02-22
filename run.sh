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
    echo "Create a .env file with at least:"
    echo "  ANTHROPIC_API_KEY=sk-ant-..."
    exit 1
fi

# Source .env to check values
set -a
source .env
set +a

if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${RED}ERROR: ANTHROPIC_API_KEY is not set in .env${NC}"
    exit 1
fi
echo -e "${GREEN}[OK]${NC} .env loaded"

# --- 2. Create virtual env if it doesn't exist, then activate ---
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    echo -e "${GREEN}[OK]${NC} Virtual environment created"
fi
source .venv/bin/activate
echo -e "${GREEN}[OK]${NC} Virtual environment activated"

# --- 3. Install Python dependencies ---
pip install -q -r requirements.txt 2>/dev/null
echo -e "${GREEN}[OK]${NC} Python dependencies installed"

# --- 4. Playwright browsers ---
python -m playwright install chromium --with-deps 2>/dev/null || python -m playwright install chromium 2>/dev/null || true
echo -e "${GREEN}[OK]${NC} Playwright browsers ready"

# --- 5. Build frontend ---
echo ""
echo "Building frontend..."
cd frontend
npm ci --silent 2>/dev/null || npm install --silent 2>/dev/null
npm run build
cd "$SCRIPT_DIR"
echo -e "${GREEN}[OK]${NC} Frontend built"

# --- 6. Start server ---
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  DemoX running on http://localhost:8000${NC}"
echo -e "${GREEN}========================================${NC}"
echo "Press Ctrl+C to stop."
echo ""

# Open browser after a short delay
(sleep 2 && open "http://localhost:8000" 2>/dev/null || xdg-open "http://localhost:8000" 2>/dev/null || true) &

# Run uvicorn from repo root so "backend.server.api" imports work
exec uvicorn backend.server.api:app --host 0.0.0.0 --port 8000
