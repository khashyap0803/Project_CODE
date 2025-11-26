#!/usr/bin/env bash
#
# Audio Keep-Alive Script for JARVIS
# Prevents PipeWire audio device from entering power-saving mode
# by periodically playing inaudible silence
#

# Configuration
INTERVAL=30  # Play silence every 30 seconds
DURATION=0.01  # 10ms of silence (inaudible)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Audio keep-alive started (interval: ${INTERVAL}s)"

# Ensure PipeWire config exists
CONFIG_DIR="$HOME/.config/pipewire/pipewire-pulse.conf.d"
CONFIG_FILE="$CONFIG_DIR/10-no-suspend.conf"

if [ ! -f "$CONFIG_FILE" ]; then
    mkdir -p "$CONFIG_DIR"
    cat > "$CONFIG_FILE" << 'EOF'
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
    log "Created PipeWire no-suspend config"
    
    # Restart PipeWire to apply
    systemctl --user restart pipewire pipewire-pulse 2>/dev/null || true
    sleep 2
fi

# Main loop - play silence periodically
while true; do
    if command -v paplay &>/dev/null; then
        # Generate tiny silence and play it (inaudible but keeps device active)
        python3 -c "
import sys
# 10ms of silence at 44100Hz stereo (16-bit)
samples = int(44100 * 0.01)
silence = bytes(samples * 4)  # 4 bytes per frame
sys.stdout.buffer.write(silence)
" 2>/dev/null | paplay --raw --rate=44100 --channels=2 --format=s16le 2>/dev/null
    fi
    
    sleep $INTERVAL
done
