import socket
import json
import time
from typing import Dict, Any
import platform

# Conditional imports for cross-platform compatibility
try:
    from pynput import mouse, keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    print("pynput not available - input forwarding disabled")

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    print("pyautogui not available - input simulation disabled")

class CrossPlatformInputSender:
    def __init__(self, control_port: int = 5556):
        self.control_port = control_port
        self.host_ip = None
        self.socket = None
        self.mouse_listener = None
        self.keyboard_listener = None
        
        # Input state tracking
        self.mouse_position = (0, 0)
        self.pressed_keys = set()
        
        # Scaling factors
        self.scale_x = 1.0
        self.scale_y = 1.0
        
        # Platform-specific attributes
        self.platform = platform.system().lower()
        self.input_enabled = PYNPUT_AVAILABLE
        
        if not self.input_enabled:
            print("Input forwarding disabled - install pynput to enable")
    
    def set_scaling(self, display_width: int, display_height: int, stream_width: int, stream_height: int):
        """Set scaling for coordinate conversion"""
        self.scale_x = display_width / stream_width
        self.scale_y = display_height / stream_height
    
    def _scale_coordinates(self, x: int, y: int) -> tuple:
        """Scale coordinates from display to stream resolution"""
        scaled_x = int(x * self.scale_x)
        scaled_y = int(y * self.scale_y)
        return scaled_x, scaled_y
    
    def connect(self, host_ip: str):
        """Connect to host input receiver"""
        self.host_ip = host_ip
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        if self.input_enabled:
            self._start_input_listeners()
        else:
            print("Input forwarding not available")
    
    def _start_input_listeners(self):
        """Start listening for input events"""
        if not self.input_enabled:
            return
            
        self.running = True
        
        # Mouse listener
        self.mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll
        )
        
        # Keyboard listener
        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        
        self.mouse_listener.start()
        self.keyboard_listener.start()
        
        print("Input listeners started")
    
    def _send_input_event(self, event_data: Dict[str, Any]):
        """Send input event to host"""
        if self.socket and self.host_ip:
            try:
                data = json.dumps(event_data).encode('utf-8')
                self.socket.sendto(data, (self.host_ip, self.control_port))
            except Exception as e:
                print(f"Input send error: {e}")
    
    def _on_mouse_move(self, x: int, y: int):
        """Handle mouse movement"""
        self.mouse_position = (x, y)
        
        event = {
            'type': 'mouse',
            'action': 'move',
            'x': x,
            'y': y,
            'timestamp': time.time()
        }
        self._send_input_event(event)
    
    def _on_mouse_click(self, x: int, y: int, button, pressed: bool):
        """Handle mouse clicks"""
        button_name = str(button).replace('Button.', '')
        
        event = {
            'type': 'mouse',
            'action': 'press' if pressed else 'release',
            'button': button_name,
            'x': x,
            'y': y,
            'timestamp': time.time()
        }
        self._send_input_event(event)
    
    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int):
        """Handle mouse scroll"""
        event = {
            'type': 'mouse',
            'action': 'scroll',
            'x': x,
            'y': y,
            'dx': dx,
            'dy': dy,
            'timestamp': time.time()
        }
        self._send_input_event(event)
    
    def _on_key_press(self, key):
        """Handle key press"""
        try:
            key_str = self._key_to_string(key)
            self.pressed_keys.add(key_str)
            
            event = {
                'type': 'keyboard',
                'action': 'press',
                'key': key_str,
                'timestamp': time.time()
            }
            self._send_input_event(event)
            
        except Exception as e:
            print(f"Key press error: {e}")
    
    def _on_key_release(self, key):
        """Handle key release"""
        try:
            key_str = self._key_to_string(key)
            self.pressed_keys.discard(key_str)
            
            event = {
                'type': 'keyboard',
                'action': 'release',
                'key': key_str,
                'timestamp': time.time()
            }
            self._send_input_event(event)
            
        except Exception as e:
            print(f"Key release error: {e}")
    
    def _key_to_string(self, key) -> str:
        """Convert key to string representation"""
        if hasattr(key, 'char') and key.char is not None:
            return key.char
        else:
            # Handle special keys
            key_str = str(key).replace('Key.', '')
            
            # Platform-specific key mappings
            if self.platform == 'darwin' and key_str == 'cmd':
                key_str = 'super'
            
            return key_str
    
    def disconnect(self):
        """Disconnect input sender"""
        self.running = False
        
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.socket:
            self.socket.close()