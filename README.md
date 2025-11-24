# JARVIS v3.0 - Intelligent Voice Assistant

A powerful, privacy-focused voice assistant with real-time streaming, tool integration, and multi-language support.

## 🎯 Key Features

### Core Capabilities
- **🎤 Real-Time Voice Streaming**: Hear responses as they're generated (< 2s latency)
- **🤖 Intelligent Tool System**: Browser automation, file operations, system control
- **🌍 Multi-Language Support**: English (Piper TTS), Telugu/Hindi (gTTS fallback)
- **🔍 Web Search**: Powered by Perplexity AI for current information
- **🧠 200-Turn Memory**: Persistent conversation context across sessions
- **⚡ GPU Acceleration**: CUDA-powered Whisper STT + Mistral LLM
- **🔒 Privacy-First**: All processing local (except optional web search)

### Agent Capabilities (v3.0)
- **Browser Automation** (Selenium): YouTube autoplay, Google search, URL navigation
- **System Control**: Launch applications (VS Code, Terminal, Arduino IDE, etc.)
- **File Operations**: Read, write, search files
- **System Monitoring**: CPU, RAM, disk usage
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

#### Interactive Voice Mode (with microphone)
```bash
./jarvis.py
```

#### Text-to-Voice Mode (no microphone needed)
```bash
./jarvis.py --text
```

#### Server Only
```bash
python3 server.py
```

## 📝 Usage Examples

### Voice Commands

**System Control:**
```
"open terminal"
"open system settings"
"open VS Code"
"open Arduino IDE"
```

**Browser Automation:**
```
"open google and search for Python tutorials"
"play Kaantha song in YouTube"  # Auto-plays first video!
"open youtube.com"
```

**File Operations:**
```
"read file config.txt"
"create file test.py with print hello world"
"list files"
```

**System Information:**
```
"check system status"
"what did I ask before"  # Recalls conversation history
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

### No Microphone
Use text-to-voice mode: `./jarvis.py --text`

## 📚 API Endpoints

- `POST /api/voice` - Audio in → Audio out
- `POST /api/voice/text` - Text in → Streaming audio out
- `POST /api/text` - Text in → Text out

## 🗺️ Roadmap

- [x] Phase 1: Real-time streaming (v2.0)
- [x] Phase 2: Tool integration & browser automation (v3.0)
- [ ] Phase 3: Telugu/Hindi streaming TTS
- [ ] Phase 4: Endpoint refactoring
- [ ] Phase 5: Complete documentation

## 📄 License

MIT License

## 🙏 Acknowledgments

- Whisper (OpenAI), Mistral AI, Piper TTS, Perplexity AI, Selenium
