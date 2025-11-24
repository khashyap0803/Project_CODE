"""
JARVIS Main Server - FastAPI with WebSocket streaming
Professional voice assistant with real-time audio processing
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from typing import Optional, Dict
import asyncio
import json
import time
import io

from core.config import settings
from core.logger import setup_logger
from core.session import session_manager
from services import whisper_stt, llm
from services.tts_hybrid import tts_service as piper_tts
from tools import perplexity
from tools.code_executor import execute_code, run_command, get_system_status, manage_file

logger = setup_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="JARVIS Voice Assistant",
    description="Advanced AI voice assistant with streaming support",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Request Models ===

class TextRequest(BaseModel):
    """Text-based query request"""
    text: str
    session_id: Optional[str] = None
    stream: bool = True

class SearchRequest(BaseModel):
    """Web search request"""
    query: str
    max_tokens: int = 1000

class CodeRequest(BaseModel):
    """Code execution request"""
    code: str

class CommandRequest(BaseModel):
    """System command request"""
    command: str

# === Helper Functions ===

def needs_web_search(text: str) -> bool:
    """Determine if query requires web search"""
    keywords = [
        'search', 'latest', 'current', 'recent', 'news', 'today',
        'price', 'cost', 'weather', 'stock', 'what is happening'
    ]
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in keywords)

def detect_query_complexity(text: str) -> tuple[int, int]:
    """
    Detect query complexity and return (max_tokens, timeout)
    Returns aggressive limits for simple queries (<1s target)
    """
    text_lower = text.lower()
    
    # Very simple queries - math, basic facts
    simple_patterns = ['what is', 'who is', 'calculate', 'plus', 'minus', 'times', 'divided', 'what\'s']
    if any(pattern in text_lower for pattern in simple_patterns) and len(text) < 30:
        return (settings.LLM_SIMPLE_QUERY_MAX_TOKENS, settings.LLM_FAST_TIMEOUT)
    
    # Detailed queries
    detailed_patterns = ['explain', 'describe', 'how does', 'tell me about', 'in detail']
    if any(pattern in text_lower for pattern in detailed_patterns):
        return (settings.LLM_DETAILED_QUERY_MAX_TOKENS, settings.LLM_NORMAL_TIMEOUT)
    
    # Normal queries
    return (settings.LLM_NORMAL_QUERY_MAX_TOKENS, settings.LLM_NORMAL_TIMEOUT)

def detect_language(text: str) -> str:
    """
    Detect language from text
    Simple detection based on Unicode ranges
    """
    # Telugu: U+0C00 to U+0C7F
    # Hindi/Devanagari: U+0900 to U+097F
    for char in text:
        code = ord(char)
        if 0x0C00 <= code <= 0x0C7F:
            return "te"
        elif 0x0900 <= code <= 0x097F:
            return "hi"
    return "en"  # Default to English

async def generate_response(
    user_query: str,
    session_id: Optional[str] = None,
    language: Optional[str] = None
):
    """
    Generate intelligent response with tool routing and language support
    
    Yields text chunks suitable for streaming TTS
    """
    # Detect language if not provided
    if language is None:
        language = detect_language(user_query)
    
    # Detect query complexity for optimization
    max_tokens, timeout = detect_query_complexity(user_query)
    
    # Get or create session
    session = session_manager.get_or_create_session(session_id)
    
    # Store language in session context
    session.context['language'] = language
    
    # Add user query to history
    session.add_turn("user", user_query)
    
    # Check if web search is needed
    if needs_web_search(user_query) and settings.ENABLE_WEB_SEARCH:
        logger.info(f"Web search requested: {user_query[:50]}")
        try:
            search_result = await perplexity.search(user_query)
            
            # Create context-aware prompt
            messages = [
                {
                    "role": "system",
                    "content": """You are JARVIS, a helpful AI assistant. Use the provided search results to answer accurately.

IMPORTANT: Format your response as continuous flowing paragraphs. Never use bullet points, lists, or numbered steps. Write everything as connected sentences for smooth, natural speech."""
                },
                *session.get_history(last_n=5),  # Include context
                {
                    "role": "user",
                    "content": f"""Search results for "{user_query}":

{search_result['answer']}

Sources: {', '.join(search_result.get('citations', [])[:3])}

Based on this information, provide a helpful answer."""
                }
            ]
        except Exception as e:
            logger.error(f"Search error: {e}")
            messages = session.get_history()
            messages.append({"role": "system", "content": "Search failed. Answer based on your knowledge."})
    else:
        # Build conversation context
        system_prompt = {
            "role": "system",
            "content": """You are JARVIS, an advanced AI assistant. Be helpful, accurate, and conversational.

IMPORTANT: Format ALL responses as continuous flowing paragraphs. Never use:
- Bullet points or lists (•, -, *, numbers)
- Multiple separate points
- Step-by-step numbered instructions

Instead, write everything as connected sentences in paragraph form for smooth, natural speech flow. Explain concepts by weaving information together naturally, as if speaking to someone in conversation.

Be concise for simple queries, detailed for complex ones. Always maintain context from previous conversation."""
        }
        messages = [system_prompt] + session.get_history()
    
    # Stream LLM response with adaptive parameters
    full_response = ""
    async for sentence in llm.generate_stream(
        messages, 
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=max_tokens,
        timeout=timeout
    ):
        full_response += sentence + " "
        yield sentence
    
    # Add assistant response to history
    session.add_turn("assistant", full_response.strip())

# === API Endpoints ===

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "services": {
            "whisper": "loaded",
            "piper": "loaded",
            "llm": "ready",
            "perplexity": "configured" if settings.ENABLE_WEB_SEARCH else "disabled"
        }
    }

@app.post("/api/text")
async def process_text(request: TextRequest):
    """Process text query (non-streaming, for compatibility)"""
    try:
        logger.info(f"Text query: {request.text[:100]}")
        
        response_text = ""
        async for sentence in generate_response(request.text, request.session_id):
            response_text += sentence + " "
        
        return {
            "response": response_text.strip(),
            "session_id": request.session_id
        }
    except Exception as e:
        logger.error(f"Text processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stream/text")
async def stream_text(request: TextRequest):
    """Stream text response with Server-Sent Events (TRUE STREAMING)"""
    async def event_generator():
        try:
            logger.info(f"Streaming text query: {request.text[:100]}")
            sentence_count = 0
            start_time = time.time()
            
            async for sentence in generate_response(request.text, request.session_id):
                sentence_count += 1
                elapsed = time.time() - start_time
                
                # Send sentence immediately as SSE event
                yield {
                    "event": "sentence",
                    "data": json.dumps({
                        "text": sentence,
                        "index": sentence_count,
                        "elapsed": round(elapsed, 3),
                        "session_id": request.session_id
                    })
                }
            
            # Send completion event
            yield {
                "event": "complete",
                "data": json.dumps({
                    "total_sentences": sentence_count,
                    "total_time": round(time.time() - start_time, 3),
                    "session_id": request.session_id
                })
            }
            
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }
    
    return EventSourceResponse(event_generator())

@app.post("/api/stream/audio")
async def stream_audio(request: TextRequest):
    """Stream audio response (text-to-speech in real-time)"""
    async def audio_generator():
        try:
            logger.info(f"Streaming audio for: {request.text[:100]}")
            
            # Detect language
            language = detect_language(request.text)
            
            async for sentence in generate_response(request.text, request.session_id, language):
                # Synthesize audio for each sentence immediately
                audio_chunks = []
                for audio_chunk in piper_tts.synthesize_stream(sentence, language):
                    audio_chunks.append(audio_chunk)
                
                # Combine chunks for this sentence
                audio_data = b''.join(audio_chunks)
                
                # Send as JSON with base64 encoding
                import base64
                yield {
                    "event": "audio",
                    "data": json.dumps({
                        "text": sentence,
                        "audio": base64.b64encode(audio_data).decode('utf-8'),
                        "language": language
                    })
                }
            
            # Send completion
            yield {
                "event": "complete",
                "data": json.dumps({"status": "done"})
            }
            
        except Exception as e:
            logger.error(f"Audio streaming error: {e}")
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)})
            }
    
    return EventSourceResponse(audio_generator())

@app.post("/api/execute/python")
async def execute_python_code(request: CodeRequest):
    """Execute Python code"""
    if not settings.ENABLE_CODE_EXECUTION:
        raise HTTPException(status_code=403, detail="Code execution is disabled")
    
    logger.info(f"Executing Python code ({len(request.code)} chars)")
    result = execute_code(request.code, "python")
    return result

@app.post("/api/execute/command")
async def execute_system_command(request: CommandRequest):
    """Execute system command"""
    if not settings.ENABLE_CODE_EXECUTION:
        raise HTTPException(status_code=403, detail="System commands are disabled")
    
    logger.info(f"Executing command: {request.command[:50]}")
    result = run_command(request.command)
    return result

@app.get("/api/system/status")
async def system_status():
    """Get system status"""
    return get_system_status()

@app.post("/api/file/operation")
async def file_operation(operation: str, path: str, content: Optional[str] = None):
    """Perform file operation"""
    if not settings.ENABLE_CODE_EXECUTION:
        raise HTTPException(status_code=403, detail="File operations are disabled")
    
    result = manage_file(operation, path, content)
    return result

@app.post("/api/search")
async def web_search(request: SearchRequest):
    """Direct web search endpoint"""
    try:
        logger.info(f"Search query: {request.query}")
        result = await perplexity.search(request.query, request.max_tokens)
        return result
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/voice/ask")
async def voice_ask(audio: UploadFile = File(...)):
    """Voice input -> Text processing -> Audio output (COMPLETE VOICE INTERACTION)"""
    try:
        # Read audio file
        audio_bytes = await audio.read()
        logger.info(f"Received audio: {len(audio_bytes)} bytes")
        
        # Transcribe audio
        transcription = whisper_stt.transcribe_audio(audio_bytes)
        user_text = transcription.get("text", "").strip()
        detected_lang = transcription.get("language", "en")
        
        if not user_text:
            raise HTTPException(status_code=400, detail="No speech detected")
        
        logger.info(f"Transcribed ({detected_lang}): {user_text}")
        
        # Generate response
        response_text = ""
        async for sentence in generate_response(user_text, None, detected_lang):
            response_text += sentence + " "
        
        response_text = response_text.strip()
        logger.info(f"Response: {response_text[:100]}")
        
        # Synthesize audio response
        audio_chunks = []
        for chunk in piper_tts.synthesize_stream(response_text, detected_lang):
            audio_chunks.append(chunk)
        
        audio_data = b''.join(audio_chunks)
        
        # Return audio with metadata in JSON wrapper
        import base64
        return {
            "audio": base64.b64encode(audio_data).decode('utf-8'),
            "transcription": user_text,
            "response_text": response_text,
            "language": detected_lang,
            "audio_size": len(audio_data)
        }
    except Exception as e:
        logger.error(f"Voice ask error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/voice/text")
async def voice_text(request: TextRequest):
    """Text input -> Audio output (TTS response) - Complete audio in JSON"""
    try:
        logger.info(f"Text to voice: {request.text[:100]}")
        
        # Detect language
        detected_lang = detect_language(request.text)
        
        # Generate response
        response_text = ""
        async for sentence in generate_response(request.text, request.session_id, detected_lang):
            response_text += sentence + " "
        
        response_text = response_text.strip()
        
        # Synthesize audio using async method
        audio_chunks = []
        async for chunk in piper_tts.synthesize_stream_async(response_text, detected_lang):
            audio_chunks.append(chunk)
        
        audio_data = b''.join(audio_chunks)
        
        # Return audio with metadata in JSON wrapper
        import base64
        return {
            "audio": base64.b64encode(audio_data).decode('utf-8'),
            "response_text": response_text,
            "language": detected_lang,
            "audio_size": len(audio_data)
        }
    except Exception as e:
        logger.error(f"Voice text error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/voice/stream")
async def voice_stream(request: TextRequest):
    """
    TRUE REAL-TIME voice streaming - sentences spoken as they're generated!
    Streams raw PCM audio (no WAV headers between sentences)
    Client receives audio in real-time and can play immediately
    """
    async def audio_stream_generator():
        try:
            logger.info(f"Real-time voice streaming: {request.text[:100]}")
            
            # Detect language
            detected_lang = detect_language(request.text)
            
            # Create WAV header once at the start (with placeholder size)
            # Client will handle streaming playback
            import struct
            sample_rate = 22050
            num_channels = 2  # Stereo
            bits_per_sample = 16
            byte_rate = sample_rate * num_channels * bits_per_sample // 8
            block_align = num_channels * bits_per_sample // 8
            
            # WAV header with max size (for streaming)
            header = struct.pack('<4sI4s', b'RIFF', 0xFFFFFFFF - 8, b'WAVE')
            header += struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, num_channels, sample_rate, byte_rate, block_align, bits_per_sample)
            header += struct.pack('<4sI', b'data', 0xFFFFFFFF)
            
            yield header
            logger.info("WAV header sent, starting sentence-by-sentence synthesis...")
            
            sentence_count = 0
            # Stream: LLM generates sentence -> TTS converts -> Audio streams immediately
            async for sentence in generate_response(request.text, request.session_id, detected_lang):
                sentence_count += 1
                logger.info(f"Sentence {sentence_count}: {sentence[:60]}...")
                
                # Convert THIS sentence to audio immediately (don't wait for more sentences!)
                # Use raw_pcm=True to get only PCM data (no WAV header for each sentence)
                async for audio_chunk in piper_tts.synthesize_stream_async(sentence, detected_lang, raw_pcm=True):
                    yield audio_chunk
                
                logger.debug(f"Sentence {sentence_count} audio streamed")
            
            logger.info(f"Streaming complete: {sentence_count} sentences")
                    
        except Exception as e:
            logger.error(f"Voice stream error: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    return StreamingResponse(
        audio_stream_generator(),
        media_type="audio/wav",
        headers={
            "X-Stream-Type": "real-time-sentence-streaming",
            "Cache-Control": "no-cache"
        }
    )

@app.websocket("/ws/voice")
async def websocket_voice(websocket: WebSocket):
    """
    WebSocket endpoint for real-time voice interaction
    
    Protocol:
    1. Client sends audio chunks (binary)
    2. Server transcribes and generates response
    3. Server sends TTS audio chunks back (binary)
    4. Client plays audio in real-time
    """
    await websocket.accept()
    session_id = None
    logger.info("WebSocket voice connection established")
    
    try:
        while True:
            # Receive audio data from client
            data = await websocket.receive()
            
            if "bytes" in data:
                # Audio data received
                audio_bytes = data["bytes"]
                logger.debug(f"Received audio: {len(audio_bytes)} bytes")
                
                # Transcribe audio (auto-detect language)
                transcription = whisper_stt.transcribe_audio(audio_bytes)
                user_text = transcription.get("text", "").strip()
                detected_lang = transcription.get("language", "en")
                
                if not user_text:
                    logger.warning("Empty transcription")
                    continue
                
                logger.info(f"User said ({detected_lang}): {user_text}")
                
                # Send transcription to client
                await websocket.send_json({
                    "type": "transcription",
                    "text": user_text,
                    "language": detected_lang
                })
                
                # Generate and stream response with language context
                async for sentence in generate_response(user_text, session_id, detected_lang):
                    # Send text chunk
                    await websocket.send_json({
                        "type": "text_chunk",
                        "text": sentence
                    })
                    
                    # Generate and send TTS audio in same language
                    async for audio_chunk in piper_tts.synthesize_stream(sentence, detected_lang):
                        await websocket.send_bytes(audio_chunk)
                
                # Signal response complete
                await websocket.send_json({
                    "type": "response_complete"
                })
            
            elif "text" in data:
                # JSON message received
                try:
                    message = json.loads(data["text"])
                    msg_type = message.get("type")
                    
                    if msg_type == "init":
                        session_id = message.get("session_id")
                        logger.info(f"Session initialized: {session_id}")
                        await websocket.send_json({
                            "type": "ready",
                            "session_id": session_id
                        })
                    
                    elif msg_type == "ping":
                        await websocket.send_json({"type": "pong"})
                
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON message")
    
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=1011, reason=str(e))
        except:
            pass

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("=" * 50)
    logger.info("JARVIS Voice Assistant Starting")
    logger.info("=" * 50)
    logger.info(f"Host: {settings.HOST}:{settings.PORT}")
    logger.info(f"CUDA: {settings.ENABLE_CUDA}")
    logger.info(f"Web Search: {settings.ENABLE_WEB_SEARCH}")
    logger.info(f"Memory: {settings.ENABLE_MEMORY}")
    logger.info("=" * 50)

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("JARVIS shutting down...")
    session_manager.cleanup_expired()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level="info"
    )
