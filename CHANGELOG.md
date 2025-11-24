# JARVIS Changelog

All notable changes to the JARVIS Voice Assistant project are documented in this file.

## [3.0.0] - 2025-11-24

### 🎉 Major Features - Tool Integration & Browser Automation

#### Agent Capabilities
- **Browser Automation (Selenium)**:
  - YouTube autoplay: Searches and automatically plays first non-sponsored video
  - Google search: Direct search from voice commands
  - URL navigation: Open any website with voice command
  - Persistent browser session for multiple requests

- **System Control**:
  - Application launcher: VS Code, Terminal, Arduino IDE, PyCharm, Sublime, etc.
  - Fallback commands: Tries multiple alternatives (xterm, konsole, gnome-terminal)
  - Background execution: Apps launch with nohup to prevent blocking
  - Desktop environment detection: Adapts to GNOME, KDE, Unity, XFCE, MATE

- **File Operations**:
  - Read files with voice command
  - Create/write files with content
  - List directory contents
  - Search files by pattern (glob-based, 50 result limit)

- **System Monitoring**:
  - CPU usage (per-core and average)
  - RAM usage (used/total)
  - Disk space (used/free/total)
  - Real-time psutil integration

- **Command Execution**:
  - Safe shell command execution (30s timeout)
  - Background process support
  - Output capture (stdout/stderr)

#### Tool System
- **7 Core Tools** implemented:
  1. `read_file` - Read file contents
  2. `write_file` - Create/modify files
  3. `list_directory` - Browse directories
  4. `run_command` - Execute shell commands
  5. `get_system_status` - System information
  6. `search_files` - Find files by pattern
  7. `open_url` - Open URLs in browser

- **Tool Manager**:
  - Centralized tool registration
  - Async execution support
  - Error handling and logging
  - Tool result formatting for LLM

- **Intent Detection**:
  - Pattern-based command recognition
  - Regex patterns for YouTube, Google, applications
  - Fallback to LLM-based tool calling
  - No latency - instant tool triggering

#### Memory System
- **200-Turn Conversation History**:
  - Persistent session management
  - Context maintained across commands
  - "What did I ask before?" recall capability
  - Session timeout: 1800s (30 minutes)
  - Deque-based efficient storage

#### Interactive Client Improvements
- **Text-to-Voice Mode** (`--text` flag):
  - Test without microphone
  - Full streaming audio output
  - 120s timeout for long queries
  - Session persistence

- **Voice Activity Detection (VAD)**:
  - Optimized threshold: 0.3 (from 0.5)
  - Better speech detection
  - Reduced false negatives

### 🔧 Technical Improvements

#### Streaming Architecture
- **TRUE Real-Time Streaming**:
  - Sentence-by-sentence processing
  - LLM generates → TTS converts → Audio plays immediately
  - <2s first-sentence latency confirmed
  - No buffering delays

#### LLM Integration
- **Mistral Small** via API:
  - Tool-aware prompts
  - Dynamic max_tokens (200-1200) based on query complexity
  - Temperature tuning per use case
  - Streaming response generation

#### TTS System
- **Hybrid TTS**:
  - English: Piper (local, real-time, multiple voices)
  - Telugu/Hindi: gTTS fallback (cloud-based)
  - Voice selection: en_US-lessac-medium (default)
  - Multiple British English voices available

#### Error Handling
- **Robust Fallbacks**:
  - Terminal: x-terminal-emulator → xterm → konsole → gnome-terminal
  - Settings: gnome-control-center → unity-control-center → systemsettings5
  - Browser: Firefox → Chrome → Chromium
  - Selenium: Firefox → Chrome fallback

#### Bug Fixes
- Fixed YouTube regex extracting "and play" in search query
- Fixed Selenium driver closing prematurely (now persistent)
- Fixed GNOME terminal snap library conflicts (nohup workaround)
- Fixed session not persisting (uses "text-to-voice-session" ID)
- Fixed WAV header struct error in streaming
- Fixed curl streaming support
- Fixed PyAudio installation path

### 📚 Documentation
- Updated README with v3.0 features
- Comprehensive usage examples
- API endpoint documentation
- Troubleshooting guide
- Architecture diagrams

### 🗑️ Cleanup
- Removed duplicate .md files
- Consolidated documentation to README.md and CHANGELOG.md
- Archived old implementation docs
- Cleaned up test scripts

---

## [2.0.0] - 2025-11-XX

### Features
- **Real-Time Streaming**:
  - TRUE sentence-by-sentence streaming
  - <2s latency for first response
  - WAV streaming support
  - Server-Sent Events (SSE)

- **Multi-Language Support**:
  - English: Piper TTS (local)
  - Telugu: gTTS (cloud fallback)
  - Hindi: gTTS (cloud fallback)
  - Auto language detection

- **Web Search Integration**:
  - Perplexity AI API
  - Automatic search intent detection
  - Citation support
  - Configurable timeout (120s)

- **Session Management**:
  - UUID-based sessions
  - Conversation history
  - Context preservation
  - Automatic cleanup

### Technical
- FastAPI server with WebSocket support
- Whisper STT (GPU-accelerated)
- Mistral LLM (GPU-accelerated)
- Piper TTS (CPU, local processing)
- CUDA optimization

---

## [1.0.0] - Initial Release

### Features
- Basic voice assistant functionality
- Whisper speech-to-text
- OpenAI GPT integration
- Basic TTS
- Simple FastAPI server

---

## Version History Summary

- **v3.0.0** (Current): Tool integration, browser automation, 200-turn memory
- **v2.0.0**: Real-time streaming, multi-language, web search
- **v1.0.0**: Initial voice assistant release

---

## Upcoming Features

### Phase 3: Multi-Language Streaming TTS
- [ ] Telugu Piper TTS model research
- [ ] Hindi Piper TTS model research
- [ ] Real-time streaming for Telugu/Hindi
- [ ] Voice selection per language

### Phase 4: Endpoint Refactoring
- [ ] Move `/api/text` to `/api/debug/text`
- [ ] Streamline endpoint structure
- [ ] Voice-first design emphasis

### Phase 5: Polish & Release
- [ ] Comprehensive testing suite
- [ ] Performance benchmarks
- [ ] Production deployment guide
- [ ] GitHub release with binaries
