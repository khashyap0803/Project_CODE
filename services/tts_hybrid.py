"""
Hybrid TTS Service: Piper (English) + Edge TTS (Hindi/Telugu) with TRUE STREAMING
Provides high-quality TTS for all three languages with real-time streaming
"""
import os
import io
import asyncio
import struct
from pathlib import Path
from typing import Generator, Optional, AsyncGenerator
from services.tts import piper_tts  # Use global instance
from core.config import settings
from core.logger import setup_logger

logger = setup_logger(__name__)

# Edge TTS for Indian languages (streaming support)
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
    logger.info("Edge TTS available for Hindi/Telugu streaming")
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logger.warning("Edge TTS not available, falling back to gTTS")

# Fallback to gTTS if Edge TTS not available
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False

# Edge TTS voice mapping for Indian languages
EDGE_TTS_VOICES = {
    'hi': 'hi-IN-MadhurNeural',   # Hindi male voice (clear and natural)
    'te': 'te-IN-MohanNeural',    # Telugu male voice
    'hi-female': 'hi-IN-SwaraNeural',  # Hindi female alternative
    'te-female': 'te-IN-ShrutiNeural', # Telugu female alternative
}

class HybridTTSService:
    def __init__(self):
        self.indian_languages = ['hi', 'te']
        self.use_edge_tts = EDGE_TTS_AVAILABLE
        
        if self.use_edge_tts:
            logger.info("Hybrid TTS initialized (Piper for English, Edge TTS for Hindi/Telugu - TRUE STREAMING)")
        elif GTTS_AVAILABLE:
            logger.info("Hybrid TTS initialized (Piper for English, gTTS for Hindi/Telugu)")
        else:
            logger.warning("No Indian language TTS available, will fall back to English")
    
    def _create_wav_header(self, sample_rate: int = 22050, num_channels: int = 2, bits_per_sample: int = 16, data_size: int = 0) -> bytes:
        """Create WAV header for raw PCM audio (stereo for better quality)"""
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        
        header = struct.pack('<4sI4s', b'RIFF', 36 + data_size, b'WAVE')
        header += struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, num_channels, sample_rate, byte_rate, block_align, bits_per_sample)
        header += struct.pack('<4sI', b'data', data_size)
        
        return header
    
    def _mono_to_stereo(self, mono_data: bytes) -> bytes:
        """Convert mono PCM data to stereo by duplicating channels"""
        # mono_data is 16-bit signed integers
        import array
        mono_samples = array.array('h', mono_data)  # 'h' = signed short (16-bit)
        stereo_samples = array.array('h')
        
        # Duplicate each sample to left and right channels
        for sample in mono_samples:
            stereo_samples.append(sample)  # Left channel
            stereo_samples.append(sample)  # Right channel
        
        return stereo_samples.tobytes()
    
    async def _edge_tts_synthesize_stream(self, text: str, language: str) -> AsyncGenerator[bytes, None]:
        """
        Stream audio from Edge TTS (Microsoft) for Hindi/Telugu.
        TRUE STREAMING - yields audio chunks as they are generated.
        """
        voice = EDGE_TTS_VOICES.get(language, EDGE_TTS_VOICES.get('hi'))
        
        try:
            communicate = edge_tts.Communicate(text, voice)
            
            # Edge TTS streams MP3 chunks - we yield them directly
            # The client can play MP3 or we can convert if needed
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
                    
        except Exception as e:
            logger.error(f"Edge TTS streaming error: {e}")
            # Fallback to gTTS if Edge TTS fails
            if GTTS_AVAILABLE:
                logger.info("Falling back to gTTS")
                for chunk in self._gtts_synthesize(text, language):
                    yield chunk
    
    async def synthesize_stream_async(
        self, 
        text: str, 
        language: str = "en",
        raw_pcm: bool = False
    ):
        """
        Async version: Synthesize speech with TRUE STREAMING for all languages
        
        Args:
            text: Text to synthesize
            language: Language code (en, hi, te)
            raw_pcm: If True, streams raw PCM data chunk-by-chunk (for English only)
        
        Yields:
            Audio chunks as bytes (PCM/WAV for English, MP3 for Hindi/Telugu with Edge TTS)
        """
        if language in self.indian_languages:
            # Use Edge TTS for Hindi/Telugu - TRUE STREAMING!
            if self.use_edge_tts:
                logger.debug(f"Using Edge TTS for {language}: {text[:50]}...")
                async for chunk in self._edge_tts_synthesize_stream(text, language):
                    yield chunk
            elif GTTS_AVAILABLE:
                # Fallback to gTTS (not streaming, but works)
                logger.debug(f"Using gTTS fallback for {language}")
                loop = asyncio.get_event_loop()
                chunks = await loop.run_in_executor(None, lambda: list(self._gtts_synthesize(text, language)))
                for chunk in chunks:
                    yield chunk
            else:
                # Final fallback to English
                logger.warning(f"No TTS available for {language}, using English")
                async for chunk in piper_tts.synthesize_stream(text, language='en'):
                    yield chunk
        else:
            # Use Piper for English
            if raw_pcm:
                # TRUE STREAMING: Convert mono to stereo and stream in larger chunks
                # Use 4KB chunks for better performance (still real-time)
                mono_buffer = bytearray()
                chunk_size = 4096  # 4KB chunks for efficient streaming
                
                async for mono_chunk in piper_tts.synthesize_stream(text, language='en'):
                    mono_buffer.extend(mono_chunk)
                    
                    # When we have enough data, convert and yield in chunks
                    while len(mono_buffer) >= chunk_size:
                        # Extract chunk (must be even number for 16-bit samples)
                        process_size = chunk_size if chunk_size % 2 == 0 else chunk_size - 1
                        mono_data = bytes(mono_buffer[:process_size])
                        mono_buffer = mono_buffer[process_size:]
                        
                        # Convert mono to stereo efficiently
                        stereo_data = self._mono_to_stereo(mono_data)
                        yield stereo_data
                
                # Process remaining bytes
                if len(mono_buffer) >= 2:
                    # Make sure it's an even number of bytes
                    process_size = len(mono_buffer) if len(mono_buffer) % 2 == 0 else len(mono_buffer) - 1
                    if process_size > 0:
                        mono_data = bytes(mono_buffer[:process_size])
                        stereo_data = self._mono_to_stereo(mono_data)
                        yield stereo_data
            else:
                # NON-STREAMING: Collect all, convert to stereo, add WAV header
                pcm_data = b""
                async for chunk in piper_tts.synthesize_stream(text, language='en'):
                    pcm_data += chunk
                
                # Convert mono to stereo
                stereo_data = self._mono_to_stereo(pcm_data)
                
                # Create WAV header with correct size
                wav_header = self._create_wav_header(
                    sample_rate=22050, 
                    num_channels=2,  # Stereo
                    bits_per_sample=16, 
                    data_size=len(stereo_data)
                )
                
                # Yield complete WAV file (header + stereo data)
                yield wav_header
                yield stereo_data
    
    def synthesize_stream(
        self, 
        text: str, 
        language: str = "en"
    ) -> Generator[bytes, None, None]:
        """
        SYNC version: Synthesize speech (for backward compatibility)
        Use synthesize_stream_async for async contexts!
        
        Args:
            text: Text to synthesize
            language: Language code (en, hi, te)
        
        Yields:
            Audio chunks as bytes
        """
        if language in self.indian_languages:
            # Use Edge TTS for Hindi/Telugu in sync context
            if self.use_edge_tts:
                yield from self._edge_tts_synthesize_sync(text, language)
            elif GTTS_AVAILABLE:
                yield from self._gtts_synthesize(text, language)
            else:
                # Fallback to English
                yield from self._piper_synthesize_sync(text, 'en')
        else:
            # Use Piper for English - collect all, convert to stereo, add proper WAV header
            try:
                import subprocess
                # Direct piper call for sync context
                cmd = [
                    "piper",
                    "--model", str(piper_tts._get_model('en')),
                    "--output-raw",
                    "--length_scale", "1.0",
                    "--noise_scale", "0.667",
                    "--noise_w", "0.8"
                ]
                
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                # Write text and close stdin
                process.stdin.write(text.encode('utf-8'))
                process.stdin.close()
                
                # Collect all PCM data
                pcm_data = b""
                while True:
                    chunk = process.stdout.read(4096)
                    if not chunk:
                        break
                    pcm_data += chunk
                
                process.wait()
                
                # Convert mono to stereo
                stereo_data = self._mono_to_stereo(pcm_data)
                
                # Create proper WAV header with correct size
                wav_header = self._create_wav_header(
                    sample_rate=22050,
                    num_channels=2,  # Stereo
                    bits_per_sample=16,
                    data_size=len(stereo_data)
                )
                
                # Yield complete WAV file
                yield wav_header
                yield stereo_data
                
            except Exception as e:
                logger.error(f"Piper sync synthesis error: {e}")
    
    def _edge_tts_synthesize_sync(self, text: str, language: str) -> Generator[bytes, None, None]:
        """Sync wrapper for Edge TTS streaming"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def collect_chunks():
                    chunks = []
                    async for chunk in self._edge_tts_synthesize_stream(text, language):
                        chunks.append(chunk)
                    return chunks
                
                chunks = loop.run_until_complete(collect_chunks())
                for chunk in chunks:
                    yield chunk
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Edge TTS sync error: {e}")
            # Fallback to gTTS
            if GTTS_AVAILABLE:
                yield from self._gtts_synthesize(text, language)
    
    def _piper_synthesize_sync(self, text: str, language: str) -> Generator[bytes, None, None]:
        """Synthesize using Piper (English) - SYNC wrapper"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async_gen = piper_tts.synthesize_stream(text, language='en')
                while True:
                    try:
                        chunk = loop.run_until_complete(async_gen.__anext__())
                        yield chunk
                    except StopAsyncIteration:
                        break
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Piper synthesis error: {e}")
    
    def _gtts_synthesize(self, text: str, language: str) -> Generator[bytes, None, None]:
        """Synthesize using gTTS (Hindi/Telugu)"""
        try:
            # Map language codes
            lang_map = {
                'hi': 'hi',  # Hindi
                'te': 'te'   # Telugu
            }
            
            # Generate speech
            tts = gTTS(text=text, lang=lang_map.get(language, 'en'), slow=False)
            
            # Convert to bytes
            audio_buffer = io.BytesIO()
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)
            
            # Read in chunks (simulate streaming)
            chunk_size = 4096
            while True:
                chunk = audio_buffer.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        
        except Exception as e:
            logger.error(f"gTTS synthesis error: {e}")
            # Fallback to English Piper
            logger.info("Falling back to English TTS")
            yield from self._piper_synthesize(text, 'en')

# Global service instance
tts_service = HybridTTSService()
