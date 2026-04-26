#!/bin/bash

# Church Scheduling System - Startup Script
# Run this from the project root directory.

echo "Starting Church Scheduling System..."

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_LOG="$ROOT_DIR/backend.log"
FRONTEND_LOG="$ROOT_DIR/frontend.log"

if [ ! -d "$ROOT_DIR/venv" ]; then
    echo "Error: Virtual environment not found. Run setup first."
    exit 1
fi

echo "Activating virtual environment..."
source "$ROOT_DIR/venv/bin/activate"

if [ -f "$ROOT_DIR/.env" ]; then
    echo "Loading environment from .env..."
    set -a
    source "$ROOT_DIR/.env"
    set +a
fi

if [ -z "$DATABASE_URL" ]; then
    echo "Error: DATABASE_URL is not set. Create or update the root .env file first."
    exit 1
fi

echo "Using database connection from DATABASE_URL"

echo "Cleaning up existing processes..."
for port in 8000 8001; do
    PIDS=$(lsof -ti tcp:$port 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "Stopping processes on port $port: $PIDS"
        kill $PIDS 2>/dev/null || true
    fi
done
sleep 2

echo "Starting FastAPI backend on port 8000..."
bash -lc "cd \"$ROOT_DIR\" && exec \"$ROOT_DIR/venv/bin/uvicorn\" main:app --host 0.0.0.0 --port 8000" > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

BACKEND_READY=0
for _ in {1..10}; do
    if curl -s http://localhost:8000/health > /dev/null; then
        BACKEND_READY=1
        break
    fi
    sleep 2
done

if [ "$BACKEND_READY" -ne 1 ]; then
    echo "Error: Backend failed to start. Recent backend.log output:"
    tail -n 40 "$BACKEND_LOG" 2>/dev/null || true
    kill $BACKEND_PID 2>/dev/null || true
    exit 1
fi

echo "Starting frontend server on port 8001..."
bash -lc "cd \"$FRONTEND_DIR\" && exec python3 -m http.server 8001" > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

FRONTEND_READY=0
for _ in {1..10}; do
    if curl -s http://localhost:8001/phase_1/ui.html > /dev/null; then
        FRONTEND_READY=1
        break
    fi
    sleep 1
done

if [ "$FRONTEND_READY" -ne 1 ]; then
    echo "Error: Frontend failed to start. Recent frontend.log output:"
    tail -n 40 "$FRONTEND_LOG" 2>/dev/null || true
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    exit 1
fi

echo ""
echo "✅ System started successfully!"
echo "📱 Admin UI: http://YOUR_SERVER_IP:8001/phase_1/ui.html"
echo "📝 Member Signup: http://YOUR_SERVER_IP:8001/phase_1/member_signup.html"
echo "📆 Availability Form: http://YOUR_SERVER_IP:8001/phase_2/availability_form.html"
echo "🔗 API Docs: http://YOUR_SERVER_IP:8000/docs"
echo "💚 Health Check: http://YOUR_SERVER_IP:8000/health"
echo "📝 Backend Log: $BACKEND_LOG"
echo "📝 Frontend Log: $FRONTEND_LOG"
echo ""
echo "Press Ctrl+C to stop all servers"

trap "echo 'Stopping servers...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT
wait
