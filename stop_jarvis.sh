#!/bin/bash

# Stop (or optionally restart) the JARVIS voice assistant server

set -euo pipefail

ROOT_DIR="/home/nani/Documents/Project/Project_CODE/jarvis"
PID_FILE="$ROOT_DIR/logs/jarvis.pid"
RESTART_AFTER_STOP=false

if [[ ${1:-} == "restart" || ${1:-} == "--restart" ]]; then
    RESTART_AFTER_STOP=true
fi

if [[ ! -f "$PID_FILE" ]]; then
    echo "No PID file found at $PID_FILE. JARVIS does not appear to be running."
else
    JARVIS_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [[ -z "$JARVIS_PID" ]]; then
        echo "PID file is empty. Removing stale file."
        rm -f "$PID_FILE"
    elif ps -p "$JARVIS_PID" > /dev/null 2>&1; then
        echo "Stopping JARVIS (PID: $JARVIS_PID)..."
        kill "$JARVIS_PID"
        for attempt in {1..10}; do
            if ! ps -p "$JARVIS_PID" > /dev/null 2>&1; then
                break
            fi
            sleep 1
        done
        if ps -p "$JARVIS_PID" > /dev/null 2>&1; then
            echo "Process did not exit gracefully, forcing stop..."
            kill -9 "$JARVIS_PID" || true
        fi
        rm -f "$PID_FILE"
        echo "JARVIS stopped."
    else
        echo "No running process with PID $JARVIS_PID. Removing stale PID file."
        rm -f "$PID_FILE"
    fi
fi

if $RESTART_AFTER_STOP; then
    echo "Restarting JARVIS..."
    "$ROOT_DIR/start_jarvis.sh"
fi
