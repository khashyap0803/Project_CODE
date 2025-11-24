#!/bin/bash

# Start JARVIS voice assistant server

echo "Starting JARVIS Voice Assistant..."

cd /home/nani/Documents/Project/Project_CODE/jarvis

# Activate virtual environment
source venv/bin/activate

# Set environment variables
export CUDA_VISIBLE_DEVICES=0
export OMP_NUM_THREADS=8

# Start server
nohup python server.py > logs/jarvis.log 2>&1 &

JARVIS_PID=$!
echo "JARVIS started (PID: $JARVIS_PID)"
echo $JARVIS_PID > logs/jarvis.pid

# Wait for server to be ready
echo "Waiting for JARVIS..."
for i in {1..20}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ JARVIS ready!"
        curl -s http://localhost:8000/health | python -m json.tool
        break
    fi
    sleep 1
done

echo ""
echo "========================================"
echo "JARVIS is running!"
echo "========================================"
echo "HTTP API: http://localhost:8000"
echo "WebSocket: ws://localhost:8000/ws/voice"
echo "Logs: tail -f logs/jarvis.log"
echo ""
echo "Stop with: ./stop_jarvis.sh"
echo "========================================"
