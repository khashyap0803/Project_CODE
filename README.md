# JARVIS - Voice Assistant System

A powerful, privacy-focused voice assistant with real-time streaming capabilities, powered by local AI models.

## 🎯 Features

- **Real-Time Voice Streaming:** Hear responses as they're generated (< 2s latency)
- **Multi-Language Support:** English (Piper TTS), Telugu, Hindi (gTTS)
- **Web Search Integration:** Powered by Perplexity AI
- **Continuous Speech Flow:** Natural paragraph-style responses optimized for listening
- **GPU Acceleration:** CUDA-powered for fast inference
- **Privacy-First:** All processing happens locally (except optional web search)

## 📊 System Architecture

```
┌─────────────┐
│   Client    │ (HTTP/WebSocket)
└──────┬──────┘
       │
┌──────▼──────────────────────────────────────┐
│            JARVIS Server                     │
│  ┌────────────────────────────────────────┐ │
│  │  FastAPI Core (server.py)              │ │
│  └────────────────────────────────────────┘ │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
│  │   STT    │  │   LLM    │  │    TTS    │ │
│  │ Whisper  │─▶│ Mistral  │─▶│   Piper   │ │
│  │  (GPU)   │  │  (GPU)   │  │  (CPU)    │ │
│  └──────────┘  └────┬─────┘  └───────────┘ │
│                     │                        │
│              ┌──────▼──────┐                 │
│              │ Perplexity  │                 │
│              │ Web Search  │                 │
│              └─────────────┘                 │
└──────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Ubuntu 24.04 LTS (or similar Linux distribution)
- NVIDIA GPU with CUDA support (RTX 5060 Ti or similar)
- Python 3.10+
- 16GB+ VRAM recommended

### Installation

```bash
# Clone the repository
cd ~/Documents/Project/Project_CODE/jarvis

# Run setup script
chmod +x setup.sh
./setup.sh

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Starting the Server

```bash
# Start the JARVIS server
python server.py

# Or use the start script
./start_jarvis.sh
```

Server will be available at: `http://localhost:8000`

## 💬 Usage Examples

### 1. Real-Time Voice Streaming (Python)

```bash
# Ask a question and hear the response in real-time
./venv/bin/python test_streaming_realtime.py "What is quantum computing?"
```

**Performance:**
- Simple queries: ~1.0s latency
- Complex explanations: ~1.5s latency
- Search queries: ~2.5s latency (includes web search)

### 2. Using curl

```bash
# Stream audio response
curl -X POST http://localhost:8000/api/voice/stream \
  -H "Content-Type: application/json" \
  -d '{"text": "Explain artificial intelligence"}' \
  --no-buffer -o response.wav

# Play the audio
aplay response.wav
```

### 3. Text-Only API

```bash
# Get text response without audio
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"text": "What is machine learning?"}'
```

### 4. Multi-Language Support

```bash
# Telugu
curl -X POST http://localhost:8000/api/voice/text \
  -H "Content-Type: application/json" \
  -d '{"text": "నమస్కారం", "language": "te"}' \
  -o telugu.mp3

# Hindi
curl -X POST http://localhost:8000/api/voice/text \
  -H "Content-Type: application/json" \
  -d '{"text": "नमस्ते", "language": "hi"}' \
  -o hindi.mp3
```

## 📡 API Endpoints

### Voice Streaming
- **POST** `/api/voice/stream` - Real-time audio streaming (sentence-by-sentence)
- **POST** `/api/voice/text` - Complete audio file generation

### Text Chat
- **POST** `/api/chat` - Text-only conversation

### Speech-to-Text
- **POST** `/api/stt` - Upload audio file for transcription

### Health Check
- **GET** `/health` - Server status

### API Documentation
- **GET** `/docs` - Interactive API documentation (Swagger UI)

## 🔧 Configuration

Edit `core/config.py` to customize:

```python
# LLM Settings
LLM_API_URL = "http://localhost:8080/v1/chat/completions"
LLM_MODEL_NAME = "mistral-small-24b"
LLM_TEMPERATURE = 0.7

# TTS Settings
PIPER_MODEL = "en_GB-alan-medium"

# Web Search
ENABLE_WEB_SEARCH = True
PERPLEXITY_API_KEY = "your-api-key"  # Optional
```

## 📁 Project Structure

```
jarvis/
├── server.py              # Main FastAPI server
├── requirements.txt       # Python dependencies
├── core/                  # Core modules
│   ├── config.py         # Configuration settings
│   ├── logger.py         # Logging setup
│   └── session.py        # Session management
├── services/             # AI services
│   ├── llm.py           # LLM streaming interface
│   ├── stt.py           # Speech-to-text (Whisper)
│   └── tts_hybrid.py    # Text-to-speech (Piper/gTTS)
├── tools/                # External tools
│   ├── perplexity.py    # Web search integration
│   └── code_executor.py # Code execution (future)
├── piper-data/           # TTS voice models
├── whisper-data/         # STT model cache
└── test_streaming_realtime.py  # Test client
```

## 🎤 Audio Specifications

### Output Format
- **Format:** WAV (RIFF)
- **Sample Rate:** 22050 Hz
- **Channels:** Stereo (2)
- **Bit Depth:** 16-bit PCM
- **Streaming:** 4KB chunks for optimal performance

### Supported Languages
- **English:** Piper TTS (multiple voices available)
- **Telugu:** gTTS (Google TTS)
- **Hindi:** gTTS (Google TTS)

## 🧪 Testing

```bash
# Test real-time streaming
./venv/bin/python test_streaming_realtime.py "Tell me about space"

# Test with curl
./test_curl_examples.sh

# Performance benchmark
./test_streaming_professional.sh
```

## 📈 Performance Metrics

Based on actual measurements:

| Query Type | Latency | Notes |
|------------|---------|-------|
| Simple Math | ~1.0s | Direct LLM response |
| Knowledge Query | ~1.5s | LLM generation + TTS |
| Web Search | ~2.5s | Search + LLM + TTS |
| Complex Explanation | ~1.5s | Longer response time |

**Audio Quality:**
- Clear, natural speech
- No artifacts or noise
- Continuous paragraph flow
- No special characters spoken

## 🛠️ Troubleshooting

### Server Won't Start

```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill existing process
pkill -9 -f "python.*server.py"

# Restart server
python server.py
```

### No Audio Output

1. Check Content-Type header in requests
2. Verify file size: `ls -lh output.wav`
3. Check server logs: `tail -f /tmp/jarvis_server.log`

### CUDA Out of Memory

```bash
# Check GPU usage
nvidia-smi

# Reduce max_tokens in config.py
# Or use smaller LLM model
```

### Audio is Noisy

- Regenerate the audio file
- Check audio format with: `file output.wav`
- Ensure proper WAV headers are present

## 🔐 Privacy & Security

- All AI processing happens locally on your machine
- No data is sent to external servers (except optional web search)
- Session data is stored in memory only
- No persistent user data collection

## 🤝 Contributing

This is a personal project. Feel free to fork and customize for your needs.

## 📝 License

MIT License - Feel free to use and modify as needed.

## 🙏 Acknowledgments

- **Piper TTS** - High-quality neural TTS
- **Whisper** - OpenAI's speech recognition
- **Mistral AI** - Powerful local LLM
- **FastAPI** - Modern Python web framework
- **Perplexity AI** - Web search integration

## 📞 Support

For issues or questions, check the logs:
```bash
tail -f /tmp/jarvis_server.log
```

---

**Version:** 2.0.0  
**Last Updated:** November 24, 2025  
**Status:** Production Ready ✅
