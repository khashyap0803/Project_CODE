"""
JARVIS Main Server - FastAPI with WebSocket streaming
Professional voice assistant with real-time audio processing
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from typing import Optional, Dict, List
import asyncio
from contextlib import suppress
import json
import time
import io
import os
import shlex
import shutil
from pathlib import Path

from core.config import settings
from core.logger import setup_logger
from core.session import session_manager
from services import whisper_stt, llm, LLMContextExceededError
from services.tts_hybrid import tts_service as piper_tts
from tools import perplexity, tool_manager
from tools.code_executor import execute_code, run_command, get_system_status, manage_file

# Setup logger first
logger = setup_logger(__name__)

# Try to import browser automation (Selenium)
try:
    from tools.browser_automation import browser_tool
    BROWSER_AUTOMATION_AVAILABLE = True
    logger.info("Browser automation (Selenium) available")
except Exception as e:
    browser_tool = None
    BROWSER_AUTOMATION_AVAILABLE = False
    logger.warning(f"Browser automation not available: {e}")

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

def limit_history_for_context(history: List[Dict[str, str]], char_limit: int) -> List[Dict[str, str]]:
    """Trim history so the combined text stays within an approximate char budget"""
    if not history:
        return history
    trimmed: List[Dict[str, str]] = []
    total_chars = 0
    # Walk from newest to oldest so we always keep the latest turns
    for turn in reversed(history):
        content_len = len(turn.get("content", ""))
        if trimmed and total_chars + content_len > char_limit:
            break
        trimmed.append(turn)
        total_chars += content_len
    return list(reversed(trimmed))


def calculate_max_prompt_chars() -> int:
    """Derive a conservative character budget from MAX_HISTORY or LLM context."""
    # Default fallback assumes 8192 context (~3 chars/token)
    max_ctx = settings.LLM_MAX_CONTEXT or 8192
    server_ctx = getattr(settings, "LLM_SERVER_MAX_CONTEXT", None)
    if server_ctx:
        max_ctx = min(max_ctx, server_ctx)
    # Be conservative: keep prompts under 65% of total context to leave headroom for response tokens
    return int(max_ctx * 0.65 * 3)

# === OS / Application Control Helpers ===

ACTION_VERBS = ("open", "launch", "start", "run", "execute", "play")

APP_KEYWORDS = {
    # System utilities
    "terminal": "terminal",
    "terminal emulator": "terminal",
    "command prompt": "terminal",
    "console": "terminal",
    "system settings": "system_settings",
    "settings": "system_settings",
    "control center": "system_settings",
    "file manager": "file_manager",
    "files": "file_manager",
    "file explorer": "file_manager",
    "calculator": "calculator",
    "text editor": "text_editor",
    "notepad": "text_editor",
    "gedit": "text_editor",

    # Browsers
    "browser": "browser",
    "firefox": "firefox",
    "chrome": "chrome",
    "chromium": "chrome",
    "google chrome": "chrome",
    "edge": "edge",
    "microsoft edge": "edge",

    # IDEs / Editors
    "vscode": "vscode",
    "vs code": "vscode",
    "visual studio code": "vscode",
    "pycharm": "pycharm",
    "sublime": "sublime",
    "atom": "atom",
    "android studio": "android_studio",
    "intellij": "intellij",

    # Maker tools
    "arduino": "arduino",
    "arduino ide": "arduino",

    # Communication / media
    "whatsapp": "whatsapp",
    "telegram": "telegram",
    "discord": "discord",
    "slack": "slack",
    "spotify": "spotify",
    "vlc": "vlc",
    "teamviewer": "teamviewer",
    "gimp": "gimp",
    "zoom": "zoom",
}

APP_COMMAND_CANDIDATES = {
    "terminal": [
        "kgx",  # GNOME console
        "gnome-terminal",
        "x-terminal-emulator",
        "tilix",
        "konsole",
        "xfce4-terminal",
        "mate-terminal",
        "alacritty",
        "xterm",
        "gtk-launch org.gnome.Console.desktop",
    ],
    "system_settings": [
        "gnome-control-center",
        "unity-control-center",
        "systemsettings5",
        "xfce4-settings-manager",
        "kcmshell5",
        "gtk-launch org.gnome.Settings.desktop",
    ],
    "file_manager": [
        "nautilus",
        "nemo",
        "dolphin",
        "thunar",
        "pcmanfm",
        "gtk-launch org.gnome.Nautilus.desktop",
    ],
    "vscode": ["code"],
    "pycharm": ["pycharm", "pycharm-community"],
    "sublime": ["subl", "sublime_text"],
    "atom": ["atom"],
    "arduino": ["arduino-ide", "arduino"],
    "intellij": ["idea", "intellij-idea-community", "intellij-idea-ultimate"],
    "android_studio": ["studio.sh", "android-studio"],
    "browser": ["xdg-open https://www.google.com", "firefox", "google-chrome", "chromium", "chromium-browser"],
    "firefox": ["firefox"],
    "chrome": ["google-chrome", "chrome", "chromium", "chromium-browser"],
    "edge": ["microsoft-edge", "microsoft-edge-stable"],
    "calculator": ["gnome-calculator", "kcalc"],
    "text_editor": ["gedit", "xed", "kate", "mousepad"],
    "whatsapp": [
        "firefox https://web.whatsapp.com",
        "google-chrome https://web.whatsapp.com",
    ],
    "telegram": ["telegram-desktop"],
    "discord": ["discord"],
    "slack": ["slack"],
    "spotify": ["spotify"],
    "vlc": ["vlc"],
    "teamviewer": ["teamviewer"],
    "gimp": ["gimp"],
    "zoom": ["zoom"],
}

APP_ENV_OVERRIDES = {
    "system_settings": {
        "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
        "DESKTOP_SESSION": "gnome",
    }
}

APP_DESKTOP_HINTS = {
    "terminal": ["console", "kgx", "konsole"],
    "system_settings": ["settings", "controlcenter", "controlcentre", "gnomecontrolcenter"],
    "file_manager": ["nautilus", "nemo", "thunar", "dolphin"],
}

ENV_DEFAULT_VARS = {
    "XDG_CURRENT_DESKTOP": "GNOME",
    "DESKTOP_SESSION": "gnome",
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin",
}

ENV_PASSTHROUGH_VARS = (
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XDG_RUNTIME_DIR",
    "DBUS_SESSION_BUS_ADDRESS",
    "XAUTHORITY",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "GNOME_DESKTOP_SESSION_ID",
    "SESSION_MANAGER",
)

def _build_env_wrapper_tokens(env_overrides: Optional[Dict[str, str]] = None) -> List[str]:
    overrides = env_overrides or {}
    tokens: List[str] = ["env", "-i"]

    for key, default in ENV_DEFAULT_VARS.items():
        value = overrides.get(key, os.environ.get(key)) or default
        if value:
            tokens.append(f"{key}={value}")

    for key in ENV_PASSTHROUGH_VARS:
        if key in ENV_DEFAULT_VARS:
            continue
        value = overrides.get(key, os.environ.get(key))
        if value:
            tokens.append(f"{key}={value}")

    for key, value in overrides.items():
        if key in ENV_DEFAULT_VARS or key in ENV_PASSTHROUGH_VARS:
            continue
        if value:
            tokens.append(f"{key}={value}")

    return tokens

DESKTOP_DIRS = [
    Path.home() / ".local/share/applications",
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
]

def _normalize_text(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())

def _build_desktop_cache() -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    for directory in DESKTOP_DIRS:
        try:
            if not directory.exists():
                continue
            for desktop_file in directory.glob("*.desktop"):
                entries.append({
                    "file": desktop_file.name,
                    "match": _normalize_text(desktop_file.stem)
                })
        except Exception as exc:
            logger.debug(f"Skipping desktop directory {directory}: {exc}")
    return entries

DESKTOP_CACHE = _build_desktop_cache()

def find_desktop_entry(app_name: str) -> Optional[str]:
    """Return .desktop filename that best matches the app name"""
    normalized = _normalize_text(app_name)
    if not normalized:
        return None
    for entry in DESKTOP_CACHE:
        if normalized in entry["match"]:
            return entry["file"]
    return None

def find_available_command(candidates: List[str]) -> Optional[str]:
    """Return the first available command from candidates"""
    for candidate in candidates:
        try:
            parts = shlex.split(candidate)
        except ValueError as exc:
            logger.debug(f"Unable to parse command '{candidate}': {exc}")
            continue
        if not parts:
            continue
        executable = parts[0]
        if shutil.which(executable):
            return " ".join(parts)
    return None

def build_launch_command(command: str, env_overrides: Optional[Dict[str, str]] = None) -> str:
    env_tokens = _build_env_wrapper_tokens(env_overrides)
    try:
        parts = shlex.split(command)
    except ValueError:
        parts = [command]

    parts = [part for part in parts if part]
    if not parts:
        parts = [command]

    final_tokens = ["nohup", *(env_tokens or []), *parts]
    quoted = " ".join(shlex.quote(token) for token in final_tokens)
    return f"{quoted} &"

def resolve_known_application(key: str) -> Optional[str]:
    candidates = APP_COMMAND_CANDIDATES.get(key)
    if candidates:
        command = find_available_command(candidates)
        if command:
            return build_launch_command(command, APP_ENV_OVERRIDES.get(key))
    # Try desktop entry fallback
    desktop_entry = find_desktop_entry(key)
    if not desktop_entry:
        for hint in APP_DESKTOP_HINTS.get(key, []):
            desktop_entry = find_desktop_entry(hint)
            if desktop_entry:
                break
    if desktop_entry and shutil.which('gtk-launch'):
        return build_launch_command(f"gtk-launch {desktop_entry}", APP_ENV_OVERRIDES.get(key))
    return None

def _generate_variants(app_name: str) -> List[str]:
    variants = {app_name.strip()}
    variants.add(app_name.replace(' ', ''))
    variants.add(app_name.replace(' ', '-'))
    variants.add(app_name.replace(' ', '_'))
    return [variant for variant in variants if variant]

def resolve_generic_application(app_name: str) -> Optional[str]:
    for variant in _generate_variants(app_name):
        parts = variant.split()
        executable = parts[0]
        if shutil.which(executable):
            return build_launch_command(variant)
    desktop_entry = find_desktop_entry(app_name)
    if desktop_entry and shutil.which('gtk-launch'):
        return build_launch_command(f"gtk-launch {desktop_entry}")
    return None

def extract_app_name_from_query(query_lower: str) -> Optional[str]:
    import re
    match = re.search(r'(?:open|launch|start|run)\s+([a-z0-9 ._+-]+)', query_lower)
    if not match:
        return None
    candidate = match.group(1)
    # Stop at connector words
    candidate = re.split(r'\b(?:please|now|for me|quickly|immediately)\b', candidate)[0]
    candidate = candidate.strip()
    candidate = candidate.rstrip(' .!,')
    if not candidate or '.' in candidate:
        return None  # Likely URL
    words = candidate.split()
    while words and words[0] in {'the', 'a', 'an', 'my'}:
        words.pop(0)
    candidate = " ".join(words).strip()
    return candidate or None

def detect_tool_intent(query: str) -> Optional[tuple[str, dict]]:
    """
    Detect if user query requires a tool based on keywords and patterns
    Returns (tool_name, parameters) or None
    """
    query_lower = query.lower().strip()
    import re
    
    # Google search with query (e.g., "open google and search for X", "search for X in google")
    google_patterns = [
        r'(?:open|go to|search)\s+(?:in\s+)?google\s+(?:and\s+)?(?:search\s+for\s+)(.+)',
        r'search\s+for\s+(.+?)\s+in\s+google',
        r'google\s+search\s+(.+)',
        r'google\s+(.+)',
    ]
    for pattern in google_patterns:
        match = re.search(pattern, query_lower)
        if match and 'google' in query_lower:
            search_query = match.group(1).strip()
            # Remove trailing noise
            search_query = re.sub(r'\s+on\s+google.*$', '', search_query)
            search_encoded = search_query.replace(' ', '+')
            return ('open_url', {'url': f'https://www.google.com/search?q={search_encoded}'})
    
    # YouTube with search query (e.g., "open kantha song in youtube", "play X on youtube")
    youtube_patterns = [
        r'(?:open|play|search|find)\s+(.+?)\s+(?:in|on)\s+youtube',
        r'youtube\s+(.+)',
        r'(?:open|play)\s+(.+?)\s+(?:youtube|yt)',
    ]
    for pattern in youtube_patterns:
        match = re.search(pattern, query_lower)
        if match and 'youtube' in query_lower:
            search_query = match.group(1).strip()
            # Remove "and play/watch" phrases completely
            search_query = re.sub(r'(^|\s+)and\s+(play|watch|see|show)(\s+|$)', ' ', search_query).strip()
            # Remove "youtube" and "yt" from query
            search_query = re.sub(r'\s+(in|on)\s+youtube.*$', '', search_query)
            search_query = re.sub(r'youtube\s+', '', search_query).strip()
            
            # Check if user wants autoplay
            wants_autoplay = any(word in query_lower for word in ['play', 'watch'])
            
            if wants_autoplay and BROWSER_AUTOMATION_AVAILABLE:
                # Use Selenium for autoplay (finds and clicks first non-sponsored video)
                return ('youtube_autoplay', {'search_query': search_query})
            else:
                # Just open search results
                search_encoded = search_query.replace(' ', '+')
                return ('open_url', {'url': f'https://www.youtube.com/results?search_query={search_encoded}'})
    
    action_present = any(word in query_lower for word in ACTION_VERBS)
    if action_present:
        matched = False
        for keyword, canonical in APP_KEYWORDS.items():
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, query_lower):
                matched = True
                launch_command = resolve_known_application(canonical)
                if launch_command:
                    logger.info(f"Resolved application '{keyword}' to command '{launch_command}'")
                    return ('run_command', {'command': launch_command})
        generic_app = extract_app_name_from_query(query_lower)
        if generic_app:
            launch_command = resolve_generic_application(generic_app)
            if launch_command:
                logger.info(f"Resolved generic application '{generic_app}' to command '{launch_command}'")
                return ('run_command', {'command': launch_command})
    
    # Regular URL (domain or full URL)
    if any(word in query_lower for word in ['open', 'launch', 'browse', 'go to', 'visit']):
        # Extract URL or domain
        url_match = re.search(r'(https?://[^\s]+|[\w-]+\.(?:com|org|net|io|co|in|edu|gov)(?:/[^\s]*)?)', query_lower)
        if url_match:
            url = url_match.group(0)
            if not url.startswith('http'):
                url = f'https://{url}'
            return ('open_url', {'url': url})
    
    # System status
    if any(phrase in query_lower for phrase in ['system status', 'cpu usage', 'ram', 'memory', 'disk space', 'check system']):
        return ('get_system_status', {})
    
    # Read file
    if 'read file' in query_lower or 'show file' in query_lower or 'cat file' in query_lower:
        # Extract filename
        file_match = re.search(r'(?:read|show|cat)\s+file\s+([^\s]+)', query_lower)
        if file_match:
            return ('read_file', {'file_path': file_match.group(1)})
    
    # Create/write file
    if 'create file' in query_lower or 'write file' in query_lower:
        # Extract: "create file X with Y"
        match = re.search(r'(?:create|write)\s+file\s+([^\s]+)\s+with\s+(.+)', query_lower)
        if match:
            return ('write_file', {'file_path': match.group(1), 'content': match.group(2)})
    
    # List directory commands (avoid matching "ls" inside other words like "vlsi")
    list_dir_phrases = ['list files', 'show files', 'list directory', 'list directories']
    if any(phrase in query_lower for phrase in list_dir_phrases):
        dir_match = re.search(r'(?:in|inside|under)\s+([\w./~-]+)', query_lower)
        directory = dir_match.group(1) if dir_match else '.'
        return ('list_directory', {'path': directory})
    ls_match = re.search(r'\bls\b(?:\s+(?P<target>[\w./~-]+))?', query_lower)
    if ls_match:
        directory = ls_match.group('target') or '.'
        return ('list_directory', {'path': directory})
    
    # Search files
    if 'search for' in query_lower and 'file' in query_lower:
        match = re.search(r'search for\s+(.+?)\s+file', query_lower)
        if match:
            pattern = match.group(1).strip()
            return ('search_files', {'pattern': f'*{pattern}*'})
    
    # Run command (explicit)
    if 'run command' in query_lower:
        match = re.search(r'run command\s+(.+)', query_lower)
        if match:
            return ('run_command', {'command': match.group(1)})
    
    return None

async def generate_response(
    user_query: str,
    session_id: Optional[str] = None,
    language: Optional[str] = None,
    enable_tools: bool = True
):
    """
    Generate intelligent response with tool routing, tool calling, and language support
    
    Args:
        user_query: User's question/command
        session_id: Session identifier for context
        language: Language code (auto-detect if None)
        enable_tools: Whether to enable tool calling (default: True)
    
    Yields text chunks suitable for streaming TTS
    """
    gen_start = time.time()
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
    logger.debug(f"[Timing] Session setup: {time.time() - gen_start:.3f}s")
    
    # Check if user is asking about history/previous commands
    if any(phrase in user_query.lower() for phrase in ['what did i', 'previous', 'earlier', 'before', 'history', 'recall', 'remember']):
        history = session.get_history()
        if history:
            history_text = "\n".join([f"{turn['role']}: {turn['content']}" for turn in history[-10:]])  # Last 10 turns
            tool_context = {
                "role": "user",
                "content": f"""The user asked: "{user_query}"

Here is the recent conversation history:
{history_text}

Provide a natural summary of what the user did or asked previously."""
            }
            messages = [
                {"role": "system", "content": "You are JARVIS. Summarize the conversation history naturally."},
                tool_context
            ]
            async for sentence in llm.generate_stream(messages, temperature=0.7, max_tokens=300):
                yield sentence
            return
    
    # Check for direct tool intent (pattern matching)
    if enable_tools:
        tool_check_start = time.time()
        tool_intent = detect_tool_intent(user_query)
        logger.debug(f"[Timing] Tool detection: {time.time() - tool_check_start:.3f}s")
        if tool_intent:
            tool_name, parameters = tool_intent
            logger.info(f"Detected tool intent: {tool_name} with params: {parameters}")
            
            # Special handling for youtube_autoplay using Selenium
            if tool_name == 'youtube_autoplay' and BROWSER_AUTOMATION_AVAILABLE:
                tool_result = await browser_tool.youtube_autoplay(parameters['search_query'])
                logger.info(f"YouTube autoplay result: {tool_result}")
            else:
                # Execute tool through tool_manager
                tool_result = await tool_manager.execute_tool(tool_name, parameters)
                logger.info(f"Tool result: {tool_result}")
            
            # Generate natural response with tool result
            tool_context = {
                "role": "user",
                "content": f"""The user asked: "{user_query}"

I executed the {tool_name} tool and got this result:
{json.dumps(tool_result, indent=2)}

Provide a natural, conversational response explaining what was done and the result. Be concise but helpful."""
            }
            
            messages = [
                {"role": "system", "content": "You are JARVIS. Explain tool results naturally and conversationally."},
                tool_context
            ]
            
            async for sentence in llm.generate_stream(messages, temperature=0.7, max_tokens=300):
                yield sentence
            
            return
    
    # Check if web search is needed
    search_context = None
    search_failure_note = None
    if needs_web_search(user_query) and settings.ENABLE_WEB_SEARCH:
        search_start = time.time()
        logger.info(f"Web search requested: {user_query[:50]}")
        try:
            search_result = await perplexity.search(user_query)
            logger.debug(f"[Timing] Web search: {time.time() - search_start:.3f}s")
            
            # Create context-aware prompt
            search_system_prompt = {
                "role": "system",
                "content": """You are JARVIS, a helpful AI assistant. Use the provided search results to answer accurately.

IMPORTANT: Format your response as continuous flowing paragraphs. Never use bullet points, lists, or numbered steps. Write everything as connected sentences for smooth, natural speech."""
            }
            search_user_prompt = {
                "role": "user",
                "content": f"""Search results for \"{user_query}\":

{search_result['answer']}

Sources: {', '.join(search_result.get('citations', [])[:3])}

Based on this information, provide a helpful answer."""
            }
            search_context = (search_system_prompt, search_user_prompt)
        except Exception as e:
            logger.error(f"Search error: {e}")
            search_failure_note = "Search failed. Answer based on your knowledge."

    if search_context is None:
        # Build conversation context with optional tool support
        base_system_content = """You are JARVIS, an advanced AI assistant. Be helpful, accurate, and conversational.

IMPORTANT: Format ALL responses as continuous flowing paragraphs. Never use:
- Bullet points or lists (•, -, *, numbers)
- Multiple separate points
- Step-by-step numbered instructions

Instead, write everything as connected sentences in paragraph form for smooth, natural speech flow. Explain concepts by weaving information together naturally, as if speaking to someone in conversation.

Be concise for simple queries, detailed for complex ones. Always maintain context from previous conversation."""
        if search_failure_note:
            base_system_content += f"\n\n{search_failure_note}"
        
        # Add tool descriptions if enabled
        if enable_tools:
            tools = [tool.to_dict() for tool in tool_manager.get_all_tools()]
            tool_prompt = llm.format_tools_for_prompt(tools)
            base_system_content += tool_prompt
        
        system_prompt = {
            "role": "system",
            "content": base_system_content
        }
    else:
        system_prompt = None  # Not used in search mode

    def build_messages():
        if search_context:
            system_msg, user_msg = search_context
            history = session.get_history(last_n=5)
            return [system_msg, *history, user_msg]
        # Limit history to avoid exceeding the model context window
        recent_history = session.get_history(last_n=settings.MAX_CONVERSATION_HISTORY)
        approx_char_limit = calculate_max_prompt_chars()
        trimmed_history = limit_history_for_context(recent_history, approx_char_limit)
        return [system_prompt] + trimmed_history
    
    messages = build_messages()
    
    # Stream LLM response with adaptive parameters
    full_response = ""
    attempt = 0
    max_attempts = 2
    logger.debug(f"[Timing] Pre-LLM setup: {time.time() - gen_start:.3f}s")
    while attempt < max_attempts:
        messages = build_messages()
        try:
            async for sentence in llm.generate_stream(
                messages,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=max_tokens,
                timeout=timeout
            ):
                full_response += sentence + " "
                yield sentence
            break
        except LLMContextExceededError as exc:
            attempt += 1
            logger.warning(f"LLM context exceeded (attempt {attempt}/{max_attempts}): {exc}")
            session.clear_history()
            session.add_turn("user", user_query)
            full_response = ""
            if attempt >= max_attempts:
                yield "I reset our conversation to keep things fast. Please ask again."
                return
            continue
    
    # Check if LLM wants to call a tool
    if enable_tools:
        logger.debug(f"Full LLM response for tool detection: {full_response}")
        tool_call = llm.extract_tool_call(full_response)
        
        if tool_call:
            logger.info(f"Tool call detected: {tool_call['tool']}")
            
            # Execute the tool
            tool_result = await tool_manager.execute_tool(
                tool_call['tool'],
                tool_call.get('parameters', {})
            )
            
            logger.info(f"Tool result: {tool_result}")
            
            # Add tool result to conversation and get final response
            tool_message = {
                "role": "assistant",
                "content": f"Tool executed. Result: {json.dumps(tool_result)}"
            }
            messages.append(tool_message)
            
            user_follow_up = {
                "role": "user",
                "content": "Based on this tool result, provide your final answer to my original question in a natural, conversational way."
            }
            messages.append(user_follow_up)
            
            # Get final response after tool execution
            final_response = ""
            async for sentence in llm.generate_stream(
                messages,
                temperature=settings.LLM_TEMPERATURE,
                max_tokens=max_tokens,
                timeout=timeout
            ):
                final_response += sentence + " "
                yield sentence
            
            # Add final response to history
            session.add_turn("assistant", final_response.strip())
            return
    
    # Add assistant response to history (if no tool was called)
    session.add_turn("assistant", full_response.strip())

# === API Endpoints ===

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "3.0.0-phase1",
        "services": {
            "whisper": "loaded",
            "piper": "loaded",
            "llm": "ready",
            "perplexity": "configured" if settings.ENABLE_WEB_SEARCH else "disabled",
            "tools": f"{len(tool_manager.get_all_tools())} tools available"
        }
    }

@app.post("/api/voice")
async def voice_interaction(audio: UploadFile = File(...)):
    """
    PRIMARY VOICE INTERFACE - Audio in, Audio out
    
    This is the main way to interact with JARVIS:
    1. Upload audio file (your voice question)
    2. JARVIS transcribes it (STT)
    3. JARVIS processes with LLM
    4. JARVIS responds with audio stream (TTS)
    
    Returns: Streaming audio (WAV format)
    """
    try:
        start_time = time.time()
        
        # Step 1: Transcribe audio
        audio_bytes = await audio.read()
        logger.info(f"Received audio: {len(audio_bytes)} bytes")
        
        # Transcribe with lower probability threshold for better detection
        transcription = whisper_stt.transcribe_audio(audio_bytes)
        user_text = transcription.get("text", "").strip()
        detected_lang = transcription.get("language", "en")
        confidence = transcription.get("probability", 0.0)
        
        logger.info(f"STT Result: text='{user_text}', lang={detected_lang}, confidence={confidence:.2f}")
        
        if not user_text:
            raise HTTPException(
                status_code=400, 
                detail=f"No speech detected (confidence: {confidence:.2f}). Please speak louder or closer to microphone."
            )
        
        logger.info(f"Transcribed ({detected_lang}): {user_text}")
        stt_time = time.time() - start_time
        
        # TRUE REAL-TIME: Stream STT → LLM → TTS → Audio
        async def audio_stream_generator():
            """Generate TRUE streaming: LLM generates → TTS converts → Audio plays IMMEDIATELY"""
            
            # Create WAV header once (with placeholder size for streaming)
            import struct
            sample_rate = 22050
            num_channels = 2
            bits_per_sample = 16
            byte_rate = sample_rate * num_channels * bits_per_sample // 8
            block_align = num_channels * bits_per_sample // 8
            
            # WAV header with max size (for streaming)
            header = struct.pack('<4sI4s', b'RIFF', 0x7FFFFFFF - 8, b'WAVE')
            header += struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, num_channels, sample_rate, byte_rate, block_align, bits_per_sample)
            header += struct.pack('<4sI', b'data', 0x7FFFFFFF)
            yield header
            warmup_duration = 0.05  # 50ms of silence to wake speakers immediately
            warmup_bytes = int(sample_rate * warmup_duration) * block_align
            if warmup_bytes:
                yield b'\x00' * warmup_bytes
                logger.debug("Sent warmup silence chunk to prime audio pipeline")
            
            logger.info("Streaming: LLM generating → TTS converting → Audio playing in real-time...")
            sentence_queue: asyncio.Queue = asyncio.Queue(maxsize=5)
            stop_token = object()
            
            async def sentence_producer():
                try:
                    async for sentence in generate_response(user_text, None, detected_lang):
                        await sentence_queue.put(sentence)
                finally:
                    await sentence_queue.put(stop_token)
            
            producer_task = asyncio.create_task(sentence_producer())
            sentence_count = 0
            first_chunk_logged = False
            try:
                while True:
                    sentence = await sentence_queue.get()
                    if sentence is stop_token:
                        sentence_queue.task_done()
                        break
                    sentence_count += 1
                    logger.debug(f"Sentence {sentence_count}: {sentence[:60]}... → TTS")
                    async for audio_chunk in piper_tts.synthesize_stream_async(
                        sentence, detected_lang, raw_pcm=True
                    ):
                        if audio_chunk and not first_chunk_logged:
                            first_chunk_logged = True
                            logger.info(
                                f"First audio chunk sent {time.time() - start_time:.2f}s after user request"
                            )
                        yield audio_chunk
                    sentence_queue.task_done()
                total_time = time.time() - start_time
                logger.info(
                    f"Voice interaction complete: STT={stt_time:.2f}s, {sentence_count} sentences, Total={total_time:.2f}s"
                )
            finally:
                if not producer_task.done():
                    producer_task.cancel()
                with suppress(asyncio.CancelledError):
                    await producer_task
        
        return StreamingResponse(
            audio_stream_generator(),
            media_type="audio/wav",
            headers={
                "X-Transcription": user_text[:200],
                "X-Language": detected_lang,
                "X-Processing-Time": f"{time.time() - start_time:.2f}s"
            }
        )
        
    except Exception as e:
        logger.error(f"Voice interaction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/voice/text")
async def voice_text_input(request: dict):
    """
    TEXT INPUT → VOICE OUTPUT (Streaming Audio)
    For testing without microphone: Type question, get voice response
    
    Input: {"text": "your question"}
    Returns: Streaming audio (WAV format) with <2s latency
    """
    try:
        start_time = time.time()
        user_text = request.get("text", "").strip()
        
        if not user_text:
            raise HTTPException(status_code=400, detail="No text provided")
        
        logger.info(f"Text-to-voice query: {user_text}")
        logger.debug(f"[Timing] Endpoint entry: 0.000s")
        
        # Auto-detect language (for future multi-language support)
        detected_lang = "en"  # Default to English for now
        
        # TRUE REAL-TIME: Stream LLM → TTS → Audio as sentences are generated!
        async def audio_stream_generator():
            """Generate TRUE streaming: LLM sentences queue up while TTS streams audio"""
            logger.debug(f"[Timing] Generator started: {time.time() - start_time:.3f}s")
            import struct
            sample_rate = 22050
            num_channels = 2
            bits_per_sample = 16
            byte_rate = sample_rate * num_channels * bits_per_sample // 8
            block_align = num_channels * bits_per_sample // 8
            
            header = struct.pack('<4sI4s', b'RIFF', 0x7FFFFFFF - 8, b'WAVE')
            header += struct.pack('<4sIHHIIHH', b'fmt ', 16, 1, num_channels, sample_rate, byte_rate, block_align, bits_per_sample)
            header += struct.pack('<4sI', b'data', 0x7FFFFFFF)
            yield header
            warmup_duration = 0.05
            warmup_bytes = int(sample_rate * warmup_duration) * block_align
            if warmup_bytes:
                yield b'\x00' * warmup_bytes
                logger.debug("Sent warmup silence chunk to prime audio pipeline")
            
            logger.info("Streaming: LLM generating → TTS converting → Audio playing in real-time...")
            sentence_queue: asyncio.Queue = asyncio.Queue(maxsize=5)
            stop_token = object()
            text_session_id = request.get("session_id", "text-to-voice-session")
            
            async def sentence_producer():
                try:
                    async for sentence in generate_response(user_text, text_session_id, detected_lang):
                        await sentence_queue.put(sentence)
                finally:
                    await sentence_queue.put(stop_token)
            
            producer_task = asyncio.create_task(sentence_producer())
            sentence_count = 0
            first_chunk_logged = False
            try:
                while True:
                    sentence = await sentence_queue.get()
                    if sentence is stop_token:
                        sentence_queue.task_done()
                        break
                    sentence_count += 1
                    logger.debug(f"Sentence {sentence_count}: {sentence[:60]}... → TTS")
                    async for audio_chunk in piper_tts.synthesize_stream_async(
                        sentence, detected_lang, raw_pcm=True
                    ):
                        if audio_chunk and not first_chunk_logged:
                            first_chunk_logged = True
                            logger.info(
                                f"First audio chunk sent {time.time() - start_time:.2f}s after request"
                            )
                        yield audio_chunk
                    sentence_queue.task_done()
                total_time = time.time() - start_time
                logger.info(f"Text-to-voice complete: {sentence_count} sentences, Total={total_time:.2f}s")
            finally:
                if not producer_task.done():
                    producer_task.cancel()
                with suppress(asyncio.CancelledError):
                    await producer_task
        
        return StreamingResponse(
            audio_stream_generator(),
            media_type="audio/wav",
            headers={
                "X-Language": detected_lang,
                "X-Stream-Type": "real-time-sentence-streaming",
                "Cache-Control": "no-cache"
            }
        )
        
    except Exception as e:
        logger.error(f"Text-to-voice error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
            warmup_duration = 0.05
            warmup_bytes = int(sample_rate * warmup_duration) * block_align
            if warmup_bytes:
                yield b'\x00' * warmup_bytes
                logger.debug("Sent warmup silence chunk to prime audio pipeline")
            logger.info("WAV header sent, starting sentence-by-sentence synthesis...")
            
            sentence_queue: asyncio.Queue = asyncio.Queue(maxsize=5)
            stop_token = object()
            
            async def sentence_producer():
                try:
                    async for sentence in generate_response(request.text, request.session_id, detected_lang):
                        await sentence_queue.put(sentence)
                finally:
                    await sentence_queue.put(stop_token)
            
            producer_task = asyncio.create_task(sentence_producer())
            sentence_count = 0
            try:
                while True:
                    sentence = await sentence_queue.get()
                    if sentence is stop_token:
                        sentence_queue.task_done()
                        break
                    sentence_count += 1
                    logger.info(f"Sentence {sentence_count}: {sentence[:60]}...")
                    async for audio_chunk in piper_tts.synthesize_stream_async(sentence, detected_lang, raw_pcm=True):
                        yield audio_chunk
                    logger.debug(f"Sentence {sentence_count} audio streamed")
                    sentence_queue.task_done()
                logger.info(f"Streaming complete: {sentence_count} sentences")
            finally:
                if not producer_task.done():
                    producer_task.cancel()
                with suppress(asyncio.CancelledError):
                    await producer_task
                    
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
