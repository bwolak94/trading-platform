#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "============================================"
echo "  AI Trading Navigator — Full Setup"
echo "============================================"
echo ""

# --- 1. Environment file ---
echo "[1/7] Setting up environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "  Created .env from .env.example"
    echo "  ⚠  Edit .env and fill in your API keys before running the system in production."
else
    echo "  .env already exists, skipping"
fi

# --- 2. Docker services ---
echo ""
echo "[2/7] Starting Docker services (PostgreSQL + TimescaleDB, Redis)..."
docker compose up -d postgres redis
echo "  Waiting for services to be healthy..."
sleep 5

# Wait for postgres to be ready
for i in {1..30}; do
    if docker compose exec -T postgres pg_isready -U user -d trading_ai > /dev/null 2>&1; then
        echo "  PostgreSQL is ready"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  ERROR: PostgreSQL did not become ready in time"
        exit 1
    fi
    sleep 2
done

# Enable TimescaleDB extension
docker compose exec -T postgres psql -U user -d trading_ai -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;" 2>/dev/null || true
echo "  TimescaleDB extension enabled"

# --- 3. Backend dependencies ---
echo ""
echo "[3/7] Installing backend dependencies..."
cd "$ROOT_DIR/backend"
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "  Backend dependencies installed"

# --- 4. Database migrations ---
echo ""
echo "[4/7] Running database migrations..."
alembic upgrade head
echo "  Migrations applied"

# --- 5. Frontend dependencies ---
echo ""
echo "[5/7] Installing frontend dependencies..."
cd "$ROOT_DIR/frontend"
npm install --silent
echo "  Frontend dependencies installed"

# --- 6. Start all services ---
echo ""
echo "[6/7] Starting application services..."
cd "$ROOT_DIR"

# Backend
cd "$ROOT_DIR/backend"
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "  Backend started (PID: $BACKEND_PID) → http://localhost:8000"

# Celery worker
celery -A app.tasks worker --loglevel=warning --concurrency=2 &
CELERY_WORKER_PID=$!
echo "  Celery worker started (PID: $CELERY_WORKER_PID)"

# Celery beat
celery -A app.tasks beat --loglevel=warning &
CELERY_BEAT_PID=$!
echo "  Celery beat started (PID: $CELERY_BEAT_PID)"

# Frontend
cd "$ROOT_DIR/frontend"
npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!
echo "  Frontend started (PID: $FRONTEND_PID) → http://localhost:5173"

# --- 7. Summary ---
echo ""
echo "============================================"
echo "  All services running!"
echo "============================================"
echo ""
echo "  Dashboard:  http://localhost:5173"
echo "  API:        http://localhost:8000/api/v1/health"
echo "  API Docs:   http://localhost:8000/docs"
echo ""
echo "  To backfill historical data for backtesting:"
echo "    cd backend && source .venv/bin/activate"
echo "    python -m scripts.backfill_historical_data"
echo ""
echo "  To validate backtest results:"
echo "    python -m scripts.validate_backtest"
echo ""
echo "  Press Ctrl+C to stop all services"
echo ""

# Trap Ctrl+C to clean up all background processes
cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID $CELERY_WORKER_PID $CELERY_BEAT_PID $FRONTEND_PID 2>/dev/null || true
    docker compose stop postgres redis 2>/dev/null || true
    echo "All services stopped."
    exit 0
}
trap cleanup SIGINT SIGTERM

# Wait for any background process to exit
wait
