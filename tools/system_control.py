"""
System Control Tool for JARVIS
Provides OS-level controls: volume, brightness, screenshots, power management, etc.
"""
import subprocess
import os
from typing import Dict, Any, Optional
from core.logger import setup_logger

logger = setup_logger(__name__)


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
        """
        action = action.lower().strip().replace(' ', '_')
        
        # Volume controls
        if action == 'volume_up':
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
