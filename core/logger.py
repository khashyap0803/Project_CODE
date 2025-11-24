"""
Professional logging setup with structured output
"""
import logging
import sys
from pathlib import Path
from typing import Optional
from .config import settings

def setup_logger(name: str, log_file: Optional[str] = None) -> logging.Logger:
    """
    Create a configured logger instance
    
    Args:
        name: Logger name (usually __name__)
        log_file: Optional specific log file
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.LOG_LEVEL))
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Console handler with color support
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter(
        '%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler for persistent logs
    if log_file:
        file_path = settings.LOGS_PATH / log_file
    else:
        file_path = settings.LOGS_PATH / f"{name.split('.')[-1]}.log"
    
    file_handler = logging.FileHandler(file_path, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(settings.LOG_FORMAT)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger
