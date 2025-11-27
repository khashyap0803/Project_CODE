"""
System Control Tool for JARVIS
Provides OS-level controls: volume, brightness, screenshots, power management, etc.
"""
import subprocess
import os
import datetime
import threading
from typing import Dict, Any, Optional
from core.logger import setup_logger

logger = setup_logger(__name__)

# Global storage for timers/reminders
_active_timers = {}
_active_reminders = {}
_active_alarms = {}
_timer_counter = 0
_stopwatch_start = None
_stopwatch_running = False


class SystemControl:
    """System-level controls for JARVIS voice assistant"""
    
    def __init__(self):
        logger.info("SystemControl initialized")
    
    def _run_command(self, command: str, timeout: int = 10) -> Dict[str, Any]:
        """Run a shell command and return result"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "code": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # ==================== VOLUME CONTROLS ====================
    
    def _get_volume_backend(self) -> str:
        """Detect audio backend: wpctl (PipeWire), pactl (PulseAudio), or amixer (ALSA)"""
        # Check for PipeWire (wpctl)
        result = self._run_command("which wpctl")
        if result["success"]:
            # Verify wpctl works
            test = self._run_command("wpctl get-volume @DEFAULT_AUDIO_SINK@")
            if test["success"]:
                return "wpctl"
        
        # Check for PulseAudio (pactl)
        result = self._run_command("which pactl")
        if result["success"]:
            return "pactl"
        
        # Fallback to ALSA (amixer)
        return "amixer"
    
    def volume_up(self, amount: int = 10) -> Dict[str, Any]:
        """Increase system volume"""
        backend = self._get_volume_backend()
        
        if backend == "wpctl":
            # wpctl uses decimal values (0.1 = 10%)
            result = self._run_command(f"wpctl set-volume @DEFAULT_AUDIO_SINK@ {amount}%+")
        elif backend == "pactl":
            result = self._run_command(f"pactl set-sink-volume @DEFAULT_SINK@ +{amount}%")
        else:
            result = self._run_command(f"amixer -D pulse sset Master {amount}%+")
        
        if result["success"]:
            return {"success": True, "message": f"Volume increased by {amount}%"}
        return {"success": False, "error": result.get("error", "Failed to increase volume")}
    
    def volume_down(self, amount: int = 10) -> Dict[str, Any]:
        """Decrease system volume"""
        backend = self._get_volume_backend()
        
        if backend == "wpctl":
            result = self._run_command(f"wpctl set-volume @DEFAULT_AUDIO_SINK@ {amount}%-")
        elif backend == "pactl":
            result = self._run_command(f"pactl set-sink-volume @DEFAULT_SINK@ -{amount}%")
        else:
            result = self._run_command(f"amixer -D pulse sset Master {amount}%-")
        
        if result["success"]:
            return {"success": True, "message": f"Volume decreased by {amount}%"}
        return {"success": False, "error": result.get("error", "Failed to decrease volume")}
    
    def volume_set(self, level: int) -> Dict[str, Any]:
        """Set system volume to specific level (0-100)"""
        level = max(0, min(100, level))
        backend = self._get_volume_backend()
        
        if backend == "wpctl":
            # wpctl uses decimal (0.5 = 50%)
            decimal_level = level / 100
            result = self._run_command(f"wpctl set-volume @DEFAULT_AUDIO_SINK@ {decimal_level}")
        elif backend == "pactl":
            result = self._run_command(f"pactl set-sink-volume @DEFAULT_SINK@ {level}%")
        else:
            result = self._run_command(f"amixer -D pulse sset Master {level}%")
        
        if result["success"]:
            return {"success": True, "message": f"Volume set to {level}%"}
        return {"success": False, "error": result.get("error", "Failed to set volume")}
    
    def volume_mute(self) -> Dict[str, Any]:
        """Mute system volume"""
        backend = self._get_volume_backend()
        
        if backend == "wpctl":
            result = self._run_command("wpctl set-mute @DEFAULT_AUDIO_SINK@ 1")
        elif backend == "pactl":
            result = self._run_command("pactl set-sink-mute @DEFAULT_SINK@ true")
        else:
            result = self._run_command("amixer -D pulse sset Master mute")
        
        if result["success"]:
            return {"success": True, "message": "System muted"}
        return {"success": False, "error": result.get("error", "Failed to mute")}
    
    def volume_unmute(self) -> Dict[str, Any]:
        """Unmute system volume"""
        backend = self._get_volume_backend()
        
        if backend == "wpctl":
            result = self._run_command("wpctl set-mute @DEFAULT_AUDIO_SINK@ 0")
        elif backend == "pactl":
            result = self._run_command("pactl set-sink-mute @DEFAULT_SINK@ false")
        else:
            result = self._run_command("amixer -D pulse sset Master unmute")
        
        if result["success"]:
            return {"success": True, "message": "System unmuted"}
        return {"success": False, "error": result.get("error", "Failed to unmute")}
    
    def volume_toggle_mute(self) -> Dict[str, Any]:
        """Toggle system mute"""
        backend = self._get_volume_backend()
        
        if backend == "wpctl":
            result = self._run_command("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle")
        elif backend == "pactl":
            result = self._run_command("pactl set-sink-mute @DEFAULT_SINK@ toggle")
        else:
            result = self._run_command("amixer -D pulse sset Master toggle")
        
        if result["success"]:
            return {"success": True, "message": "Mute toggled"}
        return {"success": False, "error": result.get("error", "Failed to toggle mute")}
    
    def get_volume(self) -> Dict[str, Any]:
        """Get current volume level"""
        backend = self._get_volume_backend()
        
        if backend == "wpctl":
            result = self._run_command("wpctl get-volume @DEFAULT_AUDIO_SINK@")
            if result["success"] and result["stdout"]:
                # Parse "Volume: 0.50" to "50%"
                try:
                    volume_str = result["stdout"]
                    if "Volume:" in volume_str:
                        vol = float(volume_str.split(":")[1].strip().split()[0])
                        vol_percent = int(vol * 100)
                        muted = "[MUTED]" in volume_str
                        status = f"{vol_percent}%" + (" (muted)" if muted else "")
                        return {"success": True, "volume": status, "message": f"Current volume: {status}"}
                except:
                    pass
        elif backend == "pactl":
            result = self._run_command("pactl get-sink-volume @DEFAULT_SINK@ | grep -oP '\\d+%' | head -1")
            if result["success"] and result["stdout"]:
                return {"success": True, "volume": result["stdout"], "message": f"Current volume: {result['stdout']}"}
        else:
            result = self._run_command("amixer -D pulse sget Master | grep -oP '\\d+%' | head -1")
            if result["success"] and result["stdout"]:
                return {"success": True, "volume": result["stdout"], "message": f"Current volume: {result['stdout']}"}
        
        return {"success": False, "error": "Could not get volume level"}
    
    # ==================== BRIGHTNESS CONTROLS ====================
    
    def brightness_up(self, amount: int = 10) -> Dict[str, Any]:
        """Increase screen brightness"""
        # Try brightnessctl first, then xrandr
        result = self._run_command(f"brightnessctl set +{amount}%")
        if result["success"]:
            return {"success": True, "message": f"Brightness increased by {amount}%"}
        
        # Fallback to xrandr (software brightness)
        result = self._run_command("xrandr --output $(xrandr | grep ' connected' | head -1 | cut -d' ' -f1) --brightness 1.0")
        if result["success"]:
            return {"success": True, "message": "Brightness increased"}
        return {"success": False, "error": "Failed to increase brightness. Install brightnessctl."}
    
    def brightness_down(self, amount: int = 10) -> Dict[str, Any]:
        """Decrease screen brightness"""
        result = self._run_command(f"brightnessctl set {amount}%-")
        if result["success"]:
            return {"success": True, "message": f"Brightness decreased by {amount}%"}
        return {"success": False, "error": "Failed to decrease brightness. Install brightnessctl."}
    
    def brightness_set(self, level: int) -> Dict[str, Any]:
        """Set brightness to specific level (0-100)"""
        level = max(1, min(100, level))
        result = self._run_command(f"brightnessctl set {level}%")
        if result["success"]:
            return {"success": True, "message": f"Brightness set to {level}%"}
        return {"success": False, "error": "Failed to set brightness. Install brightnessctl."}
    
    # ==================== SCREENSHOT ====================
    
    def take_screenshot(self, filename: str = None, area: str = "full") -> Dict[str, Any]:
        """Take a screenshot - tries multiple methods"""
        if filename is None:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            # Ensure Pictures directory exists
            pictures_dir = os.path.expanduser("~/Pictures")
            os.makedirs(pictures_dir, exist_ok=True)
            filename = f"{pictures_dir}/screenshot_{timestamp}.png"
        else:
            filename = os.path.expanduser(filename)
        
        # Method 1: gnome-screenshot (most common on Ubuntu/GNOME)
        if area == "full":
            result = self._run_command(f"gnome-screenshot -f '{filename}'")
        elif area == "window":
            result = self._run_command(f"gnome-screenshot -w -f '{filename}'")
        elif area == "select":
            result = self._run_command(f"gnome-screenshot -a -f '{filename}'")
        else:
            result = self._run_command(f"gnome-screenshot -f '{filename}'")
        
        if result["success"] and os.path.exists(filename):
            return {"success": True, "message": f"Screenshot saved"}
        
        # Method 2: scrot
        if area == "full":
            result = self._run_command(f"scrot '{filename}'")
        elif area == "window":
            result = self._run_command(f"scrot -u '{filename}'")
        elif area == "select":
            result = self._run_command(f"scrot -s '{filename}'")
        else:
            result = self._run_command(f"scrot '{filename}'")
        
        if result["success"] and os.path.exists(filename):
            return {"success": True, "message": f"Screenshot saved"}
        
        # Method 3: import (ImageMagick)
        result = self._run_command(f"import -window root '{filename}'")
        if result["success"] and os.path.exists(filename):
            return {"success": True, "message": f"Screenshot saved"}
        
        # Method 4: grim (for Wayland)
        result = self._run_command(f"grim '{filename}'")
        if result["success"] and os.path.exists(filename):
            return {"success": True, "message": f"Screenshot saved"}
        
        return {"success": False, "error": "Screenshot failed. Install gnome-screenshot or scrot."}
    
    # ==================== POWER MANAGEMENT ====================
    
    def lock_screen(self) -> Dict[str, Any]:
        """Lock the screen - tries multiple methods"""
        # Method 1: GNOME screensaver
        result = self._run_command("gnome-screensaver-command -l")
        if result["success"]:
            return {"success": True, "message": "Locked"}
        
        # Method 2: loginctl (systemd)
        result = self._run_command("loginctl lock-session")
        if result["success"]:
            return {"success": True, "message": "Locked"}
        
        # Method 3: xdg-screensaver
        result = self._run_command("xdg-screensaver lock")
        if result["success"]:
            return {"success": True, "message": "Locked"}
        
        # Method 4: dbus
        result = self._run_command("dbus-send --type=method_call --dest=org.gnome.ScreenSaver /org/gnome/ScreenSaver org.gnome.ScreenSaver.Lock")
        if result["success"]:
            return {"success": True, "message": "Locked"}
        
        # Method 5: dm-tool
        result = self._run_command("dm-tool lock")
        if result["success"]:
            return {"success": True, "message": "Locked"}
        
        return {"success": False, "error": "Could not lock screen"}
    
    def suspend(self) -> Dict[str, Any]:
        """Suspend/sleep the system"""
        # Method 1: systemctl (most reliable)
        result = self._run_command("systemctl suspend")
        if result["success"]:
            return {"success": True, "message": "Suspending"}
        
        # Method 2: pm-suspend
        result = self._run_command("pm-suspend")
        if result["success"]:
            return {"success": True, "message": "Suspending"}
        
        # Method 3: dbus
        result = self._run_command("dbus-send --system --print-reply --dest=org.freedesktop.login1 /org/freedesktop/login1 org.freedesktop.login1.Manager.Suspend boolean:true")
        if result["success"]:
            return {"success": True, "message": "Suspending"}
        
        return {"success": False, "error": "Could not suspend. May need sudo."}
    
    def hibernate(self) -> Dict[str, Any]:
        """Hibernate the system"""
        result = self._run_command("systemctl hibernate")
        if result["success"]:
            return {"success": True, "message": "Hibernating"}
        
        result = self._run_command("pm-hibernate")
        if result["success"]:
            return {"success": True, "message": "Hibernating"}
        
        return {"success": False, "error": "Could not hibernate. May not be supported."}
    
    def shutdown(self, delay: int = 0) -> Dict[str, Any]:
        """Shutdown the system"""
        # Use gnome-session-quit for GNOME (shows dialog)
        if delay == 0:
            result = self._run_command("gnome-session-quit --power-off")
            if result["success"]:
                return {"success": True, "message": "Shutting down"}
            
            # Direct shutdown
            result = self._run_command("systemctl poweroff")
            if result["success"]:
                return {"success": True, "message": "Shutting down"}
            
            result = self._run_command("shutdown now")
            if result["success"]:
                return {"success": True, "message": "Shutting down"}
        else:
            result = self._run_command(f"shutdown +{delay}")
            if result["success"]:
                return {"success": True, "message": f"Shutdown in {delay} min"}
        
        return {"success": False, "error": "Could not shutdown. May need sudo."}
    
    def restart(self, delay: int = 0) -> Dict[str, Any]:
        """Restart/reboot the system"""
        if delay == 0:
            result = self._run_command("gnome-session-quit --reboot")
            if result["success"]:
                return {"success": True, "message": "Restarting"}
            
            result = self._run_command("systemctl reboot")
            if result["success"]:
                return {"success": True, "message": "Restarting"}
            
            result = self._run_command("shutdown -r now")
            if result["success"]:
                return {"success": True, "message": "Restarting"}
        else:
            result = self._run_command(f"shutdown -r +{delay}")
            if result["success"]:
                return {"success": True, "message": f"Restart in {delay} min"}
        
        return {"success": False, "error": "Could not restart. May need sudo."}
    
    def cancel_shutdown(self) -> Dict[str, Any]:
        """Cancel scheduled shutdown"""
        result = self._run_command("shutdown -c")
        if result["success"]:
            return {"success": True, "message": "Shutdown cancelled"}
        return {"success": False, "error": "No shutdown scheduled or failed to cancel"}
    
    # ==================== NETWORK CONTROLS ====================
    
    def wifi_on(self) -> Dict[str, Any]:
        """Enable WiFi"""
        result = self._run_command("nmcli radio wifi on")
        if result["success"]:
            return {"success": True, "message": "WiFi enabled"}
        return {"success": False, "error": "Failed to enable WiFi"}
    
    def wifi_off(self) -> Dict[str, Any]:
        """Disable WiFi"""
        result = self._run_command("nmcli radio wifi off")
        if result["success"]:
            return {"success": True, "message": "WiFi disabled"}
        return {"success": False, "error": "Failed to disable WiFi"}
    
    def wifi_status(self) -> Dict[str, Any]:
        """Get WiFi status"""
        result = self._run_command("nmcli radio wifi")
        if result["success"]:
            status = result["stdout"]
            return {"success": True, "status": status, "message": f"WiFi is {status}"}
        return {"success": False, "error": "Failed to get WiFi status"}
    
    def bluetooth_on(self) -> Dict[str, Any]:
        """Enable Bluetooth"""
        result = self._run_command("bluetoothctl power on")
        if result["success"]:
            return {"success": True, "message": "Bluetooth enabled"}
        return {"success": False, "error": "Failed to enable Bluetooth"}
    
    def bluetooth_off(self) -> Dict[str, Any]:
        """Disable Bluetooth"""
        result = self._run_command("bluetoothctl power off")
        if result["success"]:
            return {"success": True, "message": "Bluetooth disabled"}
        return {"success": False, "error": "Failed to disable Bluetooth"}
    
    # ==================== WINDOW MANAGEMENT ====================
    
    def minimize_window(self, app_name: str = None) -> Dict[str, Any]:
        """Minimize active window or specific app window (case-insensitive)"""
        if app_name:
            app_lower = app_name.lower().strip()
            
            # Check if window exists
            check = self._run_command(f"xdotool search --name '{app_lower}'")
            if not check.get("stdout", "").strip():
                # Try wmctrl
                check = self._run_command(f"wmctrl -l | grep -i '{app_lower}'")
                if not check.get("stdout", "").strip():
                    return {"success": False, "error": f"No window found matching '{app_name}'"}
            
            # Method 1: xdotool search with case-insensitive name and minimize
            self._run_command(f"xdotool search --name '{app_lower}' windowminimize")
            return {"success": True, "message": "Minimized"}
        
        # Minimize active window
        self._run_command("xdotool getactivewindow windowminimize")
        return {"success": True, "message": "Minimized"}
    
    def maximize_window(self, app_name: str = None) -> Dict[str, Any]:
        """Maximize active window or specific app window (case-insensitive)"""
        if app_name:
            app_lower = app_name.lower().strip()
            
            # Check if window exists
            check = self._run_command(f"xdotool search --name '{app_lower}'")
            if not check.get("stdout", "").strip():
                # Try wmctrl
                check = self._run_command(f"wmctrl -l | grep -i '{app_lower}'")
                if not check.get("stdout", "").strip():
                    return {"success": False, "error": f"No window found matching '{app_name}'"}
            
            # Activate the window first
            self._run_command(f"xdotool search --name '{app_lower}' windowactivate")
            
            # Now maximize the active window
            self._run_command("wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz")
            return {"success": True, "message": "Maximized"}
        
        # Maximize active window
        self._run_command("wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz")
        return {"success": True, "message": "Maximized"}
    
    def close_window(self, app_name: str = None) -> Dict[str, Any]:
        """Close active window or specific app window"""
        if app_name:
            result = self._run_command(f"wmctrl -c '{app_name}'")
            if result["success"]:
                return {"success": True, "message": "Closed"}
            
            # Try pkill for the app
            result = self._run_command(f"pkill -f '{app_name}'")
            if result["success"]:
                return {"success": True, "message": "Closed"}
        
        # Close active window
        result = self._run_command("xdotool getactivewindow windowclose")
        if result["success"]:
            return {"success": True, "message": "Closed"}
        
        # Fallback: Alt+F4
        result = self._run_command("xdotool key alt+F4")
        if result["success"]:
            return {"success": True, "message": "Closed"}
        
        return {"success": False, "error": "Could not close window"}
    
    def focus_window(self, app_name: str) -> Dict[str, Any]:
        """Bring a window to focus"""
        result = self._run_command(f"wmctrl -a '{app_name}'")
        if result["success"]:
            return {"success": True, "message": f"Focused {app_name}"}
        
        result = self._run_command(f"xdotool search --name '{app_name}' windowactivate")
        if result["success"]:
            return {"success": True, "message": f"Focused {app_name}"}
        
        return {"success": False, "error": f"Could not find {app_name}"}
    
    def list_windows(self) -> Dict[str, Any]:
        """List all open windows"""
        result = self._run_command("wmctrl -l")
        if result["success"]:
            return {"success": True, "windows": result["stdout"], "message": "Windows listed"}
        return {"success": False, "error": "Could not list windows. Install wmctrl."}
    
    # ==================== APP MANAGEMENT ====================
    
    def open_app(self, app_name: str) -> Dict[str, Any]:
        """Open an application"""
        # Common app mappings
        app_commands = {
            "terminal": "gnome-terminal",
            "browser": "xdg-open http://",
            "firefox": "firefox",
            "chrome": "google-chrome",
            "files": "nautilus",
            "file manager": "nautilus",
            "settings": "gnome-control-center",
            "calculator": "gnome-calculator",
            "text editor": "gedit",
            "vscode": "code",
            "vs code": "code",
        }
        
        cmd = app_commands.get(app_name.lower(), app_name)
        
        # Run in background
        try:
            subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return {"success": True, "message": "Opened"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def close_app(self, app_name: str) -> Dict[str, Any]:
        """Close an application by name (case-insensitive partial match)"""
        if not app_name:
            return {"success": False, "error": "No app name provided"}
        
        app_lower = app_name.lower().strip()
        
        # Check if any windows match before trying to close
        check_result = self._run_command(f"xdotool search --name '{app_lower}'")
        windows_before = check_result.get("stdout", "").strip().split("\n") if check_result.get("stdout") else []
        windows_before = [w for w in windows_before if w]  # Remove empty strings
        
        if not windows_before:
            # No windows found matching that name, try wmctrl -l with grep
            check_result = self._run_command(f"wmctrl -l | grep -i '{app_lower}'")
            if not check_result.get("stdout"):
                return {"success": False, "error": f"No window found matching '{app_name}'"}
        
        # Method 1: Try wmctrl -c directly
        self._run_command(f"wmctrl -c '{app_name}'")
        
        # Method 2: Try xdotool search and close (runs on all matching windows)
        self._run_command(f"xdotool search --name '{app_lower}' windowclose")
        
        # Small delay to allow window to close
        import time
        time.sleep(0.3)
        
        # Verify the window is actually closed
        check_result = self._run_command(f"xdotool search --name '{app_lower}'")
        windows_after = check_result.get("stdout", "").strip().split("\n") if check_result.get("stdout") else []
        windows_after = [w for w in windows_after if w]
        
        if len(windows_after) < len(windows_before):
            return {"success": True, "message": "Closed"}
        
        # Method 3: Try pkill with pattern matching (last resort)
        self._run_command(f"pkill -fi '{app_lower}'")
        
        # Final check
        time.sleep(0.2)
        check_result = self._run_command(f"xdotool search --name '{app_lower}'")
        windows_final = check_result.get("stdout", "").strip() if check_result.get("stdout") else ""
        
        if not windows_final:
            return {"success": True, "message": "Closed"}
        
        return {"success": False, "error": f"Could not close {app_name}"}
    
    # ==================== CLIPBOARD ====================
    
    def copy_to_clipboard(self, text: str) -> Dict[str, Any]:
        """Copy text to clipboard"""
        try:
            process = subprocess.Popen(
                ['xclip', '-selection', 'clipboard'],
                stdin=subprocess.PIPE
            )
            process.communicate(input=text.encode())
            if process.returncode == 0:
                return {"success": True, "message": "Text copied to clipboard"}
        except:
            pass
        
        # Fallback to xsel
        try:
            process = subprocess.Popen(
                ['xsel', '--clipboard', '--input'],
                stdin=subprocess.PIPE
            )
            process.communicate(input=text.encode())
            if process.returncode == 0:
                return {"success": True, "message": "Text copied to clipboard"}
        except:
            pass
        
        return {"success": False, "error": "Failed to copy. Install xclip or xsel."}
    
    def get_clipboard(self) -> Dict[str, Any]:
        """Get clipboard content"""
        result = self._run_command("xclip -selection clipboard -o")
        if result["success"]:
            return {"success": True, "content": result["stdout"], "message": "Clipboard content retrieved"}
        
        result = self._run_command("xsel --clipboard --output")
        if result["success"]:
            return {"success": True, "content": result["stdout"], "message": "Clipboard content retrieved"}
        
        return {"success": False, "error": "Failed to get clipboard. Install xclip or xsel."}
    
    # ==================== NOTIFICATIONS ====================
    
    def send_notification(self, title: str, message: str, urgency: str = "normal") -> Dict[str, Any]:
        """Send a desktop notification"""
        result = self._run_command(f'notify-send -u {urgency} "{title}" "{message}"')
        if result["success"]:
            return {"success": True, "message": "Notification sent"}
        return {"success": False, "error": "Failed to send notification. Install libnotify."}
    
    # ==================== FILE MANAGEMENT ====================
    
    def find_file(self, name: str, path: str = "~") -> Dict[str, Any]:
        """Find files by name"""
        path = os.path.expanduser(path)
        result = self._run_command(f"find {path} -name '*{name}*' -type f 2>/dev/null | head -20", timeout=30)
        if result["success"] and result["stdout"]:
            files = result["stdout"].strip().split('\n')
            return {"success": True, "files": files, "message": f"Found {len(files)} file(s)"}
        return {"success": True, "files": [], "message": "No files found"}
    
    def find_large_files(self, min_size: str = "100M", path: str = "~") -> Dict[str, Any]:
        """Find files larger than specified size (e.g., '100M', '1G', '500K')"""
        path = os.path.expanduser(path)
        result = self._run_command(f"find {path} -type f -size +{min_size} -exec ls -lh {{}} \\; 2>/dev/null | head -20", timeout=60)
        if result["success"] and result["stdout"]:
            lines = result["stdout"].strip().split('\n')
            files = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 9:
                    files.append({"size": parts[4], "path": ' '.join(parts[8:])})
            return {"success": True, "files": files, "message": f"Found {len(files)} file(s) > {min_size}"}
        return {"success": True, "files": [], "message": f"No files > {min_size}"}
    
    def create_file(self, filepath: str, content: str = "") -> Dict[str, Any]:
        """Create a new file with optional content"""
        filepath = os.path.expanduser(filepath)
        try:
            # Create parent directories if needed
            parent_dir = os.path.dirname(filepath)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            
            with open(filepath, 'w') as f:
                f.write(content)
            return {"success": True, "message": f"Created {os.path.basename(filepath)}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def delete_file(self, filepath: str) -> Dict[str, Any]:
        """Delete a file (moves to trash if possible)"""
        filepath = os.path.expanduser(filepath)
        if not os.path.exists(filepath):
            return {"success": False, "error": "File not found"}
        
        # Try to move to trash first (safer)
        result = self._run_command(f"gio trash '{filepath}'")
        if result["success"]:
            return {"success": True, "message": "Moved to trash"}
        
        # Fallback: actually delete
        try:
            os.remove(filepath)
            return {"success": True, "message": "Deleted"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def move_file(self, source: str, destination: str) -> Dict[str, Any]:
        """Move/rename a file"""
        source = os.path.expanduser(source)
        destination = os.path.expanduser(destination)
        
        if not os.path.exists(source):
            return {"success": False, "error": "Source not found"}
        
        try:
            import shutil
            shutil.move(source, destination)
            return {"success": True, "message": "Moved"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def copy_file(self, source: str, destination: str) -> Dict[str, Any]:
        """Copy a file"""
        source = os.path.expanduser(source)
        destination = os.path.expanduser(destination)
        
        if not os.path.exists(source):
            return {"success": False, "error": "Source not found"}
        
        try:
            import shutil
            if os.path.isdir(source):
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
            return {"success": True, "message": "Copied"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_file_info(self, filepath: str) -> Dict[str, Any]:
        """Get file information (size, modified date, etc.)"""
        filepath = os.path.expanduser(filepath)
        
        if not os.path.exists(filepath):
            return {"success": False, "error": "File not found"}
        
        try:
            stat = os.stat(filepath)
            import datetime
            size = stat.st_size
            if size >= 1024*1024*1024:
                size_str = f"{size/(1024*1024*1024):.1f} GB"
            elif size >= 1024*1024:
                size_str = f"{size/(1024*1024):.1f} MB"
            elif size >= 1024:
                size_str = f"{size/1024:.1f} KB"
            else:
                size_str = f"{size} bytes"
            
            modified = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            
            return {
                "success": True,
                "path": filepath,
                "size": size_str,
                "modified": modified,
                "is_dir": os.path.isdir(filepath),
                "message": f"{os.path.basename(filepath)}: {size_str}, modified {modified}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def list_directory(self, path: str = ".") -> Dict[str, Any]:
        """List contents of a directory"""
        path = os.path.expanduser(path)
        
        if not os.path.exists(path):
            return {"success": False, "error": "Directory not found"}
        
        if not os.path.isdir(path):
            return {"success": False, "error": "Not a directory"}
        
        try:
            items = []
            for entry in os.listdir(path):
                full_path = os.path.join(path, entry)
                is_dir = os.path.isdir(full_path)
                items.append({"name": entry, "is_dir": is_dir})
            
            return {
                "success": True,
                "path": path,
                "items": items,
                "message": f"{len(items)} items in {path}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def open_file_manager(self, path: str = "~") -> Dict[str, Any]:
        """Open file manager at specified path"""
        path = os.path.expanduser(path)
        
        result = self._run_command(f"xdg-open '{path}'")
        if result["success"]:
            return {"success": True, "message": "Opened"}
        
        result = self._run_command(f"nautilus '{path}'")
        if result["success"]:
            return {"success": True, "message": "Opened"}
        
        return {"success": False, "error": "Could not open file manager"}
    
    # ==================== TIME AND DATE ====================
    
    def get_time(self) -> Dict[str, Any]:
        """Get current time"""
        now = datetime.datetime.now()
        time_str = now.strftime("%I:%M %p")  # 12-hour format with AM/PM
        return {
            "success": True, 
            "time": time_str,
            "message": f"The current time is {time_str}"
        }
    
    def get_date(self) -> Dict[str, Any]:
        """Get current date"""
        now = datetime.datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")  # "Thursday, November 27, 2025"
        return {
            "success": True,
            "date": date_str,
            "message": f"Today is {date_str}"
        }
    
    def get_datetime(self) -> Dict[str, Any]:
        """Get current date and time"""
        now = datetime.datetime.now()
        datetime_str = now.strftime("%A, %B %d, %Y at %I:%M %p")
        return {
            "success": True,
            "datetime": datetime_str,
            "message": f"It is {datetime_str}"
        }
    
    # ==================== TIMERS AND REMINDERS ====================
    
    def set_timer(self, seconds: int, name: str = None) -> Dict[str, Any]:
        """Set a timer for specified seconds"""
        global _timer_counter, _active_timers
        
        _timer_counter += 1
        timer_id = f"timer_{_timer_counter}"
        timer_name = name or f"Timer {_timer_counter}"
        
        def timer_callback():
            # Send notification when timer completes
            self.send_notification("JARVIS Timer", f"{timer_name} completed!", "critical")
            # Play a sound
            self._run_command("paplay /usr/share/sounds/freedesktop/stereo/complete.oga 2>/dev/null || paplay /usr/share/sounds/gnome/default/alerts/glass.ogg 2>/dev/null")
            _active_timers.pop(timer_id, None)
        
        timer = threading.Timer(seconds, timer_callback)
        timer.start()
        _active_timers[timer_id] = {
            "name": timer_name,
            "seconds": seconds,
            "timer": timer,
            "started": datetime.datetime.now()
        }
        
        # Format time nicely
        if seconds >= 3600:
            time_str = f"{seconds // 3600} hour(s) {(seconds % 3600) // 60} minute(s)"
        elif seconds >= 60:
            time_str = f"{seconds // 60} minute(s) {seconds % 60} second(s)"
        else:
            time_str = f"{seconds} second(s)"
        
        return {
            "success": True,
            "timer_id": timer_id,
            "message": f"Timer set for {time_str}"
        }
    
    def cancel_timer(self, timer_id: str = None) -> Dict[str, Any]:
        """Cancel a timer"""
        global _active_timers
        
        if timer_id and timer_id in _active_timers:
            _active_timers[timer_id]["timer"].cancel()
            name = _active_timers.pop(timer_id)["name"]
            return {"success": True, "message": f"Cancelled {name}"}
        elif not timer_id and _active_timers:
            # Cancel most recent timer
            timer_id = list(_active_timers.keys())[-1]
            _active_timers[timer_id]["timer"].cancel()
            name = _active_timers.pop(timer_id)["name"]
            return {"success": True, "message": f"Cancelled {name}"}
        else:
            return {"success": False, "error": "No active timers"}
    
    def list_timers(self) -> Dict[str, Any]:
        """List all active timers"""
        global _active_timers
        
        if not _active_timers:
            return {"success": True, "timers": [], "message": "No active timers"}
        
        timers = []
        now = datetime.datetime.now()
        for tid, info in _active_timers.items():
            elapsed = (now - info["started"]).seconds
            remaining = max(0, info["seconds"] - elapsed)
            timers.append({
                "id": tid,
                "name": info["name"],
                "remaining_seconds": remaining
            })
        
        return {
            "success": True,
            "timers": timers,
            "message": f"{len(timers)} active timer(s)"
        }
    
    def set_reminder(self, message: str, seconds: int) -> Dict[str, Any]:
        """Set a reminder with a custom message"""
        global _active_reminders, _timer_counter
        
        _timer_counter += 1
        reminder_id = f"reminder_{_timer_counter}"
        
        def reminder_callback():
            self.send_notification("JARVIS Reminder", message, "critical")
            self._run_command("paplay /usr/share/sounds/freedesktop/stereo/message.oga 2>/dev/null")
            _active_reminders.pop(reminder_id, None)
        
        timer = threading.Timer(seconds, reminder_callback)
        timer.start()
        _active_reminders[reminder_id] = {
            "message": message,
            "seconds": seconds,
            "timer": timer,
            "started": datetime.datetime.now()
        }
        
        # Format time nicely
        if seconds >= 3600:
            time_str = f"{seconds // 3600} hour(s) {(seconds % 3600) // 60} minute(s)"
        elif seconds >= 60:
            time_str = f"{seconds // 60} minute(s)"
        else:
            time_str = f"{seconds} seconds"
        
        return {
            "success": True,
            "reminder_id": reminder_id,
            "message": f"Reminder set for {time_str}"
        }
    
    def cancel_reminder(self, reminder_id: str = None) -> Dict[str, Any]:
        """Cancel a reminder"""
        global _active_reminders
        
        if reminder_id and reminder_id in _active_reminders:
            _active_reminders[reminder_id]["timer"].cancel()
            msg = _active_reminders.pop(reminder_id)["message"]
            return {"success": True, "message": f"Cancelled reminder: {msg}"}
        elif not reminder_id and _active_reminders:
            # Cancel most recent reminder
            reminder_id = list(_active_reminders.keys())[-1]
            _active_reminders[reminder_id]["timer"].cancel()
            msg = _active_reminders.pop(reminder_id)["message"]
            return {"success": True, "message": f"Cancelled reminder: {msg}"}
        else:
            return {"success": False, "error": "No active reminders"}
    
    def list_reminders(self) -> Dict[str, Any]:
        """List all active reminders"""
        global _active_reminders
        
        if not _active_reminders:
            return {"success": True, "reminders": [], "message": "No active reminders"}
        
        reminders = []
        now = datetime.datetime.now()
        for rid, info in _active_reminders.items():
            elapsed = (now - info["started"]).seconds
            remaining = max(0, info["seconds"] - elapsed)
            reminders.append({
                "id": rid,
                "message": info["message"],
                "remaining_seconds": remaining
            })
        
        return {
            "success": True,
            "reminders": reminders,
            "message": f"{len(reminders)} active reminder(s)"
        }
    
    # ==================== STOPWATCH ====================
    
    def start_stopwatch(self) -> Dict[str, Any]:
        """Start a stopwatch"""
        global _stopwatch_start, _stopwatch_running
        
        if _stopwatch_running:
            return {"success": False, "error": "Stopwatch already running"}
        
        _stopwatch_start = datetime.datetime.now()
        _stopwatch_running = True
        return {"success": True, "message": "Stopwatch started"}
    
    def stop_stopwatch(self) -> Dict[str, Any]:
        """Stop the stopwatch and return elapsed time"""
        global _stopwatch_start, _stopwatch_running
        
        if not _stopwatch_running:
            return {"success": False, "error": "Stopwatch is not running"}
        
        elapsed = datetime.datetime.now() - _stopwatch_start
        _stopwatch_running = False
        
        # Format elapsed time
        total_seconds = int(elapsed.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            time_str = f"{hours} hour(s) {minutes} minute(s) {seconds} second(s)"
        elif minutes > 0:
            time_str = f"{minutes} minute(s) {seconds} second(s)"
        else:
            time_str = f"{seconds} second(s)"
        
        return {
            "success": True,
            "elapsed_seconds": total_seconds,
            "message": f"Stopwatch stopped. Elapsed time: {time_str}"
        }
    
    def reset_stopwatch(self) -> Dict[str, Any]:
        """Reset the stopwatch"""
        global _stopwatch_start, _stopwatch_running
        
        _stopwatch_start = None
        _stopwatch_running = False
        return {"success": True, "message": "Stopwatch reset"}
    
    def get_stopwatch(self) -> Dict[str, Any]:
        """Get current stopwatch time without stopping"""
        global _stopwatch_start, _stopwatch_running
        
        if not _stopwatch_running or _stopwatch_start is None:
            return {"success": False, "error": "Stopwatch is not running"}
        
        elapsed = datetime.datetime.now() - _stopwatch_start
        total_seconds = int(elapsed.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            time_str = f"{hours} hour(s) {minutes} minute(s) {seconds} second(s)"
        elif minutes > 0:
            time_str = f"{minutes} minute(s) {seconds} second(s)"
        else:
            time_str = f"{seconds} second(s)"
        
        return {
            "success": True,
            "elapsed_seconds": total_seconds,
            "message": f"Stopwatch running: {time_str}"
        }
    
    # ==================== ALARMS ====================
    
    def set_alarm(self, hour: int, minute: int = 0, message: str = "Alarm!") -> Dict[str, Any]:
        """Set an alarm for a specific time"""
        global _active_alarms, _timer_counter
        
        _timer_counter += 1
        alarm_id = f"alarm_{_timer_counter}"
        
        # Calculate seconds until alarm
        now = datetime.datetime.now()
        alarm_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # If alarm time is in the past, set for tomorrow
        if alarm_time <= now:
            alarm_time += datetime.timedelta(days=1)
        
        seconds_until = (alarm_time - now).total_seconds()
        
        def alarm_callback():
            self.send_notification("JARVIS Alarm", message, "critical")
            # Play alarm sound multiple times
            for _ in range(3):
                self._run_command("paplay /usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga 2>/dev/null || paplay /usr/share/sounds/gnome/default/alerts/drip.ogg 2>/dev/null")
            _active_alarms.pop(alarm_id, None)
        
        timer = threading.Timer(seconds_until, alarm_callback)
        timer.start()
        _active_alarms[alarm_id] = {
            "time": alarm_time,
            "message": message,
            "timer": timer
        }
        
        time_str = alarm_time.strftime("%I:%M %p")
        return {
            "success": True,
            "alarm_id": alarm_id,
            "message": f"Alarm set for {time_str}"
        }
    
    def cancel_alarm(self, alarm_id: str = None) -> Dict[str, Any]:
        """Cancel an alarm"""
        global _active_alarms
        
        if alarm_id and alarm_id in _active_alarms:
            _active_alarms[alarm_id]["timer"].cancel()
            time_str = _active_alarms.pop(alarm_id)["time"].strftime("%I:%M %p")
            return {"success": True, "message": f"Cancelled alarm for {time_str}"}
        elif not alarm_id and _active_alarms:
            # Cancel most recent alarm
            alarm_id = list(_active_alarms.keys())[-1]
            _active_alarms[alarm_id]["timer"].cancel()
            time_str = _active_alarms.pop(alarm_id)["time"].strftime("%I:%M %p")
            return {"success": True, "message": f"Cancelled alarm for {time_str}"}
        else:
            return {"success": False, "error": "No active alarms"}
    
    def list_alarms(self) -> Dict[str, Any]:
        """List all active alarms"""
        global _active_alarms
        
        if not _active_alarms:
            return {"success": True, "alarms": [], "message": "No active alarms"}
        
        alarms = []
        for aid, info in _active_alarms.items():
            alarms.append({
                "id": aid,
                "time": info["time"].strftime("%I:%M %p"),
                "message": info["message"]
            })
        
        return {
            "success": True,
            "alarms": alarms,
            "message": f"{len(alarms)} active alarm(s)"
        }
    
    # ==================== SYSTEM INFORMATION ====================
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get comprehensive system information"""
        info = {}
        
        # CPU info
        result = self._run_command("grep 'model name' /proc/cpuinfo | head -1 | cut -d':' -f2")
        if result["success"]:
            info["cpu_model"] = result["stdout"].strip()
        
        # CPU usage
        result = self._run_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1")
        if result["success"]:
            info["cpu_usage"] = f"{result['stdout'].strip()}%"
        
        # Memory info
        result = self._run_command("free -h | grep Mem | awk '{print $3\"/\"$2}'")
        if result["success"]:
            info["memory"] = result["stdout"].strip()
        
        # Disk usage
        result = self._run_command("df -h / | tail -1 | awk '{print $3\"/\"$2\" (\"$5\" used)\"}'")
        if result["success"]:
            info["disk"] = result["stdout"].strip()
        
        # Uptime
        result = self._run_command("uptime -p")
        if result["success"]:
            info["uptime"] = result["stdout"].strip()
        
        return {
            "success": True,
            "info": info,
            "message": f"CPU: {info.get('cpu_usage', 'N/A')}, RAM: {info.get('memory', 'N/A')}, Disk: {info.get('disk', 'N/A')}"
        }
    
    def get_cpu_usage(self) -> Dict[str, Any]:
        """Get CPU usage percentage"""
        result = self._run_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2}'")
        if result["success"]:
            usage = result["stdout"].strip().replace('%', '')
            return {
                "success": True,
                "cpu_usage": f"{usage}%",
                "message": f"CPU usage is {usage}%"
            }
        return {"success": False, "error": "Could not get CPU usage"}
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """Get memory/RAM usage"""
        result = self._run_command("free -h | grep Mem")
        if result["success"]:
            parts = result["stdout"].split()
            if len(parts) >= 3:
                total = parts[1]
                used = parts[2]
                return {
                    "success": True,
                    "total": total,
                    "used": used,
                    "message": f"Memory: {used} used of {total}"
                }
        return {"success": False, "error": "Could not get memory usage"}
    
    def get_gpu_status(self) -> Dict[str, Any]:
        """Get GPU status (NVIDIA)"""
        result = self._run_command("nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null")
        if result["success"] and result["stdout"]:
            parts = result["stdout"].split(',')
            if len(parts) >= 5:
                name = parts[0].strip()
                temp = parts[1].strip()
                util = parts[2].strip()
                mem_used = parts[3].strip()
                mem_total = parts[4].strip()
                return {
                    "success": True,
                    "gpu_name": name,
                    "temperature": f"{temp}°C",
                    "utilization": f"{util}%",
                    "memory": f"{mem_used}MB / {mem_total}MB",
                    "message": f"GPU: {util}% usage, {temp}°C, {mem_used}MB/{mem_total}MB"
                }
        
        # Try AMD GPU
        result = self._run_command("rocm-smi --showtemp --showuse 2>/dev/null | head -5")
        if result["success"] and result["stdout"]:
            return {
                "success": True,
                "info": result["stdout"],
                "message": "AMD GPU detected"
            }
        
        return {"success": False, "error": "No GPU info available (install nvidia-smi or rocm-smi)"}
    
    def get_battery_status(self) -> Dict[str, Any]:
        """Get battery status (for laptops)"""
        result = self._run_command("upower -i /org/freedesktop/UPower/devices/battery_BAT0 2>/dev/null | grep -E 'state|percentage|time'")
        if result["success"] and result["stdout"]:
            lines = result["stdout"].strip().split('\n')
            info = {}
            for line in lines:
                if ':' in line:
                    key, val = line.split(':', 1)
                    info[key.strip()] = val.strip()
            return {
                "success": True,
                "info": info,
                "message": f"Battery: {info.get('percentage', 'N/A')} ({info.get('state', 'N/A')})"
            }
        return {"success": True, "message": "No battery detected (desktop system)"}
    
    def get_disk_usage(self) -> Dict[str, Any]:
        """Get disk usage"""
        result = self._run_command("df -h / | tail -1")
        if result["success"]:
            parts = result["stdout"].split()
            if len(parts) >= 5:
                return {
                    "success": True,
                    "total": parts[1],
                    "used": parts[2],
                    "available": parts[3],
                    "percentage": parts[4],
                    "message": f"Disk: {parts[2]} used of {parts[1]} ({parts[4]})"
                }
        return {"success": False, "error": "Could not get disk usage"}
    
    def get_network_info(self) -> Dict[str, Any]:
        """Get network information"""
        info = {}
        
        # Get IP address
        result = self._run_command("hostname -I | awk '{print $1}'")
        if result["success"]:
            info["ip_address"] = result["stdout"].strip()
        
        # Get public IP
        result = self._run_command("curl -s ifconfig.me 2>/dev/null", timeout=5)
        if result["success"]:
            info["public_ip"] = result["stdout"].strip()
        
        # Get active connection
        result = self._run_command("nmcli -t -f NAME,TYPE,DEVICE connection show --active | head -1")
        if result["success"]:
            info["connection"] = result["stdout"].strip()
        
        return {
            "success": True,
            "info": info,
            "message": f"IP: {info.get('ip_address', 'N/A')}"
        }
    
    # ==================== GENERAL SYSTEM CONTROL ====================
    
    def execute_control(self, action: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a system control action
        
        Actions:
        - volume_up, volume_down, volume_set, volume_mute, volume_unmute, get_volume
        - brightness_up, brightness_down, brightness_set
        - screenshot
        - lock, suspend, shutdown, restart, cancel_shutdown
        - wifi_on, wifi_off, wifi_status
        - bluetooth_on, bluetooth_off
        - copy, paste/get_clipboard
        - notify
        - get_time, get_date, get_datetime
        - set_timer, cancel_timer, list_timers
        - set_reminder
        - get_system_info, get_cpu_usage, get_memory_usage, get_gpu_status, get_disk_usage
        """
        action = action.lower().strip().replace(' ', '_')
        
        # Time and date
        if action in ['get_time', 'time', 'what_time']:
            return self.get_time()
        elif action in ['get_date', 'date', 'what_date']:
            return self.get_date()
        elif action in ['get_datetime', 'datetime']:
            return self.get_datetime()
        
        # Timers
        elif action in ['set_timer', 'timer']:
            return self.set_timer(kwargs.get('seconds', 60), kwargs.get('name'))
        elif action == 'cancel_timer':
            return self.cancel_timer(kwargs.get('timer_id'))
        elif action == 'list_timers':
            return self.list_timers()
        
        # Reminders
        elif action in ['set_reminder', 'reminder']:
            return self.set_reminder(kwargs.get('message', 'Reminder'), kwargs.get('seconds', 60))
        elif action == 'cancel_reminder':
            return self.cancel_reminder(kwargs.get('reminder_id'))
        elif action == 'list_reminders':
            return self.list_reminders()
        
        # Stopwatch
        elif action == 'start_stopwatch':
            return self.start_stopwatch()
        elif action == 'stop_stopwatch':
            return self.stop_stopwatch()
        elif action == 'reset_stopwatch':
            return self.reset_stopwatch()
        elif action == 'get_stopwatch':
            return self.get_stopwatch()
        
        # Alarms
        elif action == 'set_alarm':
            return self.set_alarm(kwargs.get('hour', 8), kwargs.get('minute', 0), kwargs.get('message', 'Alarm!'))
        elif action == 'cancel_alarm':
            return self.cancel_alarm(kwargs.get('alarm_id'))
        elif action == 'list_alarms':
            return self.list_alarms()
        
        # System info
        elif action in ['get_system_info', 'system_info', 'system_status']:
            return self.get_system_info()
        elif action in ['get_cpu_usage', 'cpu_usage', 'cpu']:
            return self.get_cpu_usage()
        elif action in ['get_memory_usage', 'memory_usage', 'ram', 'memory']:
            return self.get_memory_usage()
        elif action in ['get_gpu_status', 'gpu_status', 'gpu']:
            return self.get_gpu_status()
        elif action in ['get_battery', 'battery', 'battery_status']:
            return self.get_battery_status()
        elif action in ['get_disk_usage', 'disk_usage', 'disk']:
            return self.get_disk_usage()
        elif action in ['get_network_info', 'network_info', 'network', 'ip']:
            return self.get_network_info()
        
        # Volume controls
        elif action == 'volume_up':
            return self.volume_up(kwargs.get('amount', 10))
        elif action == 'volume_down':
            return self.volume_down(kwargs.get('amount', 10))
        elif action == 'volume_set':
            return self.volume_set(kwargs.get('level', 50))
        elif action in ['mute', 'volume_mute']:
            return self.volume_mute()
        elif action in ['unmute', 'volume_unmute']:
            return self.volume_unmute()
        elif action == 'toggle_mute':
            return self.volume_toggle_mute()
        elif action == 'get_volume':
            return self.get_volume()
        
        # Brightness controls
        elif action == 'brightness_up':
            return self.brightness_up(kwargs.get('amount', 10))
        elif action == 'brightness_down':
            return self.brightness_down(kwargs.get('amount', 10))
        elif action == 'brightness_set':
            return self.brightness_set(kwargs.get('level', 50))
        
        # Screenshot
        elif action == 'screenshot':
            return self.take_screenshot(kwargs.get('filename'), kwargs.get('area', 'full'))
        
        # Power management
        elif action in ['lock', 'lock_screen']:
            return self.lock_screen()
        elif action in ['sleep', 'suspend']:
            return self.suspend()
        elif action == 'hibernate':
            return self.hibernate()
        elif action == 'shutdown':
            return self.shutdown(kwargs.get('delay', 0))
        elif action in ['restart', 'reboot']:
            return self.restart(kwargs.get('delay', 0))
        elif action == 'cancel_shutdown':
            return self.cancel_shutdown()
        
        # Network
        elif action == 'wifi_on':
            return self.wifi_on()
        elif action == 'wifi_off':
            return self.wifi_off()
        elif action == 'wifi_status':
            return self.wifi_status()
        elif action == 'bluetooth_on':
            return self.bluetooth_on()
        elif action == 'bluetooth_off':
            return self.bluetooth_off()
        
        # Window management
        elif action == 'minimize_window':
            return self.minimize_window(kwargs.get('app_name'))
        elif action == 'maximize_window':
            return self.maximize_window(kwargs.get('app_name'))
        elif action == 'close_window':
            return self.close_window(kwargs.get('app_name'))
        elif action == 'focus_window':
            return self.focus_window(kwargs.get('app_name', ''))
        elif action == 'list_windows':
            return self.list_windows()
        
        # App management
        elif action == 'open_app':
            return self.open_app(kwargs.get('app_name', ''))
        elif action == 'close_app':
            return self.close_app(kwargs.get('app_name', ''))
        
        # Clipboard
        elif action == 'copy':
            return self.copy_to_clipboard(kwargs.get('text', ''))
        elif action in ['paste', 'get_clipboard']:
            return self.get_clipboard()
        
        # Notifications
        elif action == 'notify':
            return self.send_notification(
                kwargs.get('title', 'JARVIS'),
                kwargs.get('message', ''),
                kwargs.get('urgency', 'normal')
            )
        
        # File management
        elif action == 'find_file':
            return self.find_file(kwargs.get('name', ''), kwargs.get('path', '~'))
        elif action == 'find_large_files':
            return self.find_large_files(kwargs.get('min_size', '100M'), kwargs.get('path', '~'))
        elif action == 'create_file':
            return self.create_file(kwargs.get('filepath', ''), kwargs.get('content', ''))
        elif action == 'delete_file':
            return self.delete_file(kwargs.get('filepath', ''))
        elif action == 'move_file':
            return self.move_file(kwargs.get('source', ''), kwargs.get('destination', ''))
        elif action == 'copy_file':
            return self.copy_file(kwargs.get('source', ''), kwargs.get('destination', ''))
        elif action == 'file_info':
            return self.get_file_info(kwargs.get('filepath', ''))
        elif action == 'list_dir':
            return self.list_directory(kwargs.get('path', '.'))
        elif action == 'open_file_manager':
            return self.open_file_manager(kwargs.get('path', '~'))
        
        else:
            return {"success": False, "error": f"Unknown action: {action}"}


# Global instance
system_control = SystemControl()
