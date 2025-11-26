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
        """
        Take a screenshot
        area: 'full' for full screen, 'window' for active window, 'select' for selection
        """
        if filename is None:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"~/Pictures/screenshot_{timestamp}.png"
        
        filename = os.path.expanduser(filename)
        
        # Try gnome-screenshot first
        if area == "full":
            result = self._run_command(f"gnome-screenshot -f {filename}")
        elif area == "window":
            result = self._run_command(f"gnome-screenshot -w -f {filename}")
        elif area == "select":
            result = self._run_command(f"gnome-screenshot -a -f {filename}")
        else:
            result = self._run_command(f"gnome-screenshot -f {filename}")
        
        if result["success"]:
            return {"success": True, "message": f"Screenshot saved to {filename}", "path": filename}
        
        # Fallback to scrot
        if area == "full":
            result = self._run_command(f"scrot {filename}")
        elif area == "window":
            result = self._run_command(f"scrot -u {filename}")
        elif area == "select":
            result = self._run_command(f"scrot -s {filename}")
        
        if result["success"]:
            return {"success": True, "message": f"Screenshot saved to {filename}", "path": filename}
        
        return {"success": False, "error": "Failed to take screenshot. Install gnome-screenshot or scrot."}
    
    # ==================== POWER MANAGEMENT ====================
    
    def lock_screen(self) -> Dict[str, Any]:
        """Lock the screen"""
        # Try multiple lock commands
        commands = [
            "gnome-screensaver-command -l",
            "xdg-screensaver lock",
            "loginctl lock-session",
            "dm-tool lock"
        ]
        
        for cmd in commands:
            result = self._run_command(cmd)
            if result["success"]:
                return {"success": True, "message": "Screen locked"}
        
        return {"success": False, "error": "Failed to lock screen"}
    
    def suspend(self) -> Dict[str, Any]:
        """Suspend the system (sleep)"""
        result = self._run_command("systemctl suspend")
        if result["success"]:
            return {"success": True, "message": "System suspended"}
        return {"success": False, "error": "Failed to suspend. May need sudo."}
    
    def shutdown(self, delay: int = 0) -> Dict[str, Any]:
        """Shutdown the system"""
        if delay > 0:
            result = self._run_command(f"shutdown +{delay}")
        else:
            result = self._run_command("shutdown now")
        
        if result["success"]:
            return {"success": True, "message": f"System will shutdown" + (f" in {delay} minutes" if delay else " now")}
        return {"success": False, "error": "Failed to shutdown. May need sudo."}
    
    def restart(self, delay: int = 0) -> Dict[str, Any]:
        """Restart the system"""
        if delay > 0:
            result = self._run_command(f"shutdown -r +{delay}")
        else:
            result = self._run_command("shutdown -r now")
        
        if result["success"]:
            return {"success": True, "message": f"System will restart" + (f" in {delay} minutes" if delay else " now")}
        return {"success": False, "error": "Failed to restart. May need sudo."}
    
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
