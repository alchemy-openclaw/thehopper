#!/usr/bin/env bash
# TheHopper — one-command startup script.
# Installs dependencies (if needed) and runs both the FastAPI backend and
# the Vite dev server, OR the built app served by FastAPI if the frontend
# is already built.
#
# Usage:
#   ./start.sh            # dev mode (Vite + FastAPI, with hot reload)
#   ./start.sh --build    # production mode (build frontend, serve via FastAPI)
#   ./start.sh --prod     # alias for --build
#
# Environment variables:
#   STRIPE_SECRET_KEY         - Stripe secret key (test: sk_t...)
#   STRIPE_PUBLISHABLE_KEY    - Stripe publishable key (test: pk_t...)
#   PORT                      - backend port (default 8000)
#   STRIPE_WEBHOOK_SECRET     - for webhook signature verification

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/venv"
PORT="${PORT:-8000}"

# Color output
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
PINK='\033[0;35m'
NC='\033[0m' # No Color

echo -e "${PINK}🎤 TheHopper — starting up...${NC}"
echo

# ----------------------------------------------------------------------------
# 1. Python backend: create venv + install deps
# ----------------------------------------------------------------------------
echo -e "${CYAN}→ Setting up Python backend…${NC}"

if [ ! -d "$VENV_DIR" ]; then
  echo "  Creating virtualenv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

# Activate and install
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
echo "  Installing Python dependencies…"
pip install --quiet --upgrade pip 2>/dev/null || true
pip install --quiet -r "$BACKEND_DIR/requirements.txt"
echo -e "  ${GREEN}✓ Python deps installed${NC}"

# ----------------------------------------------------------------------------
# 2. Frontend: install npm deps
# ----------------------------------------------------------------------------
echo -e "${CYAN}→ Setting up frontend…${NC}"
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "  Installing npm dependencies (this may take a minute)…"
  (cd "$FRONTEND_DIR" && npm install --silent)
else
  # Ensure deps are up to date
  (cd "$FRONTEND_DIR" && npm install --silent 2>/dev/null || true)
fi
echo -e "  ${GREEN}✓ npm deps installed${NC}"

# ----------------------------------------------------------------------------
# 3. Build frontend if --build flag, otherwise run dev servers in parallel
# ----------------------------------------------------------------------------
BUILD_MODE=false
if [ "${1:-}" = "--build" ] || [ "${1:-}" = "--prod" ] || [ "${1:-}" = "build" ] || [ "${1:-}" = "prod" ]; then
  BUILD_MODE=true
fi

if [ "$BUILD_MODE" = "true" ]; then
  echo -e "${CYAN}→ Building frontend for production…${NC}"
  (cd "$FRONTEND_DIR" && npm run build)
  echo -e "  ${GREEN}✓ Frontend built to dist/${NC}"

  echo -e "${PINK}🎤 Starting TheHopper (production mode) on port $PORT…${NC}"
  echo -e "   Open: ${CYAN}http://localhost:$PORT${NC}"
  echo
  cd "$BACKEND_DIR"
  exec python -m uvicorn main:app --host 0.0.0.0 --port "$PORT"
fi

# Dev mode: run Vite (5173) + FastAPI (8000) in parallel
echo -e "${PINK}🎤 Starting TheHopper (dev mode)…${NC}"
echo -e "   Frontend (Vite): ${CYAN}http://localhost:5173${NC}"
echo -e "   Backend (API):   ${CYAN}http://localhost:$PORT${NC}"
echo -e "   ${YELLOW}Open http://localhost:5173 in your browser${NC}"
echo

# Trap cleanup
cleanup() {
  echo -e "\n${YELLOW}Shutting down…${NC}"
  kill "$VITE_PID" "$API_PID" 2>/dev/null || true
  wait "$VITE_PID" "$API_PID" 2>/dev/null || true
  echo -e "${GREEN}Bye! 🎤${NC}"
}
trap cleanup EXIT INT TERM

# Start FastAPI backend
cd "$BACKEND_DIR"
python -m uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload &
API_PID=$!

# Start Vite dev server
cd "$FRONTEND_DIR"
npm run dev &
VITE_PID=$!

# Wait for either to exit (bash 3 compatible for macOS)
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$VITE_PID" 2>/dev/null; do
  sleep 1
done
echo -e "${YELLOW}One service exited, shutting down the other…${NC}"
