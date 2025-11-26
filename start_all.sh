#!/usr/bin/env bash
#
# JARVIS Complete Startup Script
# Starts both LLM server (llama.cpp) and JARVIS server
#
# Usage: ./start_all.sh [--force]
#   --force: Kill existing processes and restart
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Configuration
LLAMA_SERVER="/home/nani/llama.cpp/build/bin/llama-server"
MODEL_PATH="/home/nani/llama.cpp/models/mistral-small-24b-instruct-q4_k_m.gguf"
LLM_PORT=8080
JARVIS_PORT=8000
LOGS_DIR="$SCRIPT_DIR/logs"
LLM_LOG="$LOGS_DIR/llm_server.log"
JARVIS_LOG="$LOGS_DIR/jarvis.log"
LLM_PID_FILE="$LOGS_DIR/llm.pid"
JARVIS_PID_FILE="$LOGS_DIR/jarvis.pid"

# ANSI Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging functions
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $1"; }

# Check if a port is in use
port_in_use() {
    local port=$1
    ss -tuln 2>/dev/null | grep -q ":$port " && return 0 || return 1
}

# Wait for a port to become available
wait_for_port() {
    local port=$1
    local max_wait=${2:-60}
    local wait_count=0
    
    while ! port_in_use $port; do
        wait_count=$((wait_count + 1))
        if [ $wait_count -ge $max_wait ]; then
            return 1
        fi
        sleep 1
    done
    return 0
}

# Check if LLM server is responding
check_llm_health() {
    curl -s -m 2 "http://localhost:$LLM_PORT/health" >/dev/null 2>&1
}

# Check if JARVIS server is responding  
check_jarvis_health() {
    curl -s -m 2 "http://localhost:$JARVIS_PORT/health" >/dev/null 2>&1
}

# Stop existing processes
stop_processes() {
    log_step "Stopping existing processes..."
    
    # Stop JARVIS first
    if [ -f "$JARVIS_PID_FILE" ]; then
        local pid=$(cat "$JARVIS_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            log_info "Stopping JARVIS server (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
            sleep 2
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$JARVIS_PID_FILE"
    fi
    
    # Stop LLM server
    if [ -f "$LLM_PID_FILE" ]; then
        local pid=$(cat "$LLM_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            log_info "Stopping LLM server (PID: $pid)..."
            kill "$pid" 2>/dev/null || true
            sleep 2
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$LLM_PID_FILE"
    fi
    
    # Kill any orphaned processes on the ports
    if port_in_use $LLM_PORT; then
        log_warn "Port $LLM_PORT still in use, force killing..."
        fuser -k $LLM_PORT/tcp 2>/dev/null || true
        sleep 1
    fi
    
    if port_in_use $JARVIS_PORT; then
        log_warn "Port $JARVIS_PORT still in use, force killing..."
        fuser -k $JARVIS_PORT/tcp 2>/dev/null || true
        sleep 1
    fi
}

# Pre-warm PipeWire audio to prevent suspension
prewarm_audio() {
    log_step "Pre-warming PipeWire audio device..."
    
    # Create PipeWire config to disable auto-suspend if not exists
    local pipewire_config_dir="$HOME/.config/pipewire/pipewire-pulse.conf.d"
    local config_file="$pipewire_config_dir/10-no-suspend.conf"
    
    if [ ! -f "$config_file" ]; then
        mkdir -p "$pipewire_config_dir"
        cat > "$config_file" << 'EOF'
# Prevent audio device auto-suspend for low-latency voice assistant
pulse.rules = [
    {
        matches = [ { node.name = "~alsa_output.*" } ]
        actions = {
            update-props = {
                session.suspend-timeout-seconds = 0
            }
        }
    }
    {
        matches = [ { node.name = "~alsa_input.*" } ]
        actions = {
            update-props = {
                session.suspend-timeout-seconds = 0
            }
        }
    }
]
EOF
        log_info "Created PipeWire no-suspend config: $config_file"
        
        # Restart PipeWire to apply config
        systemctl --user restart pipewire pipewire-pulse 2>/dev/null || true
        sleep 1
    fi
    
    # Play silent audio to wake up the device
    if command -v paplay &>/dev/null; then
        # Generate and play 100ms of silence
        python3 -c "
import sys
import wave
import io
# Generate 100ms of silence at 44100Hz stereo
duration = 0.1
rate = 44100
silence = bytes(int(rate * duration * 4))  # 4 bytes per frame (16-bit stereo)
sys.stdout.buffer.write(silence)
" | paplay --raw --rate=44100 --channels=2 --format=s16le 2>/dev/null || true
        log_info "Audio device pre-warmed"
    fi
}

# Main startup sequence
main() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}          ${CYAN}JARVIS Complete Startup Sequence${NC}                    ${BLUE}║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    # Parse arguments
    FORCE_RESTART=false
    if [ "$1" == "--force" ]; then
        FORCE_RESTART=true
        log_warn "Force restart mode enabled"
    fi
    
    # Create logs directory
    mkdir -p "$LOGS_DIR"
    
    # Check prerequisites
    log_step "Checking prerequisites..."
    
    if [ ! -x "$LLAMA_SERVER" ]; then
        log_error "llama-server not found at: $LLAMA_SERVER"
        exit 1
    fi
    log_info "✓ llama-server binary found"
    
    if [ ! -f "$MODEL_PATH" ]; then
        log_error "Model not found at: $MODEL_PATH"
        exit 1
    fi
    local model_size=$(ls -lh "$MODEL_PATH" | awk '{print $5}')
    log_info "✓ Model found ($model_size)"
    
    # Check if services are already running
    LLM_RUNNING=false
    JARVIS_RUNNING=false
    
    if check_llm_health; then
        LLM_RUNNING=true
    fi
    
    if check_jarvis_health; then
        JARVIS_RUNNING=true
    fi
    
    if $LLM_RUNNING && $JARVIS_RUNNING && ! $FORCE_RESTART; then
        log_info "✓ Both services already running!"
        echo ""
        echo -e "${GREEN}JARVIS is ready!${NC}"
        echo "  • LLM Server:    http://localhost:$LLM_PORT"
        echo "  • JARVIS Server: http://localhost:$JARVIS_PORT"
        echo ""
        echo "Run: ${CYAN}./jarvis.py --text${NC} to start chatting"
        exit 0
    fi
    
    # Stop existing processes if needed
    if $FORCE_RESTART || $LLM_RUNNING || $JARVIS_RUNNING; then
        stop_processes
    fi
    
    # Pre-warm audio
    prewarm_audio
    
    # Start LLM Server
    log_step "Starting LLM server (llama.cpp)..."
    log_info "Model: $(basename "$MODEL_PATH")"
    log_info "Port: $LLM_PORT"
    
    # LLM server parameters optimized for Mistral 24B
    nohup "$LLAMA_SERVER" \
        --model "$MODEL_PATH" \
        --host 0.0.0.0 \
        --port $LLM_PORT \
        --ctx-size 8192 \
        --n-gpu-layers 99 \
        --threads 8 \
        --parallel 1 \
        --cont-batching \
        > "$LLM_LOG" 2>&1 &
    
    LLM_PID=$!
    echo $LLM_PID > "$LLM_PID_FILE"
    log_info "LLM server started (PID: $LLM_PID)"
    
    # Wait for LLM server to be ready
    log_info "Waiting for LLM server to load model (this may take 30-60 seconds)..."
    
    WAIT_COUNT=0
    MAX_WAIT=120  # 2 minutes max
    while ! check_llm_health; do
        WAIT_COUNT=$((WAIT_COUNT + 1))
        if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
            log_error "LLM server failed to start within $MAX_WAIT seconds"
            log_error "Check log: $LLM_LOG"
            exit 1
        fi
        
        # Check if process is still running
        if ! kill -0 $LLM_PID 2>/dev/null; then
            log_error "LLM server process died unexpectedly"
            log_error "Check log: $LLM_LOG"
            tail -20 "$LLM_LOG"
            exit 1
        fi
        
        # Show progress every 10 seconds
        if [ $((WAIT_COUNT % 10)) -eq 0 ]; then
            log_info "Still loading... (${WAIT_COUNT}s)"
        fi
        
        sleep 1
    done
    
    log_info "✓ LLM server ready (took ${WAIT_COUNT}s)"
    
    # Start JARVIS Server
    log_step "Starting JARVIS server..."
    
    # Activate virtual environment if exists
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    fi
    
    # Clear Python cache to ensure fresh code
    find "$SCRIPT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    
    nohup python3 server.py > "$JARVIS_LOG" 2>&1 &
    JARVIS_PID=$!
    echo $JARVIS_PID > "$JARVIS_PID_FILE"
    log_info "JARVIS server started (PID: $JARVIS_PID)"
    
    # Wait for JARVIS server
    log_info "Waiting for JARVIS server..."
    WAIT_COUNT=0
    MAX_WAIT=30
    while ! check_jarvis_health; do
        WAIT_COUNT=$((WAIT_COUNT + 1))
        if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
            log_error "JARVIS server failed to start within $MAX_WAIT seconds"
            log_error "Check log: $JARVIS_LOG"
            exit 1
        fi
        
        if ! kill -0 $JARVIS_PID 2>/dev/null; then
            log_error "JARVIS server process died unexpectedly"
            log_error "Check log: $JARVIS_LOG"
            tail -20 "$JARVIS_LOG"
            exit 1
        fi
        
        sleep 1
    done
    
    log_info "✓ JARVIS server ready"
    
    # Final health check
    log_step "Running final health checks..."
    
    HEALTH=$(curl -s "http://localhost:$JARVIS_PORT/health")
    echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Status: {d.get(\"status\", \"unknown\")}'); print(f'  Version: {d.get(\"version\", \"unknown\")}'); [print(f'  {k}: {v}') for k,v in d.get('services',{}).items()]" 2>/dev/null || true
    
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║${NC}              ${CYAN}🎉 JARVIS is ready!${NC}                             ${GREEN}║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "  Services:"
    echo "    • LLM Server:    http://localhost:$LLM_PORT  (PID: $LLM_PID)"
    echo "    • JARVIS Server: http://localhost:$JARVIS_PORT  (PID: $JARVIS_PID)"
    echo ""
    echo "  Logs:"
    echo "    • LLM:    $LLM_LOG"
    echo "    • JARVIS: $JARVIS_LOG"
    echo ""
    echo "  Commands:"
    echo "    • Start chatting: ${CYAN}./jarvis.py --text${NC}"
    echo "    • Stop all:       ${CYAN}./stop_all.sh${NC}"
    echo "    • View logs:      ${CYAN}tail -f $JARVIS_LOG${NC}"
    echo ""
}

main "$@"
