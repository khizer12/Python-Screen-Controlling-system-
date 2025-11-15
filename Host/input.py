import socket
import threading
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

class CrossPlatformInputForwarder:
    def __init__(self, control_port: int = 5556):
        self.control_port = control_port
        self.running = False
        self.socket = None
        self.client_address = None
        
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
        
        # Platform-specific key mappings
        self.key_mappings = self._setup_key_mappings()
    
    def _setup_key_mappings(self):
        """Setup platform-specific key mappings"""
        if self.platform == "darwin":
            return {
                'cmd': 'super',
                'cmd_l': 'super',
                'cmd_r': 'super',
            }
        else:
            return {}
    
    def connect(self, client_ip: str):
        """Connect to client for input forwarding"""
        try:
            self.client_address = (client_ip, self.control_port)
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
            
            if self.input_enabled:
                self._start_input_listeners()
            else:
                print("Input forwarding not available")
            
            return True
        except Exception as e:
            print(f"Input forwarder connection error: {e}")
            return False
    
    def set_scaling(self, host_width: int, host_height: int, client_width: int, client_height: int):
        """Set scaling for coordinate conversion"""
        self.scale_x = host_width / client_width
        self.scale_y = host_height / client_height
    
    def _scale_coordinates(self, x: int, y: int) -> tuple:
        """Scale coordinates from client to host resolution"""
        scaled_x = int(x * self.scale_x)
        scaled_y = int(y * self.scale_y)
        return scaled_x, scaled_y
    
    def _start_input_listeners(self):
        """Start listening for input events"""
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
        """Send input event to client"""
        if self.socket and self.client_address:
            try:
                data = json.dumps(event_data).encode('utf-8')
                self.socket.sendto(data, self.client_address)
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
        
        # Simulate on host if available
        if PYAUTOGUI_AVAILABLE:
            try:
                if pressed:
                    pyautogui.mouseDown(x, y, button=button_name)
                else:
                    pyautogui.mouseUp(x, y, button=button_name)
            except Exception as e:
                print(f"Mouse simulation error: {e}")
    
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
        
        # Simulate on host if available
        if PYAUTOGUI_AVAILABLE:
            try:
                pyautogui.scroll(dy)
            except Exception as e:
                print(f"Scroll simulation error: {e}")
    
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
            
            # Simulate on host if available
            if PYAUTOGUI_AVAILABLE:
                try:
                    pyautogui.keyDown(key_str)
                except Exception as e:
                    print(f"Key press simulation error: {e}")
            
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
            
            # Simulate on host if available
            if PYAUTOGUI_AVAILABLE:
                try:
                    pyautogui.keyUp(key_str)
                except Exception as e:
                    print(f"Key release simulation error: {e}")
            
        except Exception as e:
            print(f"Key release error: {e}")
    
    def _key_to_string(self, key) -> str:
        """Convert key to string representation with platform mapping"""
        if hasattr(key, 'char') and key.char is not None:
            return key.char
        else:
            key_str = str(key).replace('Key.', '')
            # Apply platform-specific mappings
            return self.key_mappings.get(key_str, key_str)
    
    def disconnect(self):
        """Disconnect input forwarder"""
        self.running = False
        
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.socket:
            self.socket.close()