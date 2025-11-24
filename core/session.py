"""
Session management for maintaining conversation context and state
"""
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import deque
from core.logger import setup_logger

logger = setup_logger(__name__)

@dataclass
class ConversationTurn:
    """Single turn in a conversation"""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Session:
    """User session with conversation history and context"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    conversation_history: deque = field(default_factory=lambda: deque(maxlen=200))  # Increased from 20 to 200 turns
    context: Dict[str, Any] = field(default_factory=dict)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    
    def add_turn(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Add a conversation turn"""
        turn = ConversationTurn(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self.conversation_history.append(turn)
        self.last_activity = datetime.now()
        logger.debug(f"Session {self.session_id[:8]}: Added {role} turn")
    
    def get_history(self, last_n: Optional[int] = None) -> List[Dict[str, str]]:
        """Get conversation history in LLM format"""
        history = list(self.conversation_history)
        if last_n:
            history = history[-last_n:]
        return [{"role": turn.role, "content": turn.content} for turn in history]
    
    def is_expired(self, timeout_seconds: int) -> bool:
        """Check if session has expired"""
        return (datetime.now() - self.last_activity).seconds > timeout_seconds
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history.clear()
        logger.info(f"Session {self.session_id[:8]}: History cleared")

class SessionManager:
    """Manages multiple user sessions"""
    
    def __init__(self, timeout_seconds: int = 1800):
        self.sessions: Dict[str, Session] = {}
        self.timeout = timeout_seconds
        logger.info(f"SessionManager initialized (timeout: {timeout_seconds}s)")
    
    def create_session(self, session_id: Optional[str] = None) -> Session:
        """Create a new session"""
        session = Session(session_id=session_id or str(uuid.uuid4()))
        self.sessions[session.session_id] = session
        logger.info(f"Created session: {session.session_id[:8]}")
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """Get existing session or None"""
        session = self.sessions.get(session_id)
        if session and not session.is_expired(self.timeout):
            return session
        elif session:
            logger.warning(f"Session {session_id[:8]} expired, removing")
            self.sessions.pop(session_id, None)
        return None
    
    def get_or_create_session(self, session_id: Optional[str] = None) -> Session:
        """Get existing session or create new one"""
        if session_id:
            session = self.get_session(session_id)
            if session:
                return session
        return self.create_session(session_id)
    
    def cleanup_expired(self):
        """Remove expired sessions"""
        expired = [
            sid for sid, session in self.sessions.items()
            if session.is_expired(self.timeout)
        ]
        for sid in expired:
            logger.info(f"Cleaning up expired session: {sid[:8]}")
            self.sessions.pop(sid, None)
        return len(expired)

# Global session manager
session_manager = SessionManager()
