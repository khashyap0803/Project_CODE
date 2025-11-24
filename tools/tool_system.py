"""
JARVIS Tool System - Enable agent capabilities
Provides system control, file operations, browser automation, etc.
"""
import os
import subprocess
import json
import psutil
import glob
from pathlib import Path
from typing import Optional, Dict, List, Any
from abc import ABC, abstractmethod
from core.logger import setup_logger

logger = setup_logger(__name__)

class Tool(ABC):
    """Base class for all tools"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Tool description for LLM"""
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> Dict:
        """Tool parameters schema"""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool"""
        pass
    
    def to_dict(self) -> Dict:
        """Convert tool to dict for LLM"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }

class FileReadTool(Tool):
    """Read file contents"""
    
    @property
    def name(self) -> str:
        return "read_file"
    
    @property
    def description(self) -> str:
        return "Read the contents of a file. Use this to view file contents."
    
    @property
    def parameters(self) -> Dict:
        return {
            "file_path": {
                "type": "string",
                "description": "Path to the file to read"
            }
        }
    
    async def execute(self, file_path: str) -> Dict[str, Any]:
        try:
            path = Path(file_path).expanduser()
            if not path.exists():
                return {"error": f"File not found: {file_path}"}
            
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return {
                "success": True,
                "content": content,
                "size": len(content),
                "path": str(path)
            }
        except Exception as e:
            return {"error": str(e)}

class FileWriteTool(Tool):
    """Write content to file"""
    
    @property
    def name(self) -> str:
        return "write_file"
    
    @property
    def description(self) -> str:
        return "Write content to a file. Creates new file or overwrites existing."
    
    @property
    def parameters(self) -> Dict:
        return {
            "file_path": {
                "type": "string",
                "description": "Path to the file to write"
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file"
            }
        }
    
    async def execute(self, file_path: str, content: str) -> Dict[str, Any]:
        try:
            path = Path(file_path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return {
                "success": True,
                "path": str(path),
                "size": len(content)
            }
        except Exception as e:
            return {"error": str(e)}

class ListDirectoryTool(Tool):
    """List directory contents"""
    
    @property
    def name(self) -> str:
        return "list_directory"
    
    @property
    def description(self) -> str:
        return "List files and directories in a given path."
    
    @property
    def parameters(self) -> Dict:
        return {
            "path": {
                "type": "string",
                "description": "Directory path to list (default: current directory)"
            }
        }
    
    async def execute(self, path: str = ".") -> Dict[str, Any]:
        try:
            dir_path = Path(path).expanduser()
            if not dir_path.exists():
                return {"error": f"Directory not found: {path}"}
            
            items = []
            for item in dir_path.iterdir():
                items.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else None
                })
            
            return {
                "success": True,
                "path": str(dir_path),
                "items": items,
                "count": len(items)
            }
        except Exception as e:
            return {"error": str(e)}

class RunCommandTool(Tool):
    """Execute shell command"""
    
    @property
    def name(self) -> str:
        return "run_command"
    
    @property
    def description(self) -> str:
        return "Execute a shell command on the system. Use for system operations, launching apps, etc."
    
    @property
    def parameters(self) -> Dict:
        return {
            "command": {
                "type": "string",
                "description": "Shell command to execute"
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 30)",
                "default": 30
            }
        }
    
    async def execute(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        try:
            # Detect if this is an app launch command (contains nohup ... &)
            # For app launches, use Popen to avoid blocking
            ends_with_amp = command.strip().endswith('&')
            has_nohup = 'nohup' in command
            is_background_launch = ends_with_amp and has_nohup
            
            logger.info(f"Executing command: {command[:100]}... | ends_with_amp={ends_with_amp}, has_nohup={has_nohup}, is_background={is_background_launch}")
            
            if is_background_launch:
                # Launch app in background without blocking
                logger.warning(f"🚀 BACKGROUND LAUNCH DETECTED - Non-blocking execution for: {command[:80]}")
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True  # Detach from parent process
                )
                # Don't wait for the process - return immediately
                return {
                    "success": True,
                    "stdout": f"Application launched in background (PID: {process.pid})",
                    "stderr": "",
                    "return_code": 0,
                    "command": command
                }
            
            # For regular commands, use blocking execution
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "command": command
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}

class GetSystemStatusTool(Tool):
    """Get system resource usage"""
    
    @property
    def name(self) -> str:
        return "get_system_status"
    
    @property
    def description(self) -> str:
        return "Get current system resource usage (CPU, RAM, disk, etc.)"
    
    @property
    def parameters(self) -> Dict:
        return {}
    
    async def execute(self) -> Dict[str, Any]:
        try:
            return {
                "success": True,
                "cpu_percent": psutil.cpu_percent(interval=1),
                "ram": {
                    "total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
                    "used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
                    "percent": psutil.virtual_memory().percent
                },
                "disk": {
                    "total_gb": round(psutil.disk_usage('/').total / (1024**3), 2),
                    "used_gb": round(psutil.disk_usage('/').used / (1024**3), 2),
                    "percent": psutil.disk_usage('/').percent
                }
            }
        except Exception as e:
            return {"error": str(e)}

class SearchFilesTool(Tool):
    """Search for files by pattern"""
    
    @property
    def name(self) -> str:
        return "search_files"
    
    @property
    def description(self) -> str:
        return "Search for files matching a pattern (supports wildcards like *.py)"
    
    @property
    def parameters(self) -> Dict:
        return {
            "pattern": {
                "type": "string",
                "description": "File search pattern (e.g., '*.py', 'test_*.txt')"
            },
            "directory": {
                "type": "string",
                "description": "Directory to search in (default: current directory)"
            }
        }
    
    async def execute(self, pattern: str, directory: str = ".") -> Dict[str, Any]:
        try:
            dir_path = Path(directory).expanduser()
            search_pattern = str(dir_path / "**" / pattern)
            
            files = glob.glob(search_pattern, recursive=True)
            
            return {
                "success": True,
                "files": files[:50],  # Limit to 50 results
                "count": len(files),
                "pattern": pattern
            }
        except Exception as e:
            return {"error": str(e)}

class OpenURLTool(Tool):
    """Open URL in browser"""
    
    @property
    def name(self) -> str:
        return "open_url"
    
    @property
    def description(self) -> str:
        return "Open a URL in the default web browser"
    
    @property
    def parameters(self) -> Dict:
        return {
            "url": {
                "type": "string",
                "description": "URL to open (must include http:// or https://)"
            }
        }
    
    async def execute(self, url: str) -> Dict[str, Any]:
        try:
            import webbrowser
            webbrowser.open(url)
            
            return {
                "success": True,
                "url": url,
                "message": "URL opened in browser"
            }
        except Exception as e:
            return {"error": str(e)}

class ToolManager:
    """Manages all available tools"""
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self.register_default_tools()
        logger.info(f"Tool Manager initialized with {len(self.tools)} tools")
    
    def register_default_tools(self):
        """Register all default tools"""
        tools = [
            FileReadTool(),
            FileWriteTool(),
            ListDirectoryTool(),
            RunCommandTool(),
            GetSystemStatusTool(),
            SearchFilesTool(),
            OpenURLTool(),
        ]
        
        for tool in tools:
            self.register_tool(tool)
    
    def register_tool(self, tool: Tool):
        """Register a new tool"""
        self.tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get tool by name"""
        return self.tools.get(name)
    
    def get_all_tools(self) -> List[Tool]:
        """Get all registered tools"""
        return list(self.tools.values())
    
    def get_tools_description(self) -> str:
        """Get formatted description of all tools for LLM"""
        descriptions = []
        for tool in self.tools.values():
            params = ", ".join([f"{k}={v.get('type')}" for k, v in tool.parameters.items()])
            descriptions.append(f"- {tool.name}({params}): {tool.description}")
        
        return "\n".join(descriptions)
    
    async def execute_tool(self, tool_name: str, parameters: Dict) -> Dict[str, Any]:
        """Execute a tool by name"""
        tool = self.get_tool(tool_name)
        
        if not tool:
            return {"error": f"Tool not found: {tool_name}"}
        
        try:
            logger.info(f"Executing tool: {tool_name} with parameters: {parameters}")
            result = await tool.execute(**parameters)
            logger.debug(f"Tool {tool_name} result: {result}")
            return result
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {"error": str(e)}

# Global tool manager instance
tool_manager = ToolManager()
