#!/usr/bin/env bash
#
# JARVIS Complete Stop Script
# Stops both LLM server and JARVIS server
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/logs"
LLM_PID_FILE="$LOGS_DIR/llm.pid"
JARVIS_PID_FILE="$LOGS_DIR/jarvis.pid"

# ANSI Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

stop_process() {
    local pid_file=$1
    local name=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            log_info "Stopping $name (PID: $pid)..."
            kill "$pid" 2>/dev/null
            
            # Wait for graceful shutdown
            for i in {1..10}; do
                if ! kill -0 "$pid" 2>/dev/null; then
                    break
                fi
                sleep 0.5
            done
            
            # Force kill if still running
            if kill -0 "$pid" 2>/dev/null; then
                log_warn "Force killing $name..."
                kill -9 "$pid" 2>/dev/null || true
            fi
            
            log_info "✓ $name stopped"
        else
            log_warn "$name not running (stale PID file)"
        fi
        rm -f "$pid_file"
    else
        log_warn "No PID file for $name"
    fi
}

echo ""
echo "Stopping JARVIS services..."
echo ""

# Stop JARVIS first, then LLM
stop_process "$JARVIS_PID_FILE" "JARVIS server"
stop_process "$LLM_PID_FILE" "LLM server"

# Double-check ports
for port in 8000 8080; do
    if ss -tuln 2>/dev/null | grep -q ":$port "; then
        log_warn "Port $port still in use, force killing..."
        fuser -k $port/tcp 2>/dev/null || true
    fi
done

echo ""
log_info "All JARVIS services stopped"
echo ""
