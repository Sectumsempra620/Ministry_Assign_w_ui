#!/bin/bash

echo "Stopping Church Scheduling System..."

for port in 8000 8001; do
    PIDS=$(lsof -ti tcp:$port 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "Stopping processes on port $port: $PIDS"
        kill $PIDS 2>/dev/null || true
    else
        echo "No process found on port $port"
    fi
done

echo "Done."
