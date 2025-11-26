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
        """Minimize active window or specific app window"""
        if app_name:
            # Try to find window by app name and minimize
            result = self._run_command(f"wmctrl -c '{app_name}'")  # This closes, not minimize
            # Use xdotool to minimize by name
            result = self._run_command(f"xdotool search --name '{app_name}' windowminimize")
            if result["success"]:
                return {"success": True, "message": "Minimized"}
        
        # Minimize active window
        result = self._run_command("xdotool getactivewindow windowminimize")
        if result["success"]:
            return {"success": True, "message": "Minimized"}
        
        # Fallback: use keyboard shortcut
        result = self._run_command("xdotool key super+h")
        if result["success"]:
            return {"success": True, "message": "Minimized"}
        
        return {"success": False, "error": "Could not minimize. Install xdotool."}
    
    def maximize_window(self, app_name: str = None) -> Dict[str, Any]:
        """Maximize active window or specific app window"""
        if app_name:
            result = self._run_command(f"wmctrl -r '{app_name}' -b add,maximized_vert,maximized_horz")
            if result["success"]:
                return {"success": True, "message": "Maximized"}
            
            # Try xdotool
            result = self._run_command(f"xdotool search --name '{app_name}' windowactivate windowsize 100% 100%")
            if result["success"]:
                return {"success": True, "message": "Maximized"}
        
        # Maximize active window
        result = self._run_command("wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz")
        if result["success"]:
            return {"success": True, "message": "Maximized"}
        
        # Fallback: keyboard shortcut
        result = self._run_command("xdotool key super+Up")
        if result["success"]:
            return {"success": True, "message": "Maximized"}
        
        return {"success": False, "error": "Could not maximize. Install wmctrl."}
    
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
        """Close an application by name"""
        result = self._run_command(f"pkill -f '{app_name}'")
        if result["success"]:
            return {"success": True, "message": "Closed"}
        
        result = self._run_command(f"wmctrl -c '{app_name}'")
        if result["success"]:
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
        
        else:
            return {"success": False, "error": f"Unknown action: {action}"}


# Global instance
system_control = SystemControl()
