"""
Text-to-Speech using Piper with streaming support
"""
import subprocess
import asyncio
from pathlib import Path
from typing import AsyncGenerator, Optional
from core.config import settings
from core.logger import setup_logger

logger = setup_logger(__name__)

class PiperTTS:
    """Text-to-speech using Piper with multilingual support"""
    
    def __init__(self):
        self.models = {}
        self._load_models()
        logger.info(f"PiperTTS initialized (languages: {list(self.models.keys())})")
    
    def _load_models(self):
        """Load available Piper models for each language"""
        for lang, model_name in settings.PIPER_MODELS.items():
            model_file = settings.PIPER_MODEL_PATH / f"{model_name}.onnx"
            if model_file.exists():
                self.models[lang] = model_file
                logger.info(f"Loaded {lang} TTS model: {model_name}")
            else:
                logger.warning(f"Model not found for {lang}: {model_file}, will use fallback")
        
        # Ensure at least English model exists
        if "en" not in self.models:
            raise FileNotFoundError("English Piper model not found! Cannot initialize TTS.")
        
        # Use English as fallback for missing languages
        if "hi" not in self.models:
            logger.info("Hindi model not available, using English as fallback")
            self.models["hi"] = self.models["en"]
        if "te" not in self.models:
            logger.info("Telugu model not available, using English as fallback")
            self.models["te"] = self.models["en"]
    
    def _get_model(self, language: str = "en") -> Path:
        """Get model path for language"""
        return self.models.get(language, self.models.get(settings.PIPER_DEFAULT_LANG))
    
    async def synthesize_stream(
        self,
        text: str,
        language: str = "en",
        speaker: Optional[int] = None
    ) -> AsyncGenerator[bytes, None]:
        """
        Synthesize speech and stream audio chunks
        
        Args:
            text: Text to synthesize
            language: Language code (en, hi, te)
            speaker: Speaker ID (if multi-speaker model)
            
        Yields:
            Audio chunks as bytes (PCM 16-bit)
        """
        if not text.strip():
            return
        
        model_path = self._get_model(language)
        logger.debug(f"Synthesizing ({language}): '{text[:50]}...'")
        
        try:
            # Build piper command with speed optimization
            cmd = [
                "piper",
                "--model", str(model_path),
                "--output-raw",
                "--length_scale", str(1.0 / settings.PIPER_SPEED),  # Speed control
                "--noise_scale", "0.667",
                "--noise_w", "0.8"
            ]
            
            if speaker is not None:
                cmd.extend(["--speaker", str(speaker)])
            
            # Start piper process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Write text to stdin
            process.stdin.write(text.encode('utf-8'))
            await process.stdin.drain()
            process.stdin.close()
            
            # Stream output chunks
            chunk_size = settings.AUDIO_BUFFER_SIZE
            while True:
                chunk = await process.stdout.read(chunk_size)
                if not chunk:
                    break
                yield chunk
            
            # Wait for completion
            await process.wait()
            
            if process.returncode != 0:
                stderr = await process.stderr.read()
                logger.error(f"Piper error: {stderr.decode()}")
            else:
                logger.debug(f"Synthesis complete: {len(text)} chars")
                
        except Exception as e:
            logger.error(f"TTS error: {e}")
    
    async def synthesize_complete(self, text: str, language: str = "en") -> bytes:
        """Synthesize complete audio (non-streaming)"""
        audio_data = b""
        async for chunk in self.synthesize_stream(text, language):
            audio_data += chunk
        return audio_data

# Global Piper instance
piper_tts = PiperTTS()
