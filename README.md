# JARVIS v3.0 - Intelligent Voice Assistant

A powerful, privacy-focused voice assistant with real-time streaming, tool integration, and multi-language support.

## 🎯 Key Features

### Core Capabilities
- **🎤 Real-Time Voice Streaming**: Hear responses as they're generated (< 2s latency)
- **🤖 Intelligent Tool System**: Browser automation, file operations, system control
- **🧠 LLM Intent Classification**: Understands commands even with typos/natural variations
- **🎯 Multi-Command Execution**: Execute chained commands with delays ("open X and after 5 sec maximize it")
- **🌍 Multi-Language Streaming TTS**: English (Piper), Telugu/Hindi (Edge TTS with true streaming)
- **🔍 Web Search**: Powered by Perplexity AI for current information
- **🧠 200-Turn Memory**: Persistent conversation context across sessions
- **⚡ GPU Acceleration**: CUDA-powered Whisper STT + Mistral LLM
- **🔒 Privacy-First**: All processing local (except optional web search)

### Agent Capabilities (v3.0)
- **Browser Automation** (Selenium): YouTube autoplay, Google search, URL navigation
- **System Control**: Launch applications (VS Code, Terminal, Arduino IDE, etc.)
- **Time Management**: Timers, alarms, stopwatch, reminders
- **File Operations**: Read, write, search files
- **System Monitoring**: CPU, RAM, disk, GPU, network usage
- **Command Execution**: Run shell commands safely (30s timeout)

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- CUDA-capable GPU (optional, for GPU acceleration)
- 8GB+ RAM
- Linux (tested on Ubuntu/Unity)

### Installation

```bash
# Clone repository
cd /path/to/jarvis

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running JARVIS

#### Complete Startup (Recommended)
```bash
# Start both LLM server and JARVIS server
./start_all.sh

# Stop all services
./stop_all.sh
```

#### Interactive Voice Mode (with microphone)
```bash
./jarvis.py
```

#### Text-to-Voice Mode (no microphone needed)
```bash
./jarvis.py --text
```

#### Server Only (requires LLM server running separately)
```bash
# First start LLM server:
/home/nani/llama.cpp/build/bin/llama-server \
  -m /home/nani/llama.cpp/models/mistral-small-24b-instruct-q4_k_m.gguf \
  -c 8192 --host 0.0.0.0 --port 8080

# Then start JARVIS:
python3 server.py
```

## 📝 Usage Examples

### Voice Commands

**Time & Date:**
```
"what time is it" / "wat time" / "tell me the time"
"what's the date today" / "whats the date"
```

**Timers, Alarms & Stopwatch:**
```
"set a 5 minute timer"
"set alarm for 7:30am"
"start stopwatch" / "stop stopwatch" / "reset stopwatch"
"remind me to take medicine in 1 hour"
```

**System Control:**
```
"open terminal"
"open system settings"
"open VS Code"
"open Arduino IDE"
"lock screen" / "lokc screen" (typos work!)
```

**Volume & Brightness:**
```
"volume up" / "increase volume"
"mute" / "unmute"
"brightness 50%"
```

**Browser Automation:**
```
"open google and search for Python tutorials"
"play Kaantha song in YouTube"  # Auto-plays first video!
"open youtube.com"
"pause" / "play" / "next video" / "previous"
```

**System Information:**
```
"check cpu status"
"how much memory is being used"
"check disk space"
"what's the gpu temperature"
```

**File Operations:**
```
"read file config.txt"
"create file test.py with print hello world"
"list files"
```

**Web Search:**
```
"explain quantum computing"
"latest news about AI"
```

## 🛠️ Configuration

### Environment Variables (.env)
```env
MISTRAL_API_KEY=your_mistral_key_here
PERPLEXITY_API_KEY=your_perplexity_key_here  # Optional
```

## 🔧 Troubleshooting

### Terminal/Settings Not Opening
JARVIS tries multiple fallback commands automatically. If none work:
```bash
sudo apt-get install xterm gnome-control-center
```

### YouTube Autoplay Issues
- First use may be slow (browser startup)
- Browser stays open for subsequent requests

### Audio Latency Increasing Over Time
```bash
# Check if audio keep-alive service is running
systemctl --user status jarvis-audio-keepalive.service

# If not running, enable it
systemctl --user enable --now jarvis-audio-keepalive.service
```

### No Microphone
Use text-to-voice mode: `./jarvis.py --text`

## 📚 API Endpoints

| Endpoint | Input | Output | Use Case |
|----------|-------|--------|----------|
| `POST /api/voice` | Audio file | Streaming WAV | Full voice interaction |
| `POST /api/voice/text` | JSON `{text}` | Streaming WAV | Text-to-voice (recommended) |
| `POST /api/voice/text/json` | JSON `{text}` | JSON with base64 audio | Non-streaming alternative |
| `POST /api/text` | JSON `{text}` | JSON `{response}` | Text-only |

## 🗺️ Roadmap

- [x] Phase 1: Real-time streaming (<2s latency)
- [x] Phase 2: Tool integration & browser automation  
- [x] Phase 2.5: Production startup system & permanent fixes
- [x] Phase 3: LLM intent classification for typo handling
- [x] Phase 3.5: Multi-command execution with delays
- [x] Phase 4: Telugu/Hindi streaming TTS (Edge TTS)
- [ ] Phase 5: Endpoint refactoring
- [ ] Phase 6: Complete documentation

## 📄 Documentation

- `README.md` - Quick start and usage
- `DEVELOPMENT.md` - Technical implementation details
- `TROUBLESHOOTING.md` - Problem diagnosis and fixes
- `CHANGELOG.md` - Version history

## 🙏 Acknowledgments

- Whisper (OpenAI), Mistral AI, Piper TTS, Perplexity AI, Selenium

