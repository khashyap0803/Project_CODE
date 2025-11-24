"""
Speech-to-Text using faster-whisper with streaming support
"""
import numpy as np
from faster_whisper import WhisperModel
from typing import Optional, Dict
from core.config import settings
from core.logger import setup_logger

logger = setup_logger(__name__)

class WhisperSTT:
    """Speech recognition using faster-whisper"""
    
    def __init__(self):
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Load Whisper model"""
        try:
            logger.info(f"Loading Whisper model: {settings.WHISPER_MODEL}")
            self.model = WhisperModel(
                settings.WHISPER_MODEL,
                device=settings.WHISPER_DEVICE,
                compute_type=settings.WHISPER_COMPUTE_TYPE,
                download_root=str(settings.WHISPER_MODEL_PATH)
            )
            logger.info("Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise
    
    def transcribe_audio(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        language: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Transcribe audio data with multilingual support
        
        Args:
            audio_data: Raw audio bytes (16-bit PCM)
            sample_rate: Audio sample rate
            language: Language code (auto-detect if None) - en, hi, te
            
        Returns:
            Dict with 'text', 'language', 'confidence'
        """
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Resample if needed (faster-whisper expects 16kHz)
            if sample_rate != 16000:
                logger.warning(f"Resampling from {sample_rate}Hz to 16000Hz")
                # Simple resampling (for production, use librosa)
                audio_array = self._resample(audio_array, sample_rate, 16000)
            
            logger.debug(f"Transcribing audio: {len(audio_array)/16000:.2f}s")
            
            # Auto-detect language if not specified
            # Whisper supports en, hi, te natively
            segments, info = self.model.transcribe(
                audio_array,
                language=language,  # None for auto-detect
                beam_size=settings.WHISPER_BEAM_SIZE,
                vad_filter=True,  # Voice activity detection
                vad_parameters=dict(
                    min_silence_duration_ms=500,
                    threshold=0.5
                ),
                # Optimize for supported languages
                language_detection_threshold=0.5
            )
            
            # Combine segments
            text = " ".join([segment.text for segment in segments]).strip()
            
            logger.info(f"Transcribed: '{text}' (lang: {info.language}, prob: {info.language_probability:.2f})")
            
            return {
                "text": text,
                "language": info.language,
                "confidence": info.language_probability,
                "duration": info.duration
            }
            
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return {
                "text": "",
                "language": "en",
                "confidence": 0.0,
                "error": str(e)
            }
    
    def _resample(self, audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Simple resampling (for production use librosa.resample)"""
        duration = len(audio) / orig_sr
        target_length = int(duration * target_sr)
        indices = np.linspace(0, len(audio) - 1, target_length)
        return np.interp(indices, np.arange(len(audio)), audio)

# Global Whisper instance
whisper_stt = WhisperSTT()
