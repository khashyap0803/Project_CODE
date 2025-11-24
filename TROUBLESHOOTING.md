# JARVIS Troubleshooting Guide

## Audio Latency Issues (>2 seconds delay)

If you experience audio latency returning in the future, follow these diagnostic steps:

### Step 1: Enable Debug Logging
```bash
# Edit core/config.py
LOG_LEVEL = "DEBUG"

# Restart server
./stop_jarvis.sh restart
```

### Step 2: Check Timing Logs
```bash
# Monitor logs in real-time
tail -f logs/jarvis.log | grep -E "\[Timing\]|First audio"

# Run a test query in another terminal
python jarvis.py --text
# Type: hello
```

Look for these timing markers:
- `[Timing] Session setup` - Should be <0.01s
- `[Timing] Tool detection` - Should be <0.01s  
- `[Timing] Pre-LLM setup` - Should be <0.01s
- `First audio chunk sent` - Should be <0.5s

### Step 3: Identify the Bottleneck

**If server timing is slow (>1s):**
- Check LLM API response time
- Verify internet connection
- Check if context window is too large (trim history)

**If client timing is slow (>1s from recv to playback):**
- Check audio device status: `pactl list sinks short`
- Verify PipeWire config exists: `cat ~/.config/pipewire/pipewire-pulse.conf.d/10-no-suspend.conf`
- Check if audio device is suspended: `pactl list sinks | grep -i suspend`

**If network timing is slow:**
- Check server health: `curl http://localhost:8000/health`
- Verify server is running: `ps aux | grep "python.*server.py"`
- Check for firewall issues

### Step 4: Fix Common Issues

#### Audio Device Auto-Suspend Re-enabled
```bash
# Verify PipeWire config exists
ls ~/.config/pipewire/pipewire-pulse.conf.d/10-no-suspend.conf

# If missing, recreate it:
mkdir -p ~/.config/pipewire/pipewire-pulse.conf.d
printf '# Disable audio device auto-suspend\ncontext.exec = [\n    { path = "pactl" args = "load-module module-suspend-on-idle timeout=0" }\n]\n' > ~/.config/pipewire/pipewire-pulse.conf.d/10-no-suspend.conf

# Restart PipeWire
systemctl --user restart pipewire pipewire-pulse
```

#### Context Window Overflow
```bash
# Check logs for context errors
grep -i "context" logs/jarvis.log | tail -20

# Reset conversation in text mode
python jarvis.py --text
# Type: reset
```

#### Server Not Streaming
```bash
# Check if concurrent streaming is working
grep "asyncio.Queue" services/llm.py

# Verify sentence extraction
grep "forced_sentence" services/llm.py
```

### Step 5: Test Specific Components

**Test TTS latency:**
```bash
curl -X POST "http://localhost:8000/api/voice/text" \
  -H "Content-Type: application/json" \
  -d '{"text":"hello"}' --output test.wav
```

**Test client playback:**
```bash
python jarvis.py --text
# Type simple queries and check [recv=] [write=] [total=] timing
```

**Test audio device:**
```bash
# Play test sound
speaker-test -t wav -c 2 -l 1
```

## Application Launch Blocking Issues

If applications block JARVIS (audio response delayed until app closes):

### Symptoms
- Command like "open arduino ide" launches app correctly
- But JARVIS doesn't speak until you close the application
- Other apps like TeamViewer work fine (don't block)

### Root Cause
The application launch command is **not properly backgrounded** or subprocess is waiting for exit.

### Quick Fix
Check `tools/code_executor.py` line ~145:
```python
# Should detect background launch
is_background_launch = command.strip().endswith('&') and 'nohup' in command

if is_background_launch:
    # Use Popen with start_new_session=True
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        cwd=os.getcwd()
    )
    return {"success": True, "pid": process.pid}
```

### Verify Launch Commands
Check `server.py` `build_launch_command()` function:
```python
# Should return command like:
# nohup env -i DISPLAY=:0 ... arduino-ide &
final_tokens = ["nohup", *(env_tokens or []), *parts]
quoted = " ".join(shlex.quote(token) for token in final_tokens)
return f"{quoted} &"
```

### Test Specific Apps
```bash
# Add debug logging to see launch command
tail -f logs/jarvis.log | grep "Executing system command"

# In another terminal, test problematic app
python jarvis.py --text
# Type: open arduino ide
# Check log output for the actual command
```

## General Health Checks

### Server Status
```bash
# Check if server is running
./stop_jarvis.sh
# Should show PID if running

# Check health endpoint
curl http://localhost:8000/health
# Should return JSON with "status": "healthy"

# Check logs for errors
tail -50 logs/jarvis.log | grep -i error
```

### Audio System Status
```bash
# Check PipeWire/PulseAudio
systemctl --user status pipewire pipewire-pulse

# List audio devices
pactl list sinks short

# Check if module loaded
pactl list modules short | grep suspend-on-idle
# Should show: timeout=0 (means disabled)
```

### Python Environment
```bash
# Verify virtual environment
which python
# Should point to: /home/nani/Documents/Project/Project_CODE/jarvis/venv/bin/python

# Check dependencies
pip list | grep -E "fastapi|piper|openai|pyaudio"
```

## Performance Optimization Tips

1. **Keep conversation history short** - Type "reset" regularly in text mode
2. **Use SSD for logs** - Reduce disk I/O latency
3. **Close unnecessary apps** - Free up RAM and CPU
4. **Update GPU drivers** - For Whisper STT acceleration
5. **Check network speed** - LLM API calls need low latency

## Emergency Recovery

If JARVIS becomes unresponsive:

```bash
# Force stop
./stop_jarvis.sh
pkill -9 -f "python.*server.py"
pkill -9 -f "python.*jarvis.py"

# Clear logs (if huge)
truncate -s 0 logs/jarvis.log

# Restart fresh
./start_jarvis.sh

# Test health
curl http://localhost:8000/health
```

## Getting Help

When reporting issues, provide:
1. Last 50 lines of logs: `tail -50 logs/jarvis.log`
2. Timing output from test query
3. System info: `uname -a`, `python --version`
4. Audio system: `pactl info | grep "Server Name"`
5. Steps to reproduce the issue
