"""
Streaming LLM integration with sentence boundary detection and tool calling
"""
import aiohttp
import asyncio
import re
import json
from typing import AsyncGenerator, Optional, List, Dict, Any
from core.config import settings
from core.logger import setup_logger

logger = setup_logger(__name__)

# Simple query detection keywords
SIMPLE_KEYWORDS = ['what is', 'who is', 'calculate', 'plus', 'minus', 'times', 'divided']
DETAILED_KEYWORDS = ['explain', 'describe', 'how does', 'tell me about', 'detail']

def clean_text_for_tts(text: str) -> str:
    """
    Clean text for TTS - remove markdown and special characters
    Keeps only speech-friendly text
    """
    # Remove markdown formatting
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)  # Italic
    text = re.sub(r'__([^_]+)__', r'\1', text)  # Bold underscore
    text = re.sub(r'_([^_]+)_', r'\1', text)  # Italic underscore
    
    # Remove code blocks and inline code
    text = re.sub(r'```[^`]*```', ' ', text)  # Code blocks
    text = re.sub(r'`([^`]+)`', r'\1', text)  # Inline code
    
    # Remove links but keep text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # [text](url)
    
    # Remove special markdown characters
    text = re.sub(r'[#\-\u2022>]', ' ', text)  # Headers, bullets, quotes
    
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

class StreamingLLM:
    """Streaming LLM interface with sentence-level chunking for TTS and tool calling"""
    
    def __init__(self):
        self.api_url = settings.LLM_API_URL
        self.model = settings.LLM_MODEL_NAME
        self.sentence_buffer = ""
        # Sentence boundary patterns
        self.sentence_endings = re.compile(r'([.!?])\s+')
        logger.info(f"StreamingLLM initialized (model: {self.model})")
    
    def format_tools_for_prompt(self, tools: List[Dict]) -> str:
        """
        Format tools as part of system prompt
        Returns formatted string describing available tools
        """
        if not tools:
            return ""
        
        tool_descriptions = []
        for tool in tools:
            params = []
            for param_name, param_info in tool.get('parameters', {}).items():
                param_type = param_info.get('type', 'string')
                param_desc = param_info.get('description', '')
                params.append(f"  - {param_name} ({param_type}): {param_desc}")
            
            params_str = '\n'.join(params) if params else "  (no parameters)"
            tool_desc = f"""
Tool: {tool['name']}
Description: {tool['description']}
Parameters:
{params_str}
"""
            tool_descriptions.append(tool_desc)
        
        return f"""

=== AVAILABLE TOOLS ===
You can use the following tools to help users:

{chr(10).join(tool_descriptions)}

=== HOW TO USE TOOLS ===
When a user asks you to do something that requires a tool, you MUST respond with ONLY this JSON format (no other text):

TOOL_CALL: {{"tool": "tool_name", "parameters": {{"param_name": "value"}}}}

Examples:
- User: "open youtube.com" → You respond: TOOL_CALL: {{"tool": "open_url", "parameters": {{"url": "https://youtube.com"}}}}
- User: "check system status" → You respond: TOOL_CALL: {{"tool": "get_system_status", "parameters": {{}}}}
- User: "read file test.txt" → You respond: TOOL_CALL: {{"tool": "read_file", "parameters": {{"file_path": "test.txt"}}}}
- User: "create file hello.txt with Hello World" → You respond: TOOL_CALL: {{"tool": "write_file", "parameters": {{"file_path": "hello.txt", "content": "Hello World"}}}}

After the tool executes, you'll receive the result and should respond naturally with the information.
"""
    
    async def generate_stream(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream LLM tokens and yield complete sentences
        
        Args:
            messages: Chat messages in OpenAI format
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Yields:
            Complete sentences ready for TTS
        """
        # Use defaults from config if not specified
        if max_tokens is None:
            max_tokens = settings.LLM_NORMAL_QUERY_MAX_TOKENS
        if timeout is None:
            timeout = settings.LLM_NORMAL_TIMEOUT
        
        logger.info(f"LLM stream started (messages: {len(messages)}, max_tokens: {max_tokens})")
        self.sentence_buffer = ""
        token_count = 0
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True
                }
                
                async with session.post(
                    self.api_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    if response.status != 200:
                        error = await response.text()
                        logger.error(f"LLM API error {response.status}: {error}")
                        yield "I'm having trouble generating a response."
                        return
                    
                    async for line in response.content:
                        line = line.decode('utf-8').strip()
                        
                        if not line.startswith('data: '):
                            continue
                        
                        data_str = line[6:]  # Remove 'data: '
                        
                        if data_str == '[DONE]':
                            # Yield any remaining buffer
                            if self.sentence_buffer.strip():
                                clean_final = clean_text_for_tts(self.sentence_buffer.strip())
                                if clean_final:
                                    logger.debug(f"Final buffer: {clean_final[:50]}")
                                    yield clean_final
                            break
                        
                        try:
                            import json
                            data = json.loads(data_str)
                            delta = data['choices'][0]['delta']
                            
                            if 'content' in delta:
                                content = delta['content']
                                if content:  # Only process non-None content
                                    token_count += 1
                                    self.sentence_buffer += content
                                    
                                    # Check for sentence boundaries
                                    sentences = self._extract_sentences(self.sentence_buffer)
                                    for sentence in sentences:
                                        # Clean text for TTS (remove markdown, special chars)
                                        clean_sentence = clean_text_for_tts(sentence)
                                        if clean_sentence:  # Only yield non-empty sentences
                                            logger.debug(f"Yielding sentence: {clean_sentence[:50]}")
                                            yield clean_sentence
                                    
                        except json.JSONDecodeError:
                            continue
                        except KeyError:
                            continue
            
            logger.info(f"LLM stream completed ({token_count} tokens)")
            
        except asyncio.TimeoutError:
            logger.error("LLM stream timeout")
            yield "Response timed out."
        except Exception as e:
            logger.error(f"LLM stream error: {e}")
            yield f"Error generating response: {str(e)}"
    
    def _extract_sentences(self, text: str) -> List[str]:
        """
        Extract complete sentences from buffer
        Updates buffer to keep incomplete sentence
        
        Returns:
            List of complete sentences
        """
        sentences = []
        
        # Find sentence boundaries
        matches = list(self.sentence_endings.finditer(text))
        
        if not matches:
            return sentences
        
        # Get last sentence boundary
        last_match = matches[-1]
        boundary_pos = last_match.end()
        
        # Extract complete sentences
        complete_text = text[:boundary_pos].strip()
        if complete_text:
            sentences.append(complete_text)
        
        # Keep remaining text in buffer
        self.sentence_buffer = text[boundary_pos:].strip()
        
        return sentences
    
    async def generate_complete(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> str:
        """Generate complete response (non-streaming)"""
        response = ""
        async for sentence in self.generate_stream(messages, temperature, max_tokens):
            response += sentence + " "
        return response.strip()
    
    def extract_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract tool call from LLM response
        
        Returns:
            Dict with 'tool' and 'parameters' keys, or None if no tool call detected
        """
        # Look for TOOL_CALL: prefix followed by JSON
        tool_call_pattern = r'TOOL_CALL:\s*(\{[^}]*"tool"\s*:\s*"[^"]+[^}]*\})'
        match = re.search(tool_call_pattern, text, re.IGNORECASE)
        
        if match:
            try:
                json_str = match.group(1)
                tool_call = json.loads(json_str)
                
                if 'tool' in tool_call and 'parameters' in tool_call:
                    logger.info(f"Detected tool call: {tool_call['tool']}")
                    return tool_call
            except json.JSONDecodeError as e:
                logger.debug(f"Failed to parse tool call JSON: {e}")
        
        # Fallback: look for JSON objects with "tool" key anywhere
        json_pattern = r'\{[^}]*"tool"\s*:\s*"([^"]+)"[^}]*\}'
        match = re.search(json_pattern, text)
        
        if match:
            try:
                json_str = match.group(0)
                tool_call = json.loads(json_str)
                
                if 'tool' in tool_call and 'parameters' in tool_call:
                    logger.info(f"Detected tool call (fallback): {tool_call['tool']}")
                    return tool_call
            except json.JSONDecodeError:
                logger.debug("Failed to parse fallback tool call JSON")
        
        return None

# Global LLM instance
llm = StreamingLLM()
