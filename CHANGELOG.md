# JARVIS Changelog

All notable changes and updates to the JARVIS voice assistant project.

## [2.0.0] - 2025-11-24 - Production Release

### 🎉 Major Features
- **Real-Time Voice Streaming:** Implemented sentence-by-sentence audio streaming with < 2s latency
- **Multi-Language Support:** Added English (Piper TTS), Telugu, and Hindi (gTTS) support
- **Web Search Integration:** Integrated Perplexity AI for current information retrieval
- **Natural Speech Output:** Implemented paragraph-style formatting for continuous, natural-sounding responses

### ✨ Enhancements
- **Accurate Latency Measurement:** Fixed timing measurement to show real audio arrival time (0.8-2.5s depending on query complexity)
- **Chunk Optimization:** Improved streaming performance from 4-byte to 4KB chunks (100x improvement)
- **Text Cleanup:** Added markdown and special character removal for clean TTS output
- **Query Complexity Detection:** Adaptive token limits based on query type (simple/detailed/search)
- **Session Management:** Implemented conversation context retention with automatic expiration

### 🔧 Technical Improvements
- **Stereo Audio Output:** Convert Piper mono to stereo for better compatibility (22050 Hz, 16-bit PCM)
- **WAV Streaming Format:** Single WAV header with continuous PCM stream for real-time playback
- **Async/Sync Architecture:** Dual methods for both streaming and batch processing
- **Error Handling:** Graceful degradation with proper fallbacks

### 🐛 Bug Fixes
- Fixed English TTS generating 0 bytes (missing piper binary and espeak-ng)
- Fixed audio noise issue (added proper WAV headers with correct sizes)
- Fixed event loop conflict (async Piper called from sync context)
- Fixed curl command failures (missing Content-Type header)
- Fixed latency measurement showing constant 0.22s (now accurately measures 0.8-2.5s)
- Fixed markdown/special characters being spoken in audio output

### 📚 Documentation
- Created comprehensive README with quick start guide
- Added DEVELOPMENT.md with technical deep dive
- Consolidated all documentation into 3 main files
- Removed duplicate and outdated documentation

### 🧪 Testing
- Added `test_streaming_realtime.py` for real-time audio testing
- Created performance benchmark scripts
- Added curl example scripts
- Implemented audio quality verification tests

## [1.5.0] - 2025-11-23 - Streaming Implementation

### Added
- Sentence-by-sentence LLM streaming
- Real-time TTS conversion per sentence
- Streaming API endpoint `/api/voice/stream`
- Python streaming client with PyAudio

### Changed
- Modified TTS service to support raw PCM output
- Updated server to stream audio as sentences are generated
- Improved sentence boundary detection

### Fixed
- File-based approach replaced with streaming architecture
- Reduced latency from >10s to <2s

## [1.0.0] - 2025-11-22 - Initial Release

### Added
- FastAPI server with RESTful API
- Whisper STT integration (GPU-accelerated)
- Piper TTS integration (CPU)
- Mistral LLM integration via llama.cpp
- Basic session management
- Health check endpoint
- API documentation (Swagger UI)

### Core Modules
- `core/config.py` - Configuration management
- `core/logger.py` - Logging setup
- `core/session.py` - Session handling
- `services/stt.py` - Speech-to-text service
- `services/tts_hybrid.py` - Multi-language TTS
- `services/llm.py` - LLM streaming interface
- `tools/perplexity.py` - Web search integration

## [0.5.0] - 2025-11-21 - Foundation

### Initial Setup
- Project structure created
- Docker compose stack for Home Assistant, Whisper, Piper, LLM server
- NVIDIA Container Toolkit integration
- GPU acceleration setup
- Virtual environment configuration

### Hardware Configuration
- NVIDIA RTX 5060 Ti (16GB VRAM)
- AMD Ryzen 7 7700
- Ubuntu 24.04 LTS
- CUDA 12.x support

## Performance Benchmarks

### Latency Measurements (v2.0.0)

| Query Type | Latency | Components |
|------------|---------|------------|
| Simple Math | 0.8-1.0s | LLM generation + TTS |
| Knowledge Query | 1.0-1.5s | LLM processing + TTS |
| Web Search | 2.0-2.5s | Search API + LLM + TTS |
| Complex Explanation | 1.5-2.0s | Extended LLM generation + TTS |

### Audio Quality
- **Format:** RIFF WAV, 22050 Hz, Stereo, 16-bit PCM
- **Clarity:** Crystal clear, no artifacts
- **Naturalness:** Continuous paragraph flow
- **Streaming:** 4KB chunks, minimal buffering

### Resource Usage
- **VRAM:** ~14GB (Mistral 24B model)
- **RAM:** ~4GB (server + services)
- **CPU:** Low utilization (mainly I/O)
- **GPU Utilization:** 60-80% during inference

## Known Issues

### Current Limitations
1. **Search Query Latency:** Web searches take 2-2.5s (acceptable but could be optimized)
2. **ALSA Warnings:** PyAudio generates warnings on some systems (harmless)
3. **Single User:** No multi-user authentication (privacy-focused single-user design)
4. **Language Detection:** Simple Unicode-based detection (works but could be more sophisticated)

### Planned Improvements
- WebSocket support for bidirectional communication
- Voice Activity Detection (VAD) for better interruption handling
- Multiple voice profiles per language
- Improved language detection
- Speaker identification for multi-user scenarios
- Emotion-aware TTS

## Breaking Changes

### v2.0.0
- API endpoint `/api/voice` renamed to `/api/voice/text`
- Session management now required for multi-turn conversations
- Configuration file structure changed (see `core/config.py`)

### v1.5.0
- Streaming API requires different client implementation
- WAV format changed to continuous stream (placeholder size)

## Migration Guide

### From v1.x to v2.0
1. Update configuration file format:
   ```python
   # Old
   TTS_MODEL = "en_GB-alan-medium"
   
   # New
   PIPER_MODEL = "en_GB-alan-medium"
   ```

2. Update API calls:
   ```bash
   # Old
   curl -X POST /api/voice -d '{"text": "Hello"}'
   
   # New
   curl -X POST /api/voice/text -H "Content-Type: application/json" -d '{"text": "Hello"}'
   ```

3. For streaming, use new endpoint:
   ```bash
   curl -X POST /api/voice/stream -H "Content-Type: application/json" --no-buffer
   ```

## Contributors

- **Nani** - Lead Developer & Architect

## Acknowledgments

### Technology Stack
- **Piper TTS** by Rhasspy - High-quality neural text-to-speech
- **Whisper** by OpenAI - Robust speech recognition
- **Mistral AI** - Powerful open-source language model
- **FastAPI** - Modern Python web framework
- **llama.cpp** - Efficient LLM inference

### Community
Thanks to the open-source community for the amazing tools that made this project possible.

## License

MIT License - See LICENSE file for details

---

**Last Updated:** November 24, 2025  
**Current Version:** 2.0.0  
**Status:** Production Ready ✅
