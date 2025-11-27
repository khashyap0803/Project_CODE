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

# Try to import system control
try:
    from tools.system_control import system_control
    SYSTEM_CONTROL_AVAILABLE = True
    logger.info("System control available")
except Exception as e:
    system_control = None
    SYSTEM_CONTROL_AVAILABLE = False
    logger.warning(f"System control not available: {e}")

# Default session ID for persistent memory across requests
DEFAULT_SESSION_ID = "jarvis-default-session"

# LLM-based intent classification prompt
# NOTE: Double braces {{ }} are escaped braces for .format()
INTENT_CLASSIFICATION_PROMPT = """You are an intent classifier for a voice assistant. Analyze the user's query and classify it into one of these categories.

CATEGORIES:
1. TIME_DATE - asking for time, date, day, datetime (e.g., "whats the time", "tell me today's date", "wat day is it")
2. TIMER - setting/canceling timers (e.g., "set 5 sec timer", "timer for 10 minutes", "cancel timer")
3. ALARM - setting/canceling alarms (e.g., "set alarm for 7am", "wake me up at 8", "cancel alarm")
4. REMINDER - setting reminders (e.g., "remind me to call mom in 5 minutes", "reminder after 10 sec to drink water")
5. STOPWATCH - stopwatch controls (e.g., "start stopwatch", "stop the stopwatch", "how long has stopwatch been running")
6. VOLUME - volume controls (e.g., "volume up", "mute", "set volume to 50")
7. BRIGHTNESS - brightness controls (e.g., "increase brightness", "dim screen")
8. LOCK_SCREEN - lock the screen (e.g., "lock screen", "lock my pc", "lock computer")
9. SCREENSHOT - take screenshot (e.g., "take screenshot", "capture screen")
10. YOUTUBE_PLAY - play something on YouTube (e.g., "play X on youtube", "youtube X song")
11. YOUTUBE_CONTROL - control YouTube playback (e.g., "pause video", "next song", "previous video", "resume")
12. BROWSER_CONTROL - browser operations (e.g., "open browser", "close browser", "new tab", "go to X.com")
13. OPEN_APP - open an application (e.g., "open calculator", "launch firefox", "start vscode")
14. CLOSE_APP - close an application (e.g., "close calculator", "exit firefox")
15. WINDOW_CONTROL - window management (e.g., "maximize calculator", "minimize firefox", "focus vscode")
16. SYSTEM_INFO - system status queries (e.g., "cpu usage", "check memory", "disk space", "battery status")
17. CONVERSATION - general conversation/questions (e.g., "who are you", "tell me a joke", "explain quantum physics")
18. WEB_SEARCH - needs web search (e.g., "latest news about X", "current weather", "who won the election")

Respond with ONLY a JSON object in this exact format:
{{"category": "CATEGORY_NAME", "params": {{"key": "value"}}}}

For params, extract relevant information:
- TIME_DATE: {{"type": "time|date|datetime"}}
- TIMER: {{"seconds": 300, "action": "set|cancel|list"}}
- ALARM: {{"hour": 7, "minute": 0, "action": "set|cancel|list"}}
- REMINDER: {{"message": "call mom", "seconds": 300}}
- STOPWATCH: {{"action": "start|stop|reset|get"}}
- VOLUME: {{"action": "up|down|mute|unmute|set", "level": 50}}
- BRIGHTNESS: {{"action": "up|down|set", "level": 50}}
- YOUTUBE_PLAY: {{"query": "search term"}}
- YOUTUBE_CONTROL: {{"action": "play|pause|next|previous|mute|unmute|fullscreen"}}
- BROWSER_CONTROL: {{"action": "open|close|new_tab|goto", "url": "optional"}}
- OPEN_APP: {{"app": "application name"}}
- CLOSE_APP: {{"app": "application name"}}
- WINDOW_CONTROL: {{"action": "maximize|minimize|focus", "app": "application name"}}
- SYSTEM_INFO: {{"type": "cpu|memory|gpu|battery|disk|network|all"}}
- CONVERSATION: {{}}
- WEB_SEARCH: {{}}

User query: "{query}"
"""

# Multi-command classification prompt for sequential/chained commands
MULTI_COMMAND_CLASSIFICATION_PROMPT = """You are a command parser for a voice assistant. The user may give MULTIPLE commands in a single sentence.

Your job is to:
1. Detect if there are multiple commands
2. Extract each command with any timing/delay information
3. Return them in execution order

TIMING KEYWORDS to watch for:
- "after X seconds/minutes" - delay before this command
- "then" - execute next command after previous completes
- "and" - can mean simultaneous or sequential
- "wait X seconds" - explicit delay
- "in X seconds/minutes" - delay before command

CATEGORIES with param examples:
1. TIME_DATE - time/date queries: {{"type": "time"}} or {{"type": "date"}} or {{"type": "datetime"}}
2. TIMER - set timers: {{"action": "set", "seconds": 60}}
3. ALARM - set alarms: {{"action": "set", "hour": 8, "minute": 0}}
4. REMINDER - set reminders: {{"message": "call mom", "seconds": 300}}
5. STOPWATCH - control: {{"action": "start|stop|reset|get"}}
6. VOLUME - volume control: {{"action": "up|down|mute|set", "level": 50}}
7. BRIGHTNESS - screen brightness: {{"action": "up|down|set", "level": 50}}
8. LOCK_SCREEN - lock computer: {{}}
9. SCREENSHOT - take screenshot: {{}}
10. YOUTUBE_PLAY - play on youtube: {{"query": "song name"}}
11. YOUTUBE_CONTROL - media control: {{"action": "pause|play|next|previous"}}
12. BROWSER_CONTROL - browser: {{"action": "open|close|goto", "url": "optional"}}
13. OPEN_APP - open app: {{"app": "calculator"}}
14. CLOSE_APP - close app: {{"app": "firefox"}}
15. WINDOW_CONTROL - window: {{"action": "maximize|minimize|focus", "app": "calculator"}}
16. SYSTEM_INFO - system status (CPU, memory, disk, gpu, battery): {{"type": "cpu|memory|disk|gpu|battery|all"}}
17. CONVERSATION - general chat: {{}}
18. WEB_SEARCH - needs internet: {{}}

IMPORTANT DISTINCTIONS:
- "what time is it" → TIME_DATE with type="time" (NOT SYSTEM_INFO)
- "what date is today" → TIME_DATE with type="date" (NOT SYSTEM_INFO)
- "check cpu usage" → SYSTEM_INFO with type="cpu"
- "check memory" → SYSTEM_INFO with type="memory"

Respond with ONLY a JSON object:
{{
  "is_multi_command": true/false,
  "commands": [
    {{
      "order": 1,
      "delay_seconds": 0,
      "category": "CATEGORY_NAME",
      "params": {{}},
      "original_text": "the part of query for this command"
    }}
  ]
}}

EXAMPLES:
- "what time is it and what is the date" → 2 commands: TIME_DATE(type=time), TIME_DATE(type=date)
- "open calculator and after 5 seconds maximize it" → 2 commands: OPEN_APP(calculator), then 5sec delay, WINDOW_CONTROL(maximize, calculator)
- "play kaantha song after 10 seconds" → is_multi_command=false (single command with delay handled differently)
- "set volume to 50 and open firefox" → 2 commands: VOLUME(set 50), OPEN_APP(firefox)
- "what time is it" → is_multi_command=false (single command)

User query: "{query}"
"""

async def llm_classify_intent(query: str) -> Optional[tuple[str, dict]]:
    """
    Use LLM to classify user intent when pattern matching is uncertain.
    Returns (tool_name, parameters) or None for conversation.
    """
    import aiohttp
    import json
    
    logger.debug(f"LLM intent classification starting for: {query[:50]}")
    
    try:
        prompt = INTENT_CLASSIFICATION_PROMPT.format(query=query)
        
        payload = {
            "model": settings.LLM_MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,  # Low temperature for consistent classification
            "max_tokens": 150,
            "stream": False
        }
        
        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                settings.LLM_API_URL,  # Already includes /v1/chat/completions
                json=payload,
                timeout=aiohttp.ClientTimeout(total=5)  # 5 second timeout
            ) as response:
                if response.status != 200:
                    logger.warning(f"LLM intent classification failed: {response.status}")
                    return None
                
                result = await response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                logger.debug(f"LLM intent raw response: {content[:300]}")
                
                # Parse JSON response - handle nested braces
                data = None
                try:
                    # Method 1: Find balanced braces
                    start_idx = content.find('{')
                    if start_idx >= 0:
                        brace_count = 0
                        end_idx = start_idx
                        for i, c in enumerate(content[start_idx:], start_idx):
                            if c == '{':
                                brace_count += 1
                            elif c == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    end_idx = i + 1
                                    break
                        json_str = content[start_idx:end_idx]
                        logger.debug(f"Extracted JSON: {json_str}")
                        data = json.loads(json_str)
                    else:
                        logger.debug(f"No JSON found in LLM response")
                        return None
                except json.JSONDecodeError as e:
                    logger.debug(f"JSON parse error: {e}")
                    return None
                
                if data is None or not isinstance(data, dict):
                    logger.debug(f"Invalid data type: {type(data)}")
                    return None
                
                category = data.get("category", "")
                if not category:
                    logger.debug(f"No category in data: {data}")
                    return None
                    
                category = category.upper()
                params = data.get("params", {})
                
                logger.info(f"LLM classified intent: {category} with params: {params}")
                
                # Map categories to tool names and parameters
                if category == "TIME_DATE":
                    time_type = params.get("type", "time")
                    if time_type == "date":
                        return ("system_control", {"action": "get_date"})
                    elif time_type == "datetime":
                        return ("system_control", {"action": "get_datetime"})
                    else:
                        return ("system_control", {"action": "get_time"})
                
                elif category == "TIMER":
                    action = params.get("action", "set")
                    if action == "set":
                        return ("system_control", {"action": "set_timer", "seconds": params.get("seconds", 60)})
                    elif action == "cancel":
                        return ("system_control", {"action": "cancel_timer"})
                    else:
                        return ("system_control", {"action": "list_timers"})
                
                elif category == "ALARM":
                    action = params.get("action", "set")
                    if action == "set":
                        return ("system_control", {"action": "set_alarm", "hour": params.get("hour", 8), "minute": params.get("minute", 0)})
                    elif action == "cancel":
                        return ("system_control", {"action": "cancel_alarm"})
                    else:
                        return ("system_control", {"action": "list_alarms"})
                
                elif category == "REMINDER":
                    return ("system_control", {"action": "set_reminder", "message": params.get("message", "Reminder"), "seconds": params.get("seconds", 60)})
                
                elif category == "STOPWATCH":
                    action = params.get("action", "start")
                    return ("system_control", {"action": f"{action}_stopwatch"})
                
                elif category == "VOLUME":
                    action = params.get("action", "up")
                    if action == "set":
                        return ("system_control", {"action": "volume_set", "level": params.get("level", 50)})
                    elif action in ["up", "down"]:
                        return ("system_control", {"action": f"volume_{action}"})
                    else:
                        return ("system_control", {"action": action})
                
                elif category == "BRIGHTNESS":
                    action = params.get("action", "up")
                    if action == "set":
                        return ("system_control", {"action": "brightness_set", "level": params.get("level", 50)})
                    else:
                        return ("system_control", {"action": f"brightness_{action}"})
                
                elif category == "LOCK_SCREEN":
                    return ("system_control", {"action": "lock"})
                
                elif category == "SCREENSHOT":
                    return ("system_control", {"action": "screenshot"})
                
                elif category == "YOUTUBE_PLAY":
                    search_query = params.get("query", "")
                    if search_query and BROWSER_AUTOMATION_AVAILABLE:
                        return ("youtube_autoplay", {"search_query": search_query})
                    return None
                
                elif category == "YOUTUBE_CONTROL":
                    action = params.get("action", "play")
                    if BROWSER_AUTOMATION_AVAILABLE:
                        return ("youtube_control", {"action": action})
                    return None
                
                elif category == "BROWSER_CONTROL":
                    action = params.get("action", "open")
                    url = params.get("url")
                    if BROWSER_AUTOMATION_AVAILABLE:
                        return ("browser_control", {"action": action, "url": url})
                    return None
                
                elif category == "OPEN_APP":
                    app = params.get("app", "")
                    if app:
                        launch_cmd = resolve_known_application(app) or resolve_generic_application(app)
                        if launch_cmd:
                            return ("run_command", {"command": launch_cmd})
                    return None
                
                elif category == "CLOSE_APP":
                    app = params.get("app", "")
                    if app:
                        return ("system_control", {"action": "close_app", "app_name": app})
                    return None
                
                elif category == "WINDOW_CONTROL":
                    action = params.get("action", "maximize")
                    app = params.get("app", "")
                    if app:
                        return ("system_control", {"action": f"{action}_window", "app_name": app})
                    return None
                
                elif category == "SYSTEM_INFO":
                    info_type = params.get("type", "all")
                    if info_type == "cpu":
                        return ("system_control", {"action": "get_cpu_usage"})
                    elif info_type == "memory":
                        return ("system_control", {"action": "get_memory_usage"})
                    elif info_type == "gpu":
                        return ("system_control", {"action": "get_gpu_status"})
                    elif info_type == "battery":
                        return ("system_control", {"action": "get_battery"})
                    elif info_type == "disk":
                        return ("system_control", {"action": "get_disk_usage"})
                    elif info_type == "network":
                        return ("system_control", {"action": "get_network_info"})
                    else:
                        return ("system_control", {"action": "get_system_info"})
                
                elif category == "WEB_SEARCH":
                    return None  # Let it fall through to web search handling
                
                # CONVERSATION or unknown - return None to let LLM handle it
                return None
                
    except asyncio.TimeoutError:
        logger.warning("LLM intent classification timed out")
        return None
    except KeyError as e:
        logger.warning(f"LLM intent classification KeyError: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"LLM intent classification JSON error: {e}")
        return None
    except Exception as e:
        logger.warning(f"LLM intent classification error ({type(e).__name__}): {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return None


def is_multi_command_query(query: str) -> bool:
    """
    Quick check if a query might contain multiple commands.
    Uses simple pattern matching before calling the LLM.
    """
    query_lower = query.lower()
    
    # Multi-command indicators
    multi_indicators = [
        ' and ',           # "open X and then Y"
        ' then ',          # "do X then Y"
        ' after ',         # "do X after 5 seconds"
        ' wait ',          # "do X wait 3 sec do Y"
        ' in ',            # "play X in 10 seconds" (but avoid "play X in youtube")
        ' followed by ',   # "X followed by Y"
        ', then',          # "open X, then Y"
    ]
    
    # Check for timing patterns that suggest delays
    import re
    timing_patterns = [
        r'after\s+\d+\s*(sec|second|min|minute)',
        r'in\s+\d+\s*(sec|second|min|minute)',
        r'wait\s+\d+\s*(sec|second|min|minute)',
        r'\d+\s*(sec|second|min|minute)\s+later',
    ]
    
    for indicator in multi_indicators:
        if indicator in query_lower:
            # Exclude "in youtube", "in browser" etc.
            if indicator == ' in ' and any(x in query_lower for x in ['in youtube', 'in browser', 'in firefox', 'in chrome']):
                continue
            return True
    
    for pattern in timing_patterns:
        if re.search(pattern, query_lower):
            return True
    
    return False


async def llm_parse_multi_command(query: str) -> Optional[list[dict]]:
    """
    Use LLM to parse multiple commands from a single query.
    Returns list of command dicts with order, delay, category, and params.
    """
    import aiohttp
    
    logger.info(f"Multi-command parsing for: {query}")
    
    try:
        prompt = MULTI_COMMAND_CLASSIFICATION_PROMPT.format(query=query)
        
        payload = {
            "model": settings.LLM_MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 500,
            "stream": False
        }
        
        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(
                settings.LLM_API_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=8)
            ) as response:
                if response.status != 200:
                    logger.warning(f"Multi-command parsing failed: {response.status}")
                    return None
                
                result = await response.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                logger.debug(f"Multi-command raw response: {content[:500]}")
                
                # Parse JSON response
                data = None
                try:
                    start_idx = content.find('{')
                    if start_idx >= 0:
                        brace_count = 0
                        end_idx = start_idx
                        for i, c in enumerate(content[start_idx:], start_idx):
                            if c == '{':
                                brace_count += 1
                            elif c == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    end_idx = i + 1
                                    break
                        json_str = content[start_idx:end_idx]
                        data = json.loads(json_str)
                except json.JSONDecodeError as e:
                    logger.warning(f"Multi-command JSON parse error: {e}")
                    return None
                
                if not data or not isinstance(data, dict):
                    return None
                
                is_multi = data.get("is_multi_command", False)
                commands = data.get("commands", [])
                
                if not is_multi or not commands or len(commands) < 1:
                    logger.debug("Not a multi-command query or no commands parsed")
                    return None
                
                logger.info(f"Parsed {len(commands)} commands from query")
                return commands
                
    except asyncio.TimeoutError:
        logger.warning("Multi-command parsing timed out")
        return None
    except Exception as e:
        logger.warning(f"Multi-command parsing error: {e}")
        return None


def map_category_to_tool(category: str, params: dict) -> Optional[tuple[str, dict]]:
    """
    Map a category name and params to tool_name and parameters.
    This is a helper to reuse the mapping logic for multi-commands.
    """
    category = category.upper()
    
    if category == "TIME_DATE":
        time_type = params.get("type", "time")
        if time_type == "date":
            return ("system_control", {"action": "get_date"})
        elif time_type == "datetime":
            return ("system_control", {"action": "get_datetime"})
        else:
            return ("system_control", {"action": "get_time"})
    
    elif category == "TIMER":
        action = params.get("action", "set")
        if action == "set":
            return ("system_control", {"action": "set_timer", "seconds": params.get("seconds", 60)})
        elif action == "cancel":
            return ("system_control", {"action": "cancel_timer"})
        else:
            return ("system_control", {"action": "list_timers"})
    
    elif category == "ALARM":
        action = params.get("action", "set")
        if action == "set":
            return ("system_control", {"action": "set_alarm", "hour": params.get("hour", 8), "minute": params.get("minute", 0)})
        elif action == "cancel":
            return ("system_control", {"action": "cancel_alarm"})
        else:
            return ("system_control", {"action": "list_alarms"})
    
    elif category == "REMINDER":
        return ("system_control", {"action": "set_reminder", "message": params.get("message", "Reminder"), "seconds": params.get("seconds", 60)})
    
    elif category == "STOPWATCH":
        action = params.get("action", "start")
        return ("system_control", {"action": f"{action}_stopwatch"})
    
    elif category == "VOLUME":
        action = params.get("action", "up")
        if action == "set":
            return ("system_control", {"action": "volume_set", "level": params.get("level", 50)})
        elif action in ["up", "down"]:
            return ("system_control", {"action": f"volume_{action}"})
        else:
            return ("system_control", {"action": action})
    
    elif category == "BRIGHTNESS":
        action = params.get("action", "up")
        if action == "set":
            return ("system_control", {"action": "brightness_set", "level": params.get("level", 50)})
        else:
            return ("system_control", {"action": f"brightness_{action}"})
    
    elif category == "LOCK_SCREEN":
        return ("system_control", {"action": "lock"})
    
    elif category == "SCREENSHOT":
        return ("system_control", {"action": "screenshot"})
    
    elif category == "YOUTUBE_PLAY":
        search_query = params.get("query", "")
        if search_query and BROWSER_AUTOMATION_AVAILABLE:
            return ("youtube_autoplay", {"search_query": search_query})
        return None
    
    elif category == "YOUTUBE_CONTROL":
        action = params.get("action", "play")
        if BROWSER_AUTOMATION_AVAILABLE:
            return ("youtube_control", {"action": action})
        return None
    
    elif category == "BROWSER_CONTROL":
        action = params.get("action", "open")
        url = params.get("url")
        if BROWSER_AUTOMATION_AVAILABLE:
            return ("browser_control", {"action": action, "url": url})
        return None
    
    elif category == "OPEN_APP":
        # Handle both "app" and "app_name" variants from LLM
        app = params.get("app", "") or params.get("app_name", "")
        if app:
            launch_cmd = resolve_known_application(app) or resolve_generic_application(app)
            if launch_cmd:
                return ("run_command", {"command": launch_cmd})
        return None
    
    elif category == "CLOSE_APP":
        # Handle both "app" and "app_name" variants from LLM
        app = params.get("app", "") or params.get("app_name", "")
        if app:
            return ("system_control", {"action": "close_app", "app_name": app})
        return None
    
    elif category == "WINDOW_CONTROL":
        action = params.get("action", "maximize")
        # Handle both "app" and "app_name" variants from LLM
        app = params.get("app", "") or params.get("app_name", "")
        if app:
            return ("system_control", {"action": f"{action}_window", "app_name": app})
        return None
    
    elif category == "SYSTEM_INFO":
        info_type = params.get("type", "all")
        if info_type == "cpu":
            return ("system_control", {"action": "get_cpu_usage"})
        elif info_type == "memory":
            return ("system_control", {"action": "get_memory_usage"})
        elif info_type == "gpu":
            return ("system_control", {"action": "get_gpu_status"})
        elif info_type == "battery":
            return ("system_control", {"action": "get_battery"})
        elif info_type == "disk":
            return ("system_control", {"action": "get_disk_usage"})
        elif info_type == "network":
            return ("system_control", {"action": "get_network_info"})
        else:
            return ("system_control", {"action": "get_system_info"})
    
    return None


async def execute_single_command(tool_name: str, parameters: dict) -> dict:
    """
    Execute a single command and return the result.
    This is a helper for multi-command execution.
    """
    tool_result = None
    
    try:
        if tool_name == 'youtube_autoplay' and BROWSER_AUTOMATION_AVAILABLE:
            tool_result = await browser_tool.youtube_autoplay(parameters.get('search_query', ''))
        elif tool_name == 'youtube_control' and BROWSER_AUTOMATION_AVAILABLE:
            tool_result = await browser_tool.youtube_control(parameters.get('action', 'play'))
        elif tool_name == 'browser_control' and BROWSER_AUTOMATION_AVAILABLE:
            tool_result = await browser_tool.browser_control(
                parameters.get('action', 'open'),
                parameters.get('url')
            )
        elif tool_name == 'system_control' and SYSTEM_CONTROL_AVAILABLE:
            tool_result = system_control.execute_control(
                parameters.get('action', ''),
                **{k: v for k, v in parameters.items() if k != 'action'}
            )
        elif tool_name == 'run_command':
            tool_result = run_command(parameters.get('command', ''))
        else:
            tool_result = await tool_manager.execute_tool(tool_name, parameters)
        
        return tool_result or {"success": False, "message": "No result"}
    except Exception as e:
        logger.error(f"Command execution error: {e}")
        return {"success": False, "message": str(e)}


async def execute_multi_commands(commands: list[dict]):
    """
    Execute multiple commands sequentially with delays.
    Yields status messages as execution progresses.
    """
    total_commands = len(commands)
    results = []
    
    # Sort commands by order
    sorted_commands = sorted(commands, key=lambda x: x.get("order", 1))
    
    # Track info results to combine at end
    info_results = []
    
    for i, cmd in enumerate(sorted_commands):
        order = cmd.get("order", i + 1)
        delay = cmd.get("delay_seconds", 0)
        category = cmd.get("category", "")
        params = cmd.get("params", {})
        original_text = cmd.get("original_text", "")
        
        # Apply delay if specified
        if delay > 0:
            logger.info(f"Waiting {delay} seconds before command {order}")
            yield f"Waiting {delay} seconds..."
            await asyncio.sleep(delay)
        
        # Map category to tool
        tool_info = map_category_to_tool(category, params)
        
        if tool_info:
            tool_name, tool_params = tool_info
            logger.info(f"Executing command {order}/{total_commands}: {tool_name} with {tool_params}")
            
            # Execute the command
            result = await execute_single_command(tool_name, tool_params)
            results.append({
                "order": order,
                "category": category,
                "success": result.get("success", False),
                "message": result.get("message", "")
            })
            
            # Check if this is an info query vs action command
            info_categories = ['TIME_DATE', 'SYSTEM_INFO']
            info_actions = ['get_time', 'get_date', 'get_datetime', 'get_cpu_usage', 
                           'get_memory_usage', 'get_gpu_status', 'get_battery', 
                           'get_disk_usage', 'get_network_info', 'get_system_info',
                           'list_timers', 'list_alarms', 'get_stopwatch', 'stop_stopwatch']
            
            is_info_query = (category.upper() in info_categories or 
                            tool_params.get('action', '') in info_actions)
            
            # Yield appropriate status
            if result.get("success"):
                status = result.get("message", "Done")
                if is_info_query:
                    # For info queries, include the result in the response
                    info_results.append(status)
                    yield status
                else:
                    # For action commands, keep brief
                    if len(status) > 50:
                        status = "Done"
                    yield status
            else:
                yield f"Failed: {result.get('message', 'Unknown error')}"
        else:
            logger.warning(f"Could not map category {category} to tool")
            results.append({
                "order": order,
                "category": category,
                "success": False,
                "message": f"Unknown category: {category}"
            })
            yield f"Skipped unknown command: {original_text}"
    
    # Final summary
    successful = sum(1 for r in results if r.get("success"))
    if successful == total_commands:
        yield f"All {total_commands} commands completed."
    else:
        yield f"Completed {successful}/{total_commands} commands."

# Initialize FastAPI app
app = FastAPI(
    title="JARVIS Voice Assistant",
    description="Advanced AI voice assistant with streaming support",
    version="3.0.0"
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
    
    # === Browser Controls (check BEFORE generic app launch) ===
    if BROWSER_AUTOMATION_AVAILABLE:
        # Browser open/close controls
        if any(phrase in query_lower for phrase in ['open browser', 'open the browser', 'launch browser', 'start browser']):
            return ('browser_control', {'action': 'open_browser'})
        if any(phrase in query_lower for phrase in ['close browser', 'close the browser', 'exit browser', 'quit browser']):
            return ('browser_control', {'action': 'close_browser'})
        if any(phrase in query_lower for phrase in ['new tab', 'open new tab', 'open a new tab', 'open tab']):
            return ('browser_control', {'action': 'new_tab'})
        if any(phrase in query_lower for phrase in ['close tab', 'close this tab', 'close the tab']):
            return ('browser_control', {'action': 'close_tab'})
    
    if action_present:
        matched = False
        # Skip browser keyword if browser automation is handling it
        for keyword, canonical in APP_KEYWORDS.items():
            # Don't match 'browser' if browser automation is available
            if keyword == 'browser' and BROWSER_AUTOMATION_AVAILABLE:
                continue
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
    
    # === YouTube Media Controls ===
    if BROWSER_AUTOMATION_AVAILABLE:
        # Pause video - check if just "pause" with no other context
        if query_lower.strip() == 'pause' or any(phrase in query_lower for phrase in ['pause the video', 'pause video', 'pause the song', 'pause song', 'pause youtube', 'pause it', 'pause playback', 'stop the video', 'stop video', 'stop playing', 'pause the music', 'pause music']):
            return ('youtube_control', {'action': 'pause'})
        
        # Next video - check BEFORE play to avoid conflict
        if any(phrase in query_lower for phrase in ['next video', 'next song', 'skip video', 'skip song', 'play next']):
            return ('youtube_control', {'action': 'next'})
        
        # Previous video - check BEFORE play to avoid conflict with "play previous video"
        if any(phrase in query_lower for phrase in ['previous video', 'previous song', 'go back video', 'play previous', 'last video', 'last song']):
            return ('youtube_control', {'action': 'previous'})
        
        # Play/Resume video - check if just "play" or "resume" with no other context
        if query_lower.strip() in ['play', 'resume'] or any(phrase in query_lower for phrase in ['play the video', 'play video', 'resume the video', 'resume video', 'resume playback', 'continue playing', 'play it', 'resume playing', 'unpause', 'unpause video', 'start playing again']):
            if 'youtube' not in query_lower or 'in youtube' not in query_lower:
                return ('youtube_control', {'action': 'play'})
        
        # Mute/Unmute (for video/youtube only)
        if 'mute' in query_lower and 'unmute' not in query_lower:
            if any(phrase in query_lower for phrase in ['mute video', 'mute the video', 'mute youtube', 'mute it']):
                return ('youtube_control', {'action': 'mute'})
        if 'unmute' in query_lower and ('video' in query_lower or 'youtube' in query_lower or query_lower.strip() == 'unmute'):
            return ('youtube_control', {'action': 'unmute'})
        
        # Volume controls for video
        if 'video volume' in query_lower or 'youtube volume' in query_lower:
            if 'up' in query_lower or 'increase' in query_lower:
                return ('youtube_control', {'action': 'volume_up'})
            if 'down' in query_lower or 'decrease' in query_lower:
                return ('youtube_control', {'action': 'volume_down'})
        
        # Fullscreen
        if any(phrase in query_lower for phrase in ['fullscreen', 'full screen', 'maximize video']):
            return ('youtube_control', {'action': 'fullscreen'})
        
        # Skip forward/backward
        if any(phrase in query_lower for phrase in ['skip forward', 'fast forward', 'forward 10']):
            return ('youtube_control', {'action': 'seek_forward'})
        if any(phrase in query_lower for phrase in ['rewind', 'go back 10', 'skip backward']):
            return ('youtube_control', {'action': 'seek_backward'})
        
        # Skip ad
        if any(phrase in query_lower for phrase in ['skip ad', 'skip the ad', 'skip advertisement']):
            return ('youtube_control', {'action': 'skip_ad'})
        
        # Browser controls (additional controls - open/close/tab handled earlier)
        if any(phrase in query_lower for phrase in ['refresh page', 'refresh the page', 'reload page', 'refresh']):
            return ('browser_control', {'action': 'refresh'})
        if any(phrase in query_lower for phrase in ['go back', 'back page', 'previous page']) and 'video' not in query_lower:
            return ('browser_control', {'action': 'back'})
        if any(phrase in query_lower for phrase in ['go forward', 'forward page', 'next page']) and 'video' not in query_lower:
            return ('browser_control', {'action': 'forward'})
        if any(phrase in query_lower for phrase in ['maximize browser', 'maximize the browser', 'browser fullscreen']):
            return ('browser_control', {'action': 'maximize'})
        if any(phrase in query_lower for phrase in ['minimize browser', 'minimize the browser']):
            return ('browser_control', {'action': 'minimize'})
        
        # Navigate to URL
        url_match = re.search(r'(?:navigate to|go to|open)\s+(?:url\s+)?(?:https?://)?(\S+\.\S+)', query_lower)
        if url_match and ('navigate' in query_lower or 'url' in query_lower):
            url = url_match.group(1)
            if not url.startswith('http'):
                url = 'https://' + url
            return ('browser_control', {'action': 'goto', 'url': url})
    
    # === System Controls ===
    if SYSTEM_CONTROL_AVAILABLE:
        # Time and Date queries
        if any(phrase in query_lower for phrase in ['what time', 'what is the time', 'current time', 'tell me the time', 'what\'s the time']):
            return ('system_control', {'action': 'get_time'})
        
        if any(phrase in query_lower for phrase in ['what date', 'what is the date', 'what day', 'today\'s date', 'current date', 'what is today', 'whats the date', 'whats today', 'what\'s the date', 'what\'s today']):
            return ('system_control', {'action': 'get_date'})
        
        # Timer controls - multiple patterns
        # Pattern 1: "timer for X seconds" or "set timer for X minutes"
        timer_match = re.search(r'(?:set\s+)?(?:a\s+)?timer\s+(?:for\s+)?(\d+)\s*(second|minute|hour|min|sec|hr)s?', query_lower)
        if timer_match:
            amount = int(timer_match.group(1))
            unit = timer_match.group(2).lower()
            if unit in ['minute', 'min']:
                seconds = amount * 60
            elif unit in ['hour', 'hr']:
                seconds = amount * 3600
            else:
                seconds = amount
            return ('system_control', {'action': 'set_timer', 'seconds': seconds})
        
        # Pattern 2: "5 sec timer" or "set 5 minute timer"
        timer_match2 = re.search(r'(?:set\s+)?(?:a\s+)?(\d+)\s*(second|minute|hour|min|sec|hr)s?\s+timer', query_lower)
        if timer_match2:
            amount = int(timer_match2.group(1))
            unit = timer_match2.group(2).lower()
            if unit in ['minute', 'min']:
                seconds = amount * 60
            elif unit in ['hour', 'hr']:
                seconds = amount * 3600
            else:
                seconds = amount
            return ('system_control', {'action': 'set_timer', 'seconds': seconds})
        
        if any(phrase in query_lower for phrase in ['cancel timer', 'stop timer', 'cancel the timer']):
            return ('system_control', {'action': 'cancel_timer'})
        
        if any(phrase in query_lower for phrase in ['list timers', 'show timers', 'active timers']):
            return ('system_control', {'action': 'list_timers'})
        
        # Stopwatch controls
        if any(phrase in query_lower for phrase in ['start stopwatch', 'start the stopwatch', 'begin stopwatch', 'stopwatch start']):
            return ('system_control', {'action': 'start_stopwatch'})
        
        if any(phrase in query_lower for phrase in ['stop stopwatch', 'stop the stopwatch', 'end stopwatch', 'stopwatch stop', 'pause stopwatch']):
            return ('system_control', {'action': 'stop_stopwatch'})
        
        if any(phrase in query_lower for phrase in ['reset stopwatch', 'clear stopwatch', 'restart stopwatch']):
            return ('system_control', {'action': 'reset_stopwatch'})
        
        if any(phrase in query_lower for phrase in ['stopwatch time', 'stopwatch status', 'check stopwatch', 'how long stopwatch']):
            return ('system_control', {'action': 'get_stopwatch'})
        
        # Alarm controls
        alarm_match = re.search(r'(?:set\s+)?(?:an?\s+)?alarm\s+(?:at\s+|for\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', query_lower)
        if alarm_match:
            hour = int(alarm_match.group(1))
            minute = int(alarm_match.group(2)) if alarm_match.group(2) else 0
            period = alarm_match.group(3)
            if period == 'pm' and hour < 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0
            return ('system_control', {'action': 'set_alarm', 'hour': hour, 'minute': minute})
        
        if any(phrase in query_lower for phrase in ['cancel alarm', 'stop alarm', 'delete alarm', 'remove alarm']):
            return ('system_control', {'action': 'cancel_alarm'})
        
        if any(phrase in query_lower for phrase in ['list alarms', 'show alarms', 'active alarms', 'my alarms']):
            return ('system_control', {'action': 'list_alarms'})
        
        # Reminder controls - multiple patterns
        # Pattern 1: "reminder to X in Y seconds"
        reminder_match = re.search(r'(?:set\s+)?(?:a\s+)?reminder\s+(?:to\s+)?(.+?)\s+in\s+(\d+)\s*(second|minute|hour|min|sec|hr)s?', query_lower)
        if reminder_match:
            message = reminder_match.group(1).strip()
            amount = int(reminder_match.group(2))
            unit = reminder_match.group(3).lower()
            if unit in ['minute', 'min']:
                seconds = amount * 60
            elif unit in ['hour', 'hr']:
                seconds = amount * 3600
            else:
                seconds = amount
            return ('system_control', {'action': 'set_reminder', 'message': message, 'seconds': seconds})
        
        # Pattern 2: "remind me after X sec to Y" or "remind me in X minutes to Y"
        reminder_match2 = re.search(r'remind\s+(?:me\s+)?(?:after|in)\s+(\d+)\s*(second|minute|hour|min|sec|hr)s?\s+(?:to\s+)?(.+)', query_lower)
        if reminder_match2:
            amount = int(reminder_match2.group(1))
            unit = reminder_match2.group(2).lower()
            message = reminder_match2.group(3).strip()
            if unit in ['minute', 'min']:
                seconds = amount * 60
            elif unit in ['hour', 'hr']:
                seconds = amount * 3600
            else:
                seconds = amount
            return ('system_control', {'action': 'set_reminder', 'message': message, 'seconds': seconds})
        
        if any(phrase in query_lower for phrase in ['cancel reminder', 'stop reminder', 'delete reminder', 'remove reminder']):
            return ('system_control', {'action': 'cancel_reminder'})
        
        if any(phrase in query_lower for phrase in ['list reminders', 'show reminders', 'active reminders', 'my reminders']):
            return ('system_control', {'action': 'list_reminders'})
        
        # System info queries
        if any(phrase in query_lower for phrase in ['system status', 'system info', 'computer status', 'pc status']):
            return ('system_control', {'action': 'get_system_info'})
        
        if any(phrase in query_lower for phrase in ['cpu usage', 'cpu status', 'processor usage', 'check cpu']):
            return ('system_control', {'action': 'get_cpu_usage'})
        
        if any(phrase in query_lower for phrase in ['memory usage', 'ram usage', 'ram status', 'check memory', 'check ram']):
            return ('system_control', {'action': 'get_memory_usage'})
        
        if any(phrase in query_lower for phrase in ['gpu status', 'gpu usage', 'graphics card', 'check gpu', 'nvidia status']):
            return ('system_control', {'action': 'get_gpu_status'})
        
        if any(phrase in query_lower for phrase in ['battery status', 'battery level', 'check battery']):
            return ('system_control', {'action': 'get_battery'})
        
        if any(phrase in query_lower for phrase in ['disk usage', 'disk space', 'storage space', 'check disk', 'hard drive']):
            return ('system_control', {'action': 'get_disk_usage'})
        
        if any(phrase in query_lower for phrase in ['network info', 'ip address', 'my ip', 'network status', 'check network']):
            return ('system_control', {'action': 'get_network_info'})
        
        # Volume controls (system)
        if 'volume' in query_lower and 'video' not in query_lower and 'youtube' not in query_lower:
            if any(word in query_lower for word in ['up', 'increase', 'raise', 'higher']):
                return ('system_control', {'action': 'volume_up'})
            if any(word in query_lower for word in ['down', 'decrease', 'lower', 'reduce']):
                return ('system_control', {'action': 'volume_down'})
            if 'mute' in query_lower and 'unmute' not in query_lower:
                return ('system_control', {'action': 'mute'})
            if 'unmute' in query_lower:
                return ('system_control', {'action': 'unmute'})
            # Set volume to specific level
            match = re.search(r'volume\s+(?:to\s+)?(\d+)', query_lower)
            if match:
                return ('system_control', {'action': 'volume_set', 'level': int(match.group(1))})
        
        # Mute/Unmute without "volume" word (system level, not video)
        if 'video' not in query_lower and 'youtube' not in query_lower:
            if 'unmute' in query_lower and any(word in query_lower for word in ['system', 'computer', 'audio', 'sound']):
                return ('system_control', {'action': 'unmute'})
            if 'mute' in query_lower and 'unmute' not in query_lower and any(word in query_lower for word in ['system', 'computer', 'audio', 'sound']):
                return ('system_control', {'action': 'mute'})
        
        # Brightness controls
        if 'brightness' in query_lower:
            if any(word in query_lower for word in ['up', 'increase', 'raise', 'higher']):
                return ('system_control', {'action': 'brightness_up'})
            if any(word in query_lower for word in ['down', 'decrease', 'lower', 'reduce']):
                return ('system_control', {'action': 'brightness_down'})
            match = re.search(r'brightness\s+(?:to\s+)?(\d+)', query_lower)
            if match:
                return ('system_control', {'action': 'brightness_set', 'level': int(match.group(1))})
        
        # Screenshot
        if any(phrase in query_lower for phrase in ['take screenshot', 'take a screenshot', 'capture screen', 'screenshot']):
            return ('system_control', {'action': 'screenshot'})
        
        # Lock screen - expanded patterns
        if any(phrase in query_lower for phrase in ['lock screen', 'lockscreen', 'lock the screen', 'lock computer', 'lock my computer', 'lock the computer', 'lock pc', 'lock my pc', 'lock the pc', 'lock system']):
            return ('system_control', {'action': 'lock'})
        
        # Sleep/Suspend
        if any(phrase in query_lower for phrase in ['go to sleep', 'sleep mode', 'suspend', 'put to sleep']):
            return ('system_control', {'action': 'suspend'})
        
        # Shutdown
        if any(phrase in query_lower for phrase in ['shut down', 'shutdown', 'power off', 'turn off computer']):
            return ('system_control', {'action': 'shutdown'})
        
        # Restart
        if any(phrase in query_lower for phrase in ['restart', 'reboot', 'restart computer']):
            return ('system_control', {'action': 'restart'})
        
        # WiFi controls
        if 'wifi' in query_lower or 'wi-fi' in query_lower:
            if any(word in query_lower for word in ['on', 'enable', 'turn on']):
                return ('system_control', {'action': 'wifi_on'})
            if any(word in query_lower for word in ['off', 'disable', 'turn off']):
                return ('system_control', {'action': 'wifi_off'})
            if 'status' in query_lower:
                return ('system_control', {'action': 'wifi_status'})
        
        # Bluetooth controls
        if 'bluetooth' in query_lower:
            if any(word in query_lower for word in ['on', 'enable', 'turn on']):
                return ('system_control', {'action': 'bluetooth_on'})
            if any(word in query_lower for word in ['off', 'disable', 'turn off']):
                return ('system_control', {'action': 'bluetooth_off'})
        
        # Hibernate
        if any(phrase in query_lower for phrase in ['hibernate', 'hibernation']):
            return ('system_control', {'action': 'hibernate'})
        
        # Window/App management - Close app (e.g., "close arduino ide", "close firefox")
        # Must check this BEFORE generic window patterns
        close_app_match = re.search(r'close\s+(?:the\s+)?([a-zA-Z0-9 _-]+?)(?:\s+window|\s+app|\s+application)?$', query_lower)
        if close_app_match and 'browser' not in query_lower and 'tab' not in query_lower:
            app_name = close_app_match.group(1).strip()
            # Filter out generic words
            if app_name and app_name not in ['window', 'app', 'application', 'the', 'this', 'that']:
                return ('system_control', {'action': 'close_app', 'app_name': app_name})
        
        # Window/App management - Minimize app (e.g., "minimize arduino ide", "minimize firefox")
        minimize_match = re.search(r'minimize\s+(?:the\s+)?([a-zA-Z0-9 _-]+?)(?:\s+window|\s+app|\s+application)?$', query_lower)
        if minimize_match:
            app_name = minimize_match.group(1).strip()
            if app_name and app_name not in ['window', 'app', 'application', 'the', 'this', 'that']:
                return ('system_control', {'action': 'minimize_window', 'app_name': app_name})
        
        # Window/App management - Maximize app (e.g., "maximize arduino ide", "maximize vs code")
        maximize_match = re.search(r'maximize\s+(?:the\s+)?([a-zA-Z0-9 _-]+?)(?:\s+window|\s+app|\s+application)?$', query_lower)
        if maximize_match:
            app_name = maximize_match.group(1).strip()
            if app_name and app_name not in ['window', 'app', 'application', 'the', 'this', 'that']:
                return ('system_control', {'action': 'maximize_window', 'app_name': app_name})
        
        # Focus window / switch to app
        if any(phrase in query_lower for phrase in ['switch to', 'focus on', 'bring up', 'show me']):
            match = re.search(r'(?:switch to|focus on|bring up|show me)\s+(?:the\s+)?(.+?)(?:\s+window|\s+app)?$', query_lower)
            if match:
                app_name = match.group(1).strip()
                if app_name and app_name not in ['window', 'app', 'application']:
                    return ('system_control', {'action': 'focus_window', 'app_name': app_name})
        
        # File management - Find file
        if 'find' in query_lower and 'file' in query_lower:
            match = re.search(r'find\s+(?:a\s+)?(?:file\s+)?(?:named?\s+)?["\']?([^"\']+)["\']?(?:\s+file)?', query_lower)
            if match:
                name = match.group(1).strip()
                name = re.sub(r'\s+file$', '', name)  # Remove trailing "file"
                if name and name != 'file':
                    return ('system_control', {'action': 'find_file', 'name': name})
        
        # File management - Find large files
        if any(phrase in query_lower for phrase in ['large files', 'big files', 'files bigger than', 'files larger than', 'files over']):
            size_match = re.search(r'(\d+)\s*(gb|mb|kb|g|m|k)', query_lower)
            if size_match:
                size = size_match.group(1)
                unit = size_match.group(2).upper()
                if unit in ['GB', 'G']:
                    min_size = f"{size}G"
                elif unit in ['MB', 'M']:
                    min_size = f"{size}M"
                else:
                    min_size = f"{size}K"
            else:
                min_size = "100M"
            return ('system_control', {'action': 'find_large_files', 'min_size': min_size})
        
        # File management - Create file
        if 'create' in query_lower and 'file' in query_lower:
            match = re.search(r'create\s+(?:a\s+)?(?:new\s+)?file\s+(?:at\s+|named?\s+)?["\']?([^"\']+)["\']?', query_lower)
            if match:
                filepath = match.group(1).strip()
                return ('system_control', {'action': 'create_file', 'filepath': filepath})
        
        # File management - Delete file
        if any(word in query_lower for word in ['delete', 'remove']) and 'file' in query_lower:
            match = re.search(r'(?:delete|remove)\s+(?:the\s+)?(?:file\s+)?(?:at\s+)?["\']?([^"\']+)["\']?(?:\s+file)?', query_lower)
            if match:
                filepath = match.group(1).strip()
                filepath = re.sub(r'\s+file$', '', filepath)
                if filepath and filepath != 'file':
                    return ('system_control', {'action': 'delete_file', 'filepath': filepath})
        
        # File management - Open file manager
        if any(phrase in query_lower for phrase in ['open file manager', 'open files', 'open folder', 'open directory', 'show files']):
            path_match = re.search(r'(?:at|in)\s+["\']?([^"\']+)["\']?', query_lower)
            path = path_match.group(1).strip() if path_match else "~"
            return ('system_control', {'action': 'open_file_manager', 'path': path})
    
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
    
    # Get or create session - use default session if none provided for persistent memory
    if session_id is None:
        session_id = DEFAULT_SESSION_ID
    session = session_manager.get_or_create_session(session_id)
    
    # Store language in session context
    session.context['language'] = language
    
    # Add user query to history
    session.add_turn("user", user_query)
    logger.debug(f"[Timing] Session setup: {time.time() - gen_start:.3f}s")
    
    # Check if user is asking about history/previous commands/memory
    # Be specific to avoid matching "play previous video" etc.
    history_phrases = ['what did i', 'what i said', 'previous command', 'earlier command', 
                       'before this', 'conversation history', 'recall what', 'remember what',
                       'what did you say', 'what was my', 'do you remember', 'can you remember',
                       'our conversation', 'what we talked', 'what have we', 'our previous',
                       'my last question', 'my previous question', 'earlier conversation']
    if any(phrase in user_query.lower() for phrase in history_phrases):
        history = session.get_history()
        if history and len(history) > 1:  # More than just the current query
            history_text = "\n".join([f"{turn['role']}: {turn['content']}" for turn in history[-20:]])  # Last 20 turns
            tool_context = {
                "role": "user",
                "content": f"""The user asked: "{user_query}"

Here is our recent conversation history (last {min(20, len(history))} turns):
{history_text}

Provide a natural response based on this conversation history. Summarize what we discussed or help them recall specific information."""
            }
            messages = [
                {"role": "system", "content": "You are JARVIS, an AI assistant. You have access to the conversation history and can recall what was discussed. Be helpful and specific about past conversations."},
                tool_context
            ]
            async for sentence in llm.generate_stream(messages, temperature=0.7, max_tokens=500):
                yield sentence
            return
        else:
            # No meaningful history yet
            yield "We haven't had much conversation yet in this session. Feel free to ask me anything!"
            return
    
    # Check for direct tool intent (pattern matching)
    if enable_tools:
        # MULTI-COMMAND CHECK: Check if this is a multi-command query first
        if is_multi_command_query(user_query):
            multi_check_start = time.time()
            logger.info(f"Detected potential multi-command query: {user_query[:100]}")
            
            multi_commands = await llm_parse_multi_command(user_query)
            logger.debug(f"[Timing] Multi-command parsing: {time.time() - multi_check_start:.3f}s")
            
            if multi_commands and len(multi_commands) > 0:
                logger.info(f"Executing {len(multi_commands)} commands sequentially")
                
                # Execute commands and yield status updates
                async for status in execute_multi_commands(multi_commands):
                    yield status
                
                return
            else:
                logger.debug("Multi-command parsing returned no commands, falling through to single command")
        
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
            
            # YouTube media controls
            elif tool_name == 'youtube_control' and BROWSER_AUTOMATION_AVAILABLE:
                tool_result = await browser_tool.youtube_control(parameters['action'])
                logger.info(f"YouTube control result: {tool_result}")
            
            # Browser controls
            elif tool_name == 'browser_control' and BROWSER_AUTOMATION_AVAILABLE:
                tool_result = await browser_tool.browser_control(
                    parameters['action'], 
                    parameters.get('url')
                )
                logger.info(f"Browser control result: {tool_result}")
            
            # System controls
            elif tool_name == 'system_control' and SYSTEM_CONTROL_AVAILABLE:
                tool_result = system_control.execute_control(
                    parameters['action'],
                    **{k: v for k, v in parameters.items() if k != 'action'}
                )
                logger.info(f"System control result: {tool_result}")
            
            else:
                # Execute tool through tool_manager
                tool_result = await tool_manager.execute_tool(tool_name, parameters)
                logger.info(f"Tool result: {tool_result}")
            
            # Generate natural response with tool result
            # For successful actions, use very short responses
            is_success = tool_result.get('success', False)
            result_message = tool_result.get('message', '')
            
            # Check if this is an INFO query (time, date, system status, etc.) vs ACTION command
            info_actions = ['get_time', 'get_date', 'get_datetime', 'get_system_status', 
                           'get_cpu_usage', 'get_gpu_status', 'get_battery_status',
                           'get_disk_usage', 'get_network_info', 'get_memory_usage',
                           'system_status', 'cpu_usage', 'gpu_status', 'battery_status',
                           'disk_usage', 'network_info', 'list_timers', 'list_reminders',
                           'list_alarms', 'get_stopwatch', 'stop_stopwatch', 'set_timer',
                           'set_reminder', 'set_alarm', 'start_stopwatch']
            is_info_query = parameters.get('action', '') in info_actions
            
            if is_success and tool_name in ['youtube_control', 'browser_control', 'system_control', 'youtube_autoplay']:
                if is_info_query:
                    # For info queries, return the actual information naturally
                    tool_context = {
                        "role": "user",
                        "content": f"""User asked: "{user_query}"
Result: {result_message}

Respond naturally and briefly with just the requested information. Don't add extra commentary."""
                    }
                else:
                    # For control actions, give extremely brief responses
                    tool_context = {
                        "role": "user",
                        "content": f"""User: "{user_query}"
Tool result: {result_message}

Reply with ONLY 1-3 words confirming the action. Examples: "Done", "Paused", "Playing", "Volume up", "Opened", "Closed". Do NOT explain further."""
                    }
            else:
                # For other tools or failures, be more descriptive
                tool_context = {
                    "role": "user",
                    "content": f"""User: "{user_query}"
Tool: {tool_name}
Result: {json.dumps(tool_result, indent=2)}

{"Briefly explain what went wrong." if not is_success else "Briefly confirm what was done."}"""
                }
            
            messages = [
                {"role": "system", "content": "You are JARVIS. Be extremely brief for successful control actions (1-3 words). Only elaborate if there was an error."},
                tool_context
            ]
            
            async for sentence in llm.generate_stream(messages, temperature=0.3, max_tokens=100):
                yield sentence
            
            return
        
        # Pattern matching didn't find a tool - try LLM-based classification
        # This handles typos, variations, and natural language commands
        llm_intent_start = time.time()
        llm_intent = await llm_classify_intent(user_query)
        logger.debug(f"[Timing] LLM intent classification: {time.time() - llm_intent_start:.3f}s")
        
        if llm_intent:
            tool_name, parameters = llm_intent
            logger.info(f"LLM classified tool intent: {tool_name} with params: {parameters}")
            
            # Execute the classified intent (same handling as pattern matching)
            tool_result = None
            
            if tool_name == 'youtube_autoplay' and BROWSER_AUTOMATION_AVAILABLE:
                tool_result = await browser_tool.youtube_autoplay(parameters.get('search_query', ''))
            elif tool_name == 'youtube_control' and BROWSER_AUTOMATION_AVAILABLE:
                tool_result = await browser_tool.youtube_control(parameters.get('action', 'play'))
            elif tool_name == 'browser_control' and BROWSER_AUTOMATION_AVAILABLE:
                tool_result = await browser_tool.browser_control(
                    parameters.get('action', 'open'),
                    parameters.get('url')
                )
            elif tool_name == 'system_control' and SYSTEM_CONTROL_AVAILABLE:
                tool_result = system_control.execute_control(
                    parameters.get('action', ''),
                    **{k: v for k, v in parameters.items() if k != 'action'}
                )
            elif tool_name == 'run_command':
                tool_result = run_command(parameters.get('command', ''))
            else:
                tool_result = await tool_manager.execute_tool(tool_name, parameters)
            
            if tool_result:
                logger.info(f"LLM-classified tool result: {tool_result}")
                
                is_success = tool_result.get('success', False)
                result_message = tool_result.get('message', '')
                
                # Check if info query
                info_actions = ['get_time', 'get_date', 'get_datetime', 'get_system_status', 
                               'get_cpu_usage', 'get_gpu_status', 'get_battery_status',
                               'get_disk_usage', 'get_network_info', 'get_memory_usage',
                               'list_timers', 'list_reminders', 'list_alarms', 'get_stopwatch',
                               'stop_stopwatch', 'set_timer', 'set_reminder', 'set_alarm', 'start_stopwatch']
                is_info_query = parameters.get('action', '') in info_actions
                
                if is_success:
                    if is_info_query:
                        tool_context = {
                            "role": "user",
                            "content": f"""User asked: "{user_query}"
Result: {result_message}

Respond naturally and briefly with just the requested information."""
                        }
                    else:
                        tool_context = {
                            "role": "user",
                            "content": f"""User: "{user_query}"
Tool result: {result_message}

Reply with ONLY 1-3 words confirming the action."""
                        }
                else:
                    tool_context = {
                        "role": "user",
                        "content": f"""User: "{user_query}"
Result: {json.dumps(tool_result, indent=2)}

Briefly explain what went wrong."""
                    }
                
                messages = [
                    {"role": "system", "content": "You are JARVIS. Be extremely brief."},
                    tool_context
                ]
                
                async for sentence in llm.generate_stream(messages, temperature=0.3, max_tokens=100):
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

RESPONSE LENGTH RULES:
- For system/browser/YouTube control actions that SUCCEEDED: Reply with just 1-3 words like "Done", "Opened", "Paused", "Volume up", etc. Do NOT give long explanations.
- For actions that FAILED: Briefly explain what went wrong in one sentence.
- For questions and conversations: Be conversational but concise.
- For complex queries: Be detailed as needed.

Always maintain context from previous conversation."""
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

@app.post("/api/voice/text/json")
async def voice_text_json(request: TextRequest):
    """Text input -> Audio output (TTS response) - Complete audio in JSON (non-streaming)
    
    NOTE: Use /api/voice/text for streaming audio response (recommended for low latency).
    This endpoint waits for complete response before returning.
    """
    try:
        logger.info(f"Text to voice (JSON): {request.text[:100]}")
        
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
        logger.error(f"Voice text JSON error: {e}")
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
