#!/bin/bash
set -e

# Start Celery worker in background
celery -A worker.tasks worker --loglevel=info --workdir /app > /tmp/worker.log 2>&1 &
WORKER_PID=$!
echo "[entrypoint] Celery worker started (PID $WORKER_PID)"

# Wait for worker to initialize
sleep 2
echo "[entrypoint] === Starting API ==="

# Start Uvicorn API (runs forever, this is our main process)
uvicorn app.main:app --host 0.0.0.0 --port 8000 2>&1 | while IFS= read -r line; do
    echo "$line"
done &
API_PID=$!

# Stream worker logs to stdout
tail -f /tmp/worker.log &
TAIL_PID=$!

# Wait for API to exit
wait $API_PID
