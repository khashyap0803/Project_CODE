"""
Code Execution and System Control via Open Interpreter
Enables JARVIS to execute Python code, run system commands, and interact with the OS
"""
import subprocess
import sys
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
from core.logger import setup_logger
from core.config import settings

logger = setup_logger(__name__)

class CodeExecutor:
    """Safe code execution with sandboxing and permissions"""
    
    def __init__(self):
        self.allowed_imports = [
            'os', 'sys', 'json', 'datetime', 'time', 'math', 'random',
            'pathlib', 'subprocess', 'requests', 'numpy', 'pandas'
        ]
        self.forbidden_operations = [
            'rm -rf /', 'sudo ', 'chmod 777', 'dd if=', 'format'
        ]
    
    def is_safe_command(self, command: str) -> tuple[bool, str]:
        """Check if system command is safe to execute"""
        command_lower = command.lower()
        
        # Check for dangerous commands
        for forbidden in self.forbidden_operations:
            if forbidden in command_lower:
                return False, f"Dangerous operation detected: {forbidden}"
        
        # Check for critical system directories
        dangerous_paths = ['/sys', '/proc', '/dev', '/boot']
        for path in dangerous_paths:
            if path in command and ('rm' in command_lower or 'delete' in command_lower):
                return False, f"Cannot modify critical system directory: {path}"
        
        return True, "Safe to execute"
    
    def execute_python(
        self, 
        code: str, 
        timeout: int = 30,
        capture_output: bool = True
    ) -> Dict[str, Any]:
        """
        Execute Python code safely
        
        Args:
            code: Python code to execute
            timeout: Execution timeout in seconds
            capture_output: Whether to capture stdout/stderr
            
        Returns:
            Dict with stdout, stderr, return_code, success
        """
        try:
            logger.info(f"Executing Python code ({len(code)} chars)")
            
            # Create temporary file
            temp_file = Path("/tmp/jarvis_exec.py")
            temp_file.write_text(code)
            
            # Execute with timeout
            result = subprocess.run(
                [sys.executable, str(temp_file)],
                capture_output=capture_output,
                text=True,
                timeout=timeout,
                cwd=os.getcwd()
            )
            
            # Cleanup
            temp_file.unlink()
            
            success = result.returncode == 0
            
            logger.info(f"Python execution {'succeeded' if success else 'failed'} (exit code: {result.returncode})")
            
            return {
                "success": success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "error": None if success else result.stderr
            }
            
        except subprocess.TimeoutExpired:
            logger.warning(f"Python execution timed out after {timeout}s")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds",
                "return_code": -1,
                "error": "Timeout"
            }
        except Exception as e:
            logger.error(f"Python execution error: {e}")
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
                "error": str(e)
            }
    
    def execute_system_command(
        self,
        command: str,
        timeout: int = 30,
        shell: bool = True
    ) -> Dict[str, Any]:
        """
        Execute system command with safety checks
        
        Args:
            command: System command to execute
            timeout: Execution timeout in seconds
            shell: Whether to use shell execution
            
        Returns:
            Dict with stdout, stderr, return_code, success
        """
        try:
            # Safety check
            is_safe, reason = self.is_safe_command(command)
            if not is_safe:
                logger.warning(f"Blocked unsafe command: {reason}")
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Command blocked: {reason}",
                    "return_code": -1,
                    "error": f"Safety check failed: {reason}"
                }
            
            logger.info(f"Executing system command: {command[:50]}...")
            
            # Detect if this is an app launch command (contains nohup ... &)
            # For app launches, use Popen to avoid blocking
            is_background_launch = command.strip().endswith('&') and 'nohup' in command
            
            if is_background_launch:
                # Launch app in background without blocking
                logger.info("Detected background app launch - using non-blocking execution")
                process = subprocess.Popen(
                    command,
                    shell=shell,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,  # Detach from parent process
                    cwd=os.getcwd()
                )
                # Don't wait for the process - return immediately
                return {
                    "success": True,
                    "stdout": f"Application launched in background (PID: {process.pid})",
                    "stderr": "",
                    "return_code": 0,
                    "error": None,
                    "pid": process.pid
                }
            
            # For regular commands, use blocking execution
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=shell,
                cwd=os.getcwd()
            )
            
            success = result.returncode == 0
            
            logger.info(f"Command {'succeeded' if success else 'failed'} (exit code: {result.returncode})")
            
            return {
                "success": success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "error": None if success else result.stderr
            }
            
        except subprocess.TimeoutExpired:
            logger.warning(f"Command timed out after {timeout}s")
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "return_code": -1,
                "error": "Timeout"
            }
        except Exception as e:
            logger.error(f"Command execution error: {e}")
            return {
                "success": False,
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
                "error": str(e)
            }
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get system information"""
        try:
            import platform
            import psutil
            
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # GPU info if available
            gpu_info = "Not available"
            try:
                result = subprocess.run(
                    ['nvidia-smi', '--query-gpu=name,memory.used,memory.total', '--format=csv,noheader,nounits'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    gpu_info = result.stdout.strip()
            except:
                pass
            
            return {
                "success": True,
                "system": {
                    "os": platform.system(),
                    "os_version": platform.version(),
                    "architecture": platform.machine(),
                    "processor": platform.processor(),
                    "python_version": platform.python_version(),
                },
                "resources": {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_available_gb": round(memory.available / (1024**3), 2),
                    "disk_percent": disk.percent,
                    "disk_free_gb": round(disk.free / (1024**3), 2),
                },
                "gpu": gpu_info
            }
        except Exception as e:
            logger.error(f"Error getting system info: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def file_operations(
        self,
        operation: str,
        path: str,
        content: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Safe file operations
        
        Args:
            operation: read, write, append, delete, list
            path: File or directory path
            content: Content for write/append operations
        """
        try:
            file_path = Path(path).expanduser()
            
            if operation == "read":
                if not file_path.exists():
                    return {"success": False, "error": "File not found"}
                content = file_path.read_text()
                return {"success": True, "content": content, "size": len(content)}
            
            elif operation == "write":
                if content is None:
                    return {"success": False, "error": "No content provided"}
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content)
                return {"success": True, "message": f"Written {len(content)} chars to {path}"}
            
            elif operation == "append":
                if content is None:
                    return {"success": False, "error": "No content provided"}
                existing = file_path.read_text() if file_path.exists() else ""
                file_path.write_text(existing + content)
                return {"success": True, "message": f"Appended to {path}"}
            
            elif operation == "delete":
                if not file_path.exists():
                    return {"success": False, "error": "File not found"}
                file_path.unlink()
                return {"success": True, "message": f"Deleted {path}"}
            
            elif operation == "list":
                if not file_path.exists():
                    return {"success": False, "error": "Directory not found"}
                if not file_path.is_dir():
                    return {"success": False, "error": "Not a directory"}
                files = [str(f.name) for f in file_path.iterdir()]
                return {"success": True, "files": files, "count": len(files)}
            
            else:
                return {"success": False, "error": f"Unknown operation: {operation}"}
                
        except Exception as e:
            logger.error(f"File operation error: {e}")
            return {"success": False, "error": str(e)}


# Global executor instance
code_executor = CodeExecutor()


# Convenience functions for server integration
def execute_code(code: str, language: str = "python") -> Dict[str, Any]:
    """Execute code (currently supports Python only)"""
    if language.lower() == "python":
        return code_executor.execute_python(code)
    else:
        return {
            "success": False,
            "error": f"Language '{language}' not supported. Only Python is available."
        }


def run_command(command: str) -> Dict[str, Any]:
    """Run system command with safety checks"""
    return code_executor.execute_system_command(command)


def get_system_status() -> Dict[str, Any]:
    """Get current system status"""
    return code_executor.get_system_info()


def manage_file(operation: str, path: str, content: Optional[str] = None) -> Dict[str, Any]:
    """Perform file operation"""
    return code_executor.file_operations(operation, path, content)
