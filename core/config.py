"""
JARVIS - Advanced Voice Assistant Configuration
Professional, modular configuration management
"""
import os
from pathlib import Path
from typing import Optional, Dict
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # === Paths ===
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    WHISPER_MODEL_PATH: Path = PROJECT_ROOT / "whisper-data"
    PIPER_MODEL_PATH: Path = PROJECT_ROOT / "piper-data"
    LLM_MODEL_PATH: Path = Path("/home/nani/llama.cpp/models/mistral-small-24b-instruct-q4_k_m.gguf")
    VECTOR_DB_PATH: Path = PROJECT_ROOT / "vector_db"
    LOGS_PATH: Path = PROJECT_ROOT / "logs"
    
    # === Server Configuration ===
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WS_PING_INTERVAL: int = 30
    WS_PING_TIMEOUT: int = 10
    
    # === Speech-to-Text (Whisper) ===
    WHISPER_MODEL: str = "small"  # small, medium, large
    WHISPER_DEVICE: str = "cpu"  # Use CPU to save VRAM for LLM
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_BEAM_SIZE: int = 5
    WHISPER_LANGUAGE: Optional[str] = None  # Auto-detect: en, hi, te
    WHISPER_SUPPORTED_LANGUAGES: list = ["en", "hi", "te"]  # English, Hindi, Telugu
    
    # === LLM Configuration ===
    LLM_API_URL: str = "http://localhost:8080/v1/chat/completions"
    LLM_MODEL_NAME: str = "mistral-small"
    LLM_MAX_CONTEXT: int = 8192
    LLM_SERVER_MAX_CONTEXT: int = 2048  # Actual upstream limit
    LLM_TEMPERATURE: float = 0.7
    LLM_TOP_P: float = 0.9
    LLM_STREAM: bool = True
    
    # Performance optimizations
    LLM_SIMPLE_QUERY_MAX_TOKENS: int = 150  # Fast responses
    LLM_NORMAL_QUERY_MAX_TOKENS: int = 500
    LLM_DETAILED_QUERY_MAX_TOKENS: int = 1200
    LLM_FAST_TIMEOUT: int = 5  # Aggressive timeout for simple queries
    LLM_NORMAL_TIMEOUT: int = 15
    LLM_FORCED_SENTENCE_CHARS: int = 150  # Longer buffer for better Hindi/Telugu breaks
    
    # === Text-to-Speech (Piper) ===
    PIPER_MODELS: Dict[str, str] = {
        "en": "en_US-lessac-medium",
        "hi": "hi_HI-medium",  # Hindi model
        "te": "te_IN-medium"   # Telugu model
    }
    PIPER_DEFAULT_LANG: str = "en"
    PIPER_SPEAKER: Optional[int] = None
    PIPER_SAMPLE_RATE: int = 22050
    PIPER_SPEED: float = 1.1  # Slightly faster for lower latency
    
    # === Perplexity API ===
    PERPLEXITY_API_KEY: str = os.getenv("PERPLEXITY_API_KEY", "")  # Set via .env file
    PERPLEXITY_MODEL: str = "sonar-pro"  # sonar-pro or sonar for faster/cheaper
    PERPLEXITY_MAX_TOKENS: int = 1000
    
    # === Session Management ===
    SESSION_TIMEOUT: int = 1800  # 30 minutes
    MAX_CONVERSATION_HISTORY: int = 20  # Last N turns
    CONVERSATION_SUMMARY_THRESHOLD: int = 15  # Summarize after N turns
    
    # === Vector Database ===
    VECTOR_DB_COLLECTION: str = "jarvis_memory"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    VECTOR_SEARCH_TOP_K: int = 5
    
    # === Performance ===
    MAX_WORKERS: int = 4
    ENABLE_CUDA: bool = True
    AUDIO_BUFFER_SIZE: int = 4096
    
    # === Features ===
    ENABLE_WEB_SEARCH: bool = True
    ENABLE_CODE_EXECUTION: bool = True
    ENABLE_MEMORY: bool = True
    ENABLE_INTERRUPTION: bool = True
    
    # === Logging ===
    LOG_LEVEL: str = "DEBUG"
    LOG_FORMAT: str = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Global settings instance
settings = Settings()

# Ensure required directories exist
settings.LOGS_PATH.mkdir(exist_ok=True)
settings.VECTOR_DB_PATH.mkdir(exist_ok=True)
