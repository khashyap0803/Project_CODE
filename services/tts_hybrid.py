"""
Hybrid TTS Service: Piper (English) + Edge TTS (Hindi/Telugu) with TRUE STREAMING
Provides high-quality TTS for all three languages with real-time streaming
Converts all audio to unified PCM/WAV format (22050Hz, stereo, 16-bit)
"""
import os
import io
import asyncio
import struct
import tempfile
import subprocess
from pathlib import Path
from typing import Generator, Optional, AsyncGenerator
from services.tts import piper_tts  # Use global instance
from core.config import settings
from core.logger import setup_logger
import time

logger = setup_logger(__name__)

# pydub for audio format conversion
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
    logger.info("pydub available for MP3→PCM conversion")
except ImportError:
    PYDUB_AVAILABLE = False
    logger.warning("pydub not available - Edge TTS may not work correctly")

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
# Using highest quality neural voices
EDGE_TTS_VOICES = {
    'hi': 'hi-IN-SwaraNeural',    # Hindi female - very natural
    'te': 'te-IN-ShrutiNeural',   # Telugu female - clear pronunciation
}

# Hindi number words for better TTS pronunciation
HINDI_NUMBERS = {
    0: 'शून्य', 1: 'एक', 2: 'दो', 3: 'तीन', 4: 'चार', 5: 'पांच',
    6: 'छह', 7: 'सात', 8: 'आठ', 9: 'नौ', 10: 'दस',
    11: 'ग्यारह', 12: 'बारह', 13: 'तेरह', 14: 'चौदह', 15: 'पंद्रह',
    16: 'सोलह', 17: 'सत्रह', 18: 'अठारह', 19: 'उन्नीस', 20: 'बीस',
    21: 'इक्कीस', 22: 'बाईस', 23: 'तेईस', 24: 'चौबीस', 25: 'पच्चीस',
    26: 'छब्बीस', 27: 'सत्ताईस', 28: 'अट्ठाईस', 29: 'उनतीस', 30: 'तीस',
    31: 'इकतीस', 32: 'बत्तीस', 33: 'तैंतीस', 34: 'चौंतीस', 35: 'पैंतीस',
    36: 'छत्तीस', 37: 'सैंतीस', 38: 'अड़तीस', 39: 'उनतालीस', 40: 'चालीस',
    41: 'इकतालीस', 42: 'बयालीस', 43: 'तैंतालीस', 44: 'चौवालीस', 45: 'पैंतालीस',
    46: 'छियालीस', 47: 'सैंतालीस', 48: 'अड़तालीस', 49: 'उनचास', 50: 'पचास',
    51: 'इक्यावन', 52: 'बावन', 53: 'तिरपन', 54: 'चौवन', 55: 'पचपन',
    56: 'छप्पन', 57: 'सत्तावन', 58: 'अट्ठावन', 59: 'उनसठ', 60: 'साठ',
    61: 'इकसठ', 62: 'बासठ', 63: 'तिरसठ', 64: 'चौंसठ', 65: 'पैंसठ',
    66: 'छियासठ', 67: 'सड़सठ', 68: 'अड़सठ', 69: 'उनहत्तर', 70: 'सत्तर',
    71: 'इकहत्तर', 72: 'बहत्तर', 73: 'तिहत्तर', 74: 'चौहत्तर', 75: 'पचहत्तर',
    76: 'छिहत्तर', 77: 'सतहत्तर', 78: 'अठहत्तर', 79: 'उनासी', 80: 'अस्सी',
    81: 'इक्यासी', 82: 'बयासी', 83: 'तिरासी', 84: 'चौरासी', 85: 'पचासी',
    86: 'छियासी', 87: 'सत्तासी', 88: 'अट्ठासी', 89: 'नवासी', 90: 'नब्बे',
    91: 'इक्यानवे', 92: 'बानवे', 93: 'तिरानवे', 94: 'चौरानवे', 95: 'पचानवे',
    96: 'छियानवे', 97: 'सत्तानवे', 98: 'अट्ठानवे', 99: 'निन्यानवे', 100: 'सौ'
}

def convert_numbers_to_hindi_words(text: str) -> str:
    """Convert numeric digits to Hindi words for better TTS pronunciation"""
    import re
    
    def replace_number(match):
        num = int(match.group())
        if num in HINDI_NUMBERS:
            return HINDI_NUMBERS[num]
        elif num < 1000:
            # Handle larger numbers: break into hundreds + remainder
            hundreds = num // 100
            remainder = num % 100
            result = []
            if hundreds > 0:
                result.append(HINDI_NUMBERS.get(hundreds, str(hundreds)))
                result.append('सौ')
            if remainder > 0:
                result.append(HINDI_NUMBERS.get(remainder, str(remainder)))
            return ' '.join(result)
        return str(num)  # Keep as-is for very large numbers
    
    # Replace standalone numbers (not part of URLs, times, etc.)
    original = text
    result = re.sub(r'\b(\d{1,3})\b', replace_number, text)
    if original != result:
        logger.debug(f"Hindi number conversion: '{original}' → '{result}'")
    return result

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
        Stream audio from Edge TTS with TRUE STREAMING MP3→PCM conversion.
        Uses ffmpeg pipe for real-time conversion without waiting for full audio.
        Output: 22050Hz, stereo, 16-bit PCM (matches Piper output format)
        """
        voice = EDGE_TTS_VOICES.get(language, EDGE_TTS_VOICES.get('hi'))
        start_time = time.time()
        
        # Convert numbers to Hindi words for better pronunciation
        if language == 'hi':
            text = convert_numbers_to_hindi_words(text)
        
        try:
            # Start ffmpeg process for real-time MP3→PCM conversion
            # Input: MP3 stream, Output: raw PCM s16le, 22050Hz, stereo
            ffmpeg_process = await asyncio.create_subprocess_exec(
                'ffmpeg',
                '-hide_banner', '-loglevel', 'error',
                '-f', 'mp3', '-i', 'pipe:0',  # Input: MP3 from stdin
                '-f', 's16le',                 # Output format: raw PCM
                '-ar', '22050',                # Sample rate: 22050Hz (match Piper)
                '-ac', '2',                    # Channels: stereo
                '-acodec', 'pcm_s16le',        # Codec: 16-bit signed little-endian
                'pipe:1',                      # Output to stdout
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Use slightly faster rate (+5%) for lower latency while maintaining quality
            # Rate range: -50% to +100%, default is +0%
            communicate = edge_tts.Communicate(text, voice, rate="+5%")
            
            # Task to feed MP3 data to ffmpeg stdin
            async def feed_mp3():
                try:
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            ffmpeg_process.stdin.write(chunk["data"])
                            await ffmpeg_process.stdin.drain()
                    ffmpeg_process.stdin.close()
                    await ffmpeg_process.stdin.wait_closed()
                except Exception as e:
                    logger.error(f"Edge TTS feed error: {e}")
                    try:
                        ffmpeg_process.stdin.close()
                    except:
                        pass
            
            # Start feeding MP3 data in background
            feed_task = asyncio.create_task(feed_mp3())
            
            # Read PCM output from ffmpeg in real-time
            first_chunk = True
            total_bytes = 0
            chunk_size = 4096  # 4KB chunks for smooth streaming
            
            while True:
                pcm_chunk = await ffmpeg_process.stdout.read(chunk_size)
                if not pcm_chunk:
                    break
                    
                if first_chunk:
                    first_chunk = False
                    logger.debug(f"Edge TTS first PCM chunk in {time.time() - start_time:.3f}s")
                
                total_bytes += len(pcm_chunk)
                yield pcm_chunk
            
            # Wait for feed task to complete
            await feed_task
            
            # Wait for ffmpeg to finish
            await ffmpeg_process.wait()
            
            logger.info(f"Edge TTS [{language}]: {len(text)} chars → {total_bytes} bytes PCM in {time.time() - start_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Edge TTS streaming error: {e}")
            # Fallback to non-streaming method
            async for chunk in self._edge_tts_fallback(text, language):
                yield chunk
    
    async def _edge_tts_fallback(self, text: str, language: str) -> AsyncGenerator[bytes, None]:
        """Fallback: collect all MP3, then convert (higher latency but more reliable)"""
        voice = EDGE_TTS_VOICES.get(language, EDGE_TTS_VOICES.get('hi'))
        
        try:
            communicate = edge_tts.Communicate(text, voice)
            mp3_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_data += chunk["data"]
            
            if not mp3_data:
                logger.warning("Edge TTS returned no audio data")
                return
            
            # Convert using pydub
            if PYDUB_AVAILABLE:
                audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
                audio = audio.set_frame_rate(22050).set_channels(2).set_sample_width(2)
                pcm_data = audio.raw_data
                
                chunk_size = 4096
                for i in range(0, len(pcm_data), chunk_size):
                    yield pcm_data[i:i + chunk_size]
            else:
                # ffmpeg fallback
                async for chunk in self._convert_mp3_to_pcm_ffmpeg(mp3_data):
                    yield chunk
                    
        except Exception as e:
            logger.error(f"Edge TTS fallback error: {e}")
    
    async def _convert_mp3_to_pcm_ffmpeg(self, mp3_data: bytes) -> AsyncGenerator[bytes, None]:
        """Convert MP3 to PCM using ffmpeg subprocess"""
        try:
            # Use ffmpeg to convert MP3 to raw PCM
            process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-i', 'pipe:0', '-f', 's16le', '-ar', '22050', '-ac', '2', 'pipe:1',
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate(input=mp3_data)
            
            if process.returncode != 0:
                logger.error(f"ffmpeg error: {stderr.decode()}")
                return
                
            # Stream PCM data in chunks
            chunk_size = 4096
            for i in range(0, len(stdout), chunk_size):
                yield stdout[i:i + chunk_size]
                
        except Exception as e:
            logger.error(f"ffmpeg conversion error: {e}")
    
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
            yield from self._piper_synthesize_sync(text, 'en')

# Global service instance
tts_service = HybridTTSService()
