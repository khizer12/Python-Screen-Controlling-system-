import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import queue
import json
import socket
import platform
import sys
import os
import subprocess
from typing import Optional, Callable

# ========== PLATFORM-SPECIFIC IMPORTS ==========
try:
    import cv2
    import numpy as np
    from PIL import Image, ImageTk
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("OpenCV/PIL not available - video display disabled")

try:
    from pynput import mouse, keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    print("pynput not available - input forwarding disabled")

# ========== CONFIGURATION ==========
class StreamConfig:
    def __init__(self):
        self.width = 1280
        self.height = 720
        self.fps = 30
        self.bitrate = "1M"

class NetworkConfig:
    def __init__(self):
        self.video_port = 5555
        self.control_port = 5556
        self.discovery_port = 5557

class ConfigManager:
    def __init__(self):
        self.stream_config = StreamConfig()
        self.network_config = NetworkConfig()

# ========== FFMPEG VIDEO RECEIVER ==========
class FFmpegVideoReceiver:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.connected = False
        self.running = False
        self.frame_queue = queue.Queue(maxsize=10)
        self.current_frame = None
        self.fps = 0
        self.frame_count = 0
        self.fps_update_time = time.time()
        self.on_frame_callback = None
        self.ffmpeg_process = None
        self.decoder_thread = None
        
        self.platform = platform.system().lower()
        print(f"Platform: {self.platform}")
        
    def connect(self, host_ip: str) -> bool:
        """Connect to host using FFmpeg for H.264 decoding"""
        try:
            self.running = True
            self.connected = True
            
            # Start FFmpeg in a thread
            self.decoder_thread = threading.Thread(
                target=self._ffmpeg_receive_loop, 
                args=(host_ip,),
                daemon=True
            )
            self.decoder_thread.start()
            
            print(f"✅ FFmpeg receiver started for {host_ip}")
            return True
            
        except Exception as e:
            print(f"❌ FFmpeg connection failed: {e}")
            return False
    
    def _ffmpeg_receive_loop(self, host_ip):
        """FFmpeg reception and decoding loop"""
        width = self.config_manager.stream_config.width
        height = self.config_manager.stream_config.height
        port = self.config_manager.network_config.video_port
        frame_size = width * height * 3  # BGR24 format
        
        # FFmpeg command to receive UDP stream and decode to raw video
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', f'udp://{host_ip}:{port}?timeout=5000000',
            '-f', 'rawvideo',
            '-pix_fmt', 'bgr24',
            '-vcodec', 'rawvideo',
            '-fflags', 'nobuffer',
            '-flags', 'low_delay',
            '-avioflags', 'direct',
            'pipe:1'
        ]
        
        try:
            print(f"🎬 Starting FFmpeg: {' '.join(ffmpeg_cmd)}")
            
            self.ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=frame_size * 5
            )
            
            print("✅ FFmpeg process started successfully")
            
            # Start stderr reader thread
            stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
            stderr_thread.start()
            
            while self.running and self.ffmpeg_process.poll() is None:
                try:
                    # Read raw frame data from FFmpeg
                    raw_frame = self.ffmpeg_process.stdout.read(frame_size)
                    
                    if len(raw_frame) == frame_size:
                        # Convert to numpy array and reshape
                        frame = np.frombuffer(raw_frame, np.uint8)
                        frame = frame.reshape((height, width, 3))
                        self._handle_decoded_frame(frame)
                    else:
                        # Incomplete frame or no data
                        if len(raw_frame) == 0:
                            time.sleep(0.001)
                        else:
                            print(f"⚠️ Incomplete frame: {len(raw_frame)}/{frame_size} bytes")
                            
                except Exception as e:
                    print(f"FFmpeg frame error: {e}")
                    time.sleep(0.01)
                    
        except Exception as e:
            print(f"❌ FFmpeg process error: {e}")
            self.connected = False
            self._create_error_frame(f"FFmpeg Error: {str(e)}")
        finally:
            if self.ffmpeg_process:
                self.ffmpeg_process.terminate()
    
    def _read_stderr(self):
        """Read FFmpeg stderr for debugging"""
        while self.running and self.ffmpeg_process and self.ffmpeg_process.poll() is None:
            try:
                line = self.ffmpeg_process.stderr.readline()
                if line:
                    print(f"FFmpeg (client): {line.decode().strip()}")
            except:
                break
    
    def _handle_decoded_frame(self, frame):
        """Handle successfully decoded frame"""
        self.current_frame = frame
        self.frame_count += 1
        
        # Update FPS counter
        current_time = time.time()
        if current_time - self.fps_update_time >= 1.0:
            self.fps = self.frame_count
            self.frame_count = 0
            self.fps_update_time = current_time
        
        # Put in queue
        if not self.frame_queue.full():
            try:
                self.frame_queue.put_nowait(frame)
            except queue.Full:
                pass
        
        # Call callback
        if self.on_frame_callback:
            self.on_frame_callback(frame)
    
    def _create_error_frame(self, message):
        """Create error frame when FFmpeg fails"""
        if not CV2_AVAILABLE:
            return
            
        try:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[:] = [40, 40, 120]  # Blue background
            
            # Add error text
            font = cv2.FONT_HERSHEY_SIMPLEX
            cv2.putText(frame, "EDGELITE CLIENT", (30, 60), font, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, message, (30, 120), font, 0.6, (255, 255, 255), 1)
            cv2.putText(frame, "Troubleshooting:", (30, 180), font, 0.6, (255, 255, 255), 1)
            cv2.putText(frame, "1. Check if host is running", (30, 210), font, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, "2. Verify host IP and port", (30, 240), font, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, "3. Check firewall settings", (30, 270), font, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, "4. Ensure FFmpeg is installed", (30, 300), font, 0.5, (255, 255, 255), 1)
            
            self._handle_decoded_frame(frame)
        except Exception as e:
            print(f"Error frame creation failed: {e}")
    
    def get_frame(self):
        """Get the latest video frame"""
        try:
            # Get latest frame from queue
            if not self.frame_queue.empty():
                self.current_frame = self.frame_queue.get_nowait()
            return self.current_frame
        except:
            return self.current_frame
    
    def get_stats(self) -> dict:
        """Get streaming statistics"""
        return {
            'fps': self.fps,
            'connected': self.connected,
            'decoder': 'ffmpeg',
            'queue_size': self.frame_queue.qsize(),
            'platform': self.platform
        }
    
    def set_frame_callback(self, callback: Callable):
        """Set callback for new frames"""
        self.on_frame_callback = callback
    
    def disconnect(self):
        """Disconnect from stream"""
        self.running = False
        self.connected = False
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait(timeout=2.0)
            except:
                try:
                    self.ffmpeg_process.kill()
                except:
                    pass
        print("✅ FFmpeg receiver disconnected")

# ========== SIMPLE FALLBACK RECEIVER ==========
class SimpleVideoReceiver:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.connected = False
        self.running = False
        self.socket = None
        self.frame_queue = queue.Queue(maxsize=2)
        self.current_frame = None
        self.fps = 0
        self.frame_count = 0
        self.fps_update_time = time.time()
        self.on_frame_callback = None
        
        self.platform = platform.system().lower()
    
    def connect(self, host_ip: str) -> bool:
        """Simple UDP connection for testing"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
            self.socket.settimeout(2.0)
            self.socket.bind(('', self.config_manager.network_config.video_port))
            
            self.connected = True
            self.running = True
            
            thread = threading.Thread(target=self._receive_loop, daemon=True)
            thread.start()
            
            print(f"✅ Simple receiver started for {host_ip}")
            return True
            
        except Exception as e:
            print(f"❌ Simple connection failed: {e}")
            return False
    
    def _receive_loop(self):
        """Simple receive loop that shows connection status"""
        while self.running and self.connected:
            try:
                data, addr = self.socket.recvfrom(65536)
                
                # Create a simple test frame to show we're connected
                if CV2_AVAILABLE and self.frame_queue.empty():
                    test_frame = self._create_test_frame()
                    self.current_frame = test_frame
                    
                    # Update FPS
                    self.frame_count += 1
                    current_time = time.time()
                    if current_time - self.fps_update_time >= 1.0:
                        self.fps = min(self.frame_count, 30)
                        self.frame_count = 0
                        self.fps_update_time = current_time
                    
                    if self.on_frame_callback:
                        self.on_frame_callback(test_frame)
                    
                    try:
                        self.frame_queue.put_nowait(test_frame)
                    except queue.Full:
                        pass
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Receive error: {e}")
    
    def _create_test_frame(self):
        """Create a test frame to show we're connected"""
        try:
            # Create a simple colored frame with connection info
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            frame[:] = [50, 50, 150]  # Blue background
            
            # Add text
            text = "SIMPLE UDP TEST MODE"
            font = cv2.FONT_HERSHEY_SIMPLEX
            cv2.putText(frame, text, (50, 100), font, 0.8, (255, 255, 255), 2)
            cv2.putText(frame, "✅ Receiving UDP packets", (50, 150), font, 0.6, (255, 255, 255), 1)
            cv2.putText(frame, "⚠️ Using simple receiver (no video)", (50, 200), font, 0.6, (255, 255, 255), 1)
            cv2.putText(frame, "💡 Install FFmpeg for H.264 video", (50, 250), font, 0.6, (255, 255, 255), 1)
            
            return frame
        except:
            return None
    
    def get_frame(self):
        try:
            while not self.frame_queue.empty():
                self.current_frame = self.frame_queue.get_nowait()
            return self.current_frame
        except:
            return self.current_frame
    
    def get_stats(self):
        return {
            'fps': self.fps,
            'connected': self.connected,
            'decoder': 'test_mode',
            'queue_size': self.frame_queue.qsize(),
            'platform': self.platform
        }
    
    def set_frame_callback(self, callback: Callable):
        self.on_frame_callback = callback
    
    def disconnect(self):
        self.running = False
        self.connected = False
        if self.socket:
            self.socket.close()

# ========== INPUT SENDER ==========
class CrossPlatformInputSender:
    def __init__(self, control_port: int = 5556):
        self.control_port = control_port
        self.host_ip = None
        self.socket = None
        self.mouse_listener = None
        self.keyboard_listener = None
        self.running = False
        
        self.mouse_position = (0, 0)
        self.pressed_keys = set()
        
        # Client display dimensions for scaling
        self.display_width = 1920
        self.display_height = 1080
        self.stream_width = 1280
        self.stream_height = 720
        
        self.platform = platform.system().lower()
        self.input_enabled = PYNPUT_AVAILABLE
        
        if not self.input_enabled:
            print("Input forwarding disabled - install pynput to enable")
    
    def set_scaling(self, display_width: int, display_height: int, stream_width: int, stream_height: int):
        """Set scaling for coordinate conversion"""
        self.display_width = display_width
        self.display_height = display_height
        self.stream_width = stream_width
        self.stream_height = stream_height
        print(f"Input scaling set: Display {display_width}x{display_height}, Stream {stream_width}x{stream_height}")
    
    def _scale_coordinates(self, x: int, y: int) -> tuple:
        """Scale coordinates from display to stream resolution"""
        if self.display_width > 0 and self.display_height > 0:
            scaled_x = int(x * self.stream_width / self.display_width)
            scaled_y = int(y * self.stream_height / self.display_height)
            return scaled_x, scaled_y
        return x, y
    
    def connect(self, host_ip: str):
        """Connect to host input receiver"""
        try:
            self.host_ip = host_ip
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(1.0)
            
            if self.input_enabled:
                self._start_input_listeners()
            else:
                print("Input forwarding not available")
            
            print(f"✅ Input sender connected to {host_ip}")
            return True
        except Exception as e:
            print(f"❌ Input sender connection error: {e}")
            return False
    
    def _start_input_listeners(self):
        """Start listening for input events"""
        if not self.input_enabled:
            return
            
        self.running = True
        
        self.mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll
        )
        
        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        
        self.mouse_listener.start()
        self.keyboard_listener.start()
        
        print("✅ Input listeners started")
    
    def _send_input_event(self, event_data: dict):
        """Send input event to host"""
        if self.socket and self.host_ip and self.running:
            try:
                data = json.dumps(event_data).encode('utf-8')
                self.socket.sendto(data, (self.host_ip, self.control_port))
            except Exception as e:
                print(f"Input send error: {e}")
    
    def _on_mouse_move(self, x: int, y: int):
        """Handle mouse movement"""
        if not self.running:
            return
            
        self.mouse_position = (x, y)
        
        # Scale coordinates
        scaled_x, scaled_y = self._scale_coordinates(x, y)
        
        event = {
            'type': 'mouse',
            'action': 'move',
            'x': scaled_x,
            'y': scaled_y,
            'timestamp': time.time()
        }
        self._send_input_event(event)
    
    def _on_mouse_click(self, x: int, y: int, button, pressed: bool):
        """Handle mouse clicks"""
        if not self.running:
            return
            
        button_name = str(button).replace('Button.', '')
        
        # Scale coordinates
        scaled_x, scaled_y = self._scale_coordinates(x, y)
        
        event = {
            'type': 'mouse',
            'action': 'press' if pressed else 'release',
            'button': button_name,
            'x': scaled_x,
            'y': scaled_y,
            'timestamp': time.time()
        }
        self._send_input_event(event)
    
    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int):
        """Handle mouse scroll"""
        if not self.running:
            return
            
        # Scale coordinates
        scaled_x, scaled_y = self._scale_coordinates(x, y)
        
        event = {
            'type': 'mouse',
            'action': 'scroll',
            'x': scaled_x,
            'y': scaled_y,
            'dx': dx,
            'dy': dy,
            'timestamp': time.time()
        }
        self._send_input_event(event)
    
    def _on_key_press(self, key):
        """Handle key press"""
        if not self.running:
            return
            
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
        if not self.running:
            return
            
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
            return str(key).replace('Key.', '')
    
    def disconnect(self):
        """Disconnect input sender"""
        self.running = False
        
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.socket:
            self.socket.close()

# ========== VIDEO DISPLAY ==========
class VideoDisplay:
    def __init__(self, parent, width=1280, height=720):
        self.parent = parent
        self.width = width
        self.height = height
        self.current_image = None
        
        self.setup_display()
    
    def setup_display(self):
        """Setup Tkinter video display using grid"""
        self.frame = ttk.Frame(self.parent)
        self.frame.grid(row=0, column=0, sticky="nsew")
        
        self.frame.grid_rowconfigure(0, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)
        
        self.video_label = ttk.Label(
            self.frame, 
            text="Enter host IP (e.g., 192.168.0.155) and click Connect",
            background='black',
            foreground='white',
            font=('Arial', 12),
            anchor='center',
            justify='center'
        )
        self.video_label.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        
        self.status_frame = ttk.Frame(self.frame)
        self.status_frame.grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        
        self.fps_label = ttk.Label(self.status_frame, text="FPS: 0")
        self.fps_label.pack(side=tk.LEFT, padx=5)
        
        self.connection_label = ttk.Label(self.status_frame, text="FFmpeg Receiver")
        self.connection_label.pack(side=tk.LEFT, padx=5)
        
        platform_info = f"{platform.system()} {platform.release()}"
        self.platform_label = ttk.Label(self.status_frame, text=platform_info)
        self.platform_label.pack(side=tk.RIGHT, padx=5)
        
        self.status_frame.columnconfigure(0, weight=1)
    
    def update_frame(self, frame, stats):
        """Update the video display with new frame"""
        if frame is None or not CV2_AVAILABLE:
            self._update_status(stats)
            return
        
        self._update_tkinter_frame(frame, stats)
    
    def _update_tkinter_frame(self, frame, stats):
        """Update Tkinter display with new frame"""
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb_frame)
            
            display_width = self.video_label.winfo_width()
            display_height = self.video_label.winfo_height()
            
            if display_width <= 1 or display_height <= 1:
                display_width = self.width
                display_height = self.height
            
            img.thumbnail((display_width, display_height), Image.Resampling.LANCZOS)
            
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.configure(image=imgtk, text="")
            self.video_label.image = imgtk
            
            self._update_status(stats)
            
        except Exception as e:
            print(f"Frame update error: {e}")
    
    def _update_status(self, stats):
        """Update status labels"""
        try:
            self.fps_label.config(text=f"FPS: {stats.get('fps', 0)}")
            
            if stats.get('connected', False):
                self.connection_label.config(text="🟢 Streaming", foreground="green")
            else:
                self.connection_label.config(text="🔴 Disconnected", foreground="red")
                
        except Exception as e:
            print(f"Status update error: {e}")
    
    def show_connecting(self):
        """Show connecting state"""
        self.video_label.configure(
            image='',
            text="Connecting to host...\n\nStarting FFmpeg receiver...",
            background='black',
            foreground='white'
        )
    
    def show_error(self, message):
        """Show error message"""
        self.video_label.configure(
            image='',
            text=f"Error: {message}\n\nCheck host connection and try again",
            background='darkred',
            foreground='white'
        )
        self.connection_label.config(text="🔴 Error", foreground="red")

# ========== MAIN CLIENT GUI ==========
class EdgeLiteClient:
    def __init__(self):
        self.config_manager = ConfigManager()
        
        # Check if FFmpeg is available
        self.ffmpeg_available = self._check_ffmpeg()
        
        # Select receiver based on FFmpeg availability
        if self.ffmpeg_available:
            self.receiver = FFmpegVideoReceiver(self.config_manager)
            print("🔧 Using FFmpeg H.264 video receiver")
        else:
            self.receiver = SimpleVideoReceiver(self.config_manager)
            print("🔧 Using simple video receiver (FFmpeg not available)")
            
        self.input_sender = CrossPlatformInputSender(self.config_manager.network_config.control_port)
        
        self.connected = False
        self.connection_start_time = 0
        self.host_ip = None
        
        self.root = None
        self.log_text = None
        self.connect_btn = None
        self.connection_status = None
        self.video_display = None
        
        self.setup_gui()
        self.receiver.set_frame_callback(self.on_new_frame)
    
    def _check_ffmpeg(self):
        """Check if FFmpeg is available on the system"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=5)
            if result.returncode == 0:
                print("✅ FFmpeg is available")
                return True
            else:
                print("❌ FFmpeg check failed")
                return False
        except:
            print("❌ FFmpeg not found in system PATH")
            return False
    
    def setup_gui(self):
        """Setup the main client GUI using grid consistently"""
        self.root = tk.Tk()
        self.root.title("EdgeLite Client - FFmpeg H.264")
        self.root.geometry("800x600")
        
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_rowconfigure(2, weight=0)
        self.root.grid_columnconfigure(0, weight=1)
        
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.grid(row=0, column=0, sticky="ew")
        
        ttk.Label(control_frame, text="Host IP:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.host_ip_var = tk.StringVar(value="127.0.0.1")  # Default to localhost for testing
        ip_entry = ttk.Entry(control_frame, textvariable=self.host_ip_var, width=15)
        ip_entry.grid(row=0, column=1, sticky="ew", padx=(0, 5))
        
        self.connect_btn = ttk.Button(control_frame, text="Connect", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=2, padx=(0, 5))
        
        self.connection_status = ttk.Label(control_frame, text="🔴 DISCONNECTED", foreground="red", font=('Arial', 9, 'bold'))
        self.connection_status.grid(row=0, column=3, padx=(10, 0))
        
        control_frame.grid_columnconfigure(1, weight=1)
        
        video_container = ttk.Frame(self.root)
        video_container.grid(row=1, column=0, sticky="nsew")
        video_container.grid_rowconfigure(0, weight=1)
        video_container.grid_columnconfigure(0, weight=1)
        
        self.video_display = VideoDisplay(video_container)
        
        log_frame = ttk.LabelFrame(self.root, text="Connection Log", padding="5")
        log_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)
        
        self.log_text = tk.Text(log_frame, height=6)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.setup_platform_input()
        
        self.log("✅ EdgeLite FFmpeg H.264 Client Started")
        self.log(f"🌍 Platform: {platform.system()} {platform.release()}")
        
        if self.ffmpeg_available:
            self.log("🔧 Using FFmpeg H.264 decoder with UDP")
        else:
            self.log("⚠️ Using simple receiver - FFmpeg not available")
            self.log("💡 Install FFmpeg for better video performance:")
            self.log("   Windows: download from ffmpeg.org")
            self.log("   macOS: brew install ffmpeg")
            self.log("   Linux: sudo apt install ffmpeg")
        
        self.log("💡 Enter host IP and click Connect")
        self.log("💡 For testing, use 127.0.0.1 to connect to yourself")
        
        if not CV2_AVAILABLE:
            self.log("❌ WARNING: OpenCV/PIL not installed - video display disabled")
            self.log("   Install with: pip install opencv-python Pillow")
        if not PYNPUT_AVAILABLE:
            self.log("❌ WARNING: pynput not installed - input forwarding disabled")
            self.log("   Install with: pip install pynput")
    
    def setup_platform_input(self):
        """Setup input forwarding with proper focus handling"""
        if hasattr(self.video_display, 'video_label'):
            # Bind focus events to video display
            self.video_display.video_label.bind('<Enter>', self.on_video_focus)
            self.video_display.video_label.bind('<Leave>', self.on_video_blur)
            self.video_display.video_label.bind('<Button-1>', self.on_video_click)
            
            # Make video label focusable
            self.video_display.video_label.focus_set()
    
    def on_video_click(self, event):
        """When video display is clicked, focus it"""
        self.video_display.video_label.focus_set()
        self.log("🎯 Video display focused - input forwarding active")
        
    def on_video_focus(self, event):
        """When video display gets focus"""
        if self.connected:
            self.log("🎯 Video display focused - input forwarding active")
            self.log("🖱️  You can now control the host computer")
            self.log("💡 Click anywhere outside the video to release control")
    
    def on_video_blur(self, event):
        """When video display loses focus"""
        if self.connected:
            self.log("🎯 Video display unfocused - input forwarding inactive")
    
    def on_new_frame(self, frame):
        """Callback for new video frames"""
        if hasattr(self, 'video_display'):
            stats = self.receiver.get_stats()
            self.root.after(0, self.update_display, frame, stats)
    
    def update_display(self, frame, stats):
        """Update video display and stats in main thread"""
        if self.video_display:
            self.video_display.update_frame(frame, stats)
        
        if self.connected and stats['connected']:
            connection_time = time.time() - self.connection_start_time
            status_text = f"🟢 CONNECTED ({int(connection_time)}s)"
            self.connection_status.config(text=status_text, foreground="green")
        else:
            if self.connected and not stats['connected']:
                self.connected = False
                self.connect_btn.config(text="Connect")
                self.connection_status.config(text="🔴 CONNECTION LOST", foreground="red")
                self.log("❌ Connection lost - video stream disconnected")
                self.video_display.show_error("Connection lost")
    
    def toggle_connection(self):
        """Connect or disconnect from host"""
        if not self.connected:
            self.connect_to_host()
        else:
            self.disconnect_from_host()
    
    def connect_to_host(self):
        """Connect to selected host"""
        host_ip = self.host_ip_var.get().strip()
        if not host_ip:
            messagebox.showerror("Error", "Please enter host IP address")
            return
        
        if not CV2_AVAILABLE:
            messagebox.showerror("Error",
                "OpenCV/PIL not installed!\n\n"
                "Video display requires OpenCV and PIL.\n"
                "Install with: pip install opencv-python Pillow")
            return
        
        self.log(f"🔗 Connecting to {host_ip}...")
        self.video_display.show_connecting()
        
        self.connection_status.config(text="🟡 CONNECTING...", foreground="orange")
        self.connect_btn.config(state="disabled")
        
        def connect_thread():
            success = self.receiver.connect(host_ip)
            self.root.after(0, self._connection_result, success, host_ip)
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    def _connection_result(self, success, host_ip):
        self.connect_btn.config(state="normal")
        
        if success:
            self.connected = True
            self.connection_start_time = time.time()
            self.host_ip = host_ip
            
            self.connect_btn.config(text="Disconnect")
            self.connection_status.config(text="🟢 CONNECTED", foreground="green")
            
            # Setup input scaling with proper dimensions
            display_width = self.video_display.video_label.winfo_width()
            display_height = self.video_display.video_label.winfo_height()
            
            # If video label dimensions are not available yet, use default
            if display_width <= 1 or display_height <= 1:
                display_width = 1280
                display_height = 720
            
            stream_config = self.config_manager.stream_config
            self.input_sender.set_scaling(
                display_width, display_height,
                stream_config.width,
                stream_config.height
            )
            
            # Start input sender
            input_success = self.input_sender.connect(host_ip)
            if input_success:
                self.log("✅ Input control initialized")
            else:
                self.log("⚠️ Input control failed to start")
            
            self.log(f"✅ Successfully connected to {host_ip}")
            if self.ffmpeg_available:
                self.log("🔧 Using FFmpeg H.264 decoder")
            else:
                self.log("🔧 Using simple UDP receiver")
            self.log("🎯 Click the video display to start controlling the host")
            self.log("📺 Waiting for video stream...")
            
        else:
            self.connection_status.config(text="🔴 CONNECTION FAILED", foreground="red")
            self.video_display.show_error(f"Cannot connect to {host_ip}")
            self.log(f"❌ Failed to connect to {host_ip}")
            
            error_msg = f"Failed to connect to {host_ip}\n\nPossible issues:\n"
            error_msg += "• Host IP address is incorrect\n"
            error_msg += "• Host is not running EdgeLite\n"
            error_msg += "• Host firewall is blocking connection\n"
            error_msg += "• Make sure host has started streaming\n"
            
            if not self.ffmpeg_available:
                error_msg += "• FFmpeg is not installed on client\n"
            
            messagebox.showerror("Connection Failed", error_msg)
    
    def disconnect_from_host(self):
        """Disconnect from host"""
        self.log("🔌 Disconnecting from host...")
        
        self.receiver.disconnect()
        self.input_sender.disconnect()
        
        self.connected = False
        self.connect_btn.config(text="Connect")
        self.connection_status.config(text="🔴 DISCONNECTED", foreground="red")
        
        if self.video_display:
            self.video_display.video_label.configure(
                image='',
                text="Disconnected\n\n" +
                     "Enter host IP and click Connect to reconnect",
                background='black',
                foreground='white'
            )
        
        self.log("✅ Disconnected from host")
        self.log("💡 Ready for new connection")
    
    def log(self, message: str):
        """Add message to log"""
        try:
            timestamp = time.strftime('%H:%M:%S')
            if self.log_text:
                self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
                self.log_text.see(tk.END)
            else:
                print(f"[{timestamp}] {message}")
        except Exception as e:
            print(f"Log error: {e}")
            print(f"Message: {message}")
    
    def run(self):
        """Start the client application"""
        try:
            self.update_stats()
            self.root.mainloop()
        except KeyboardInterrupt:
            self.cleanup()
        finally:
            self.cleanup()
    
    def update_stats(self):
        """Periodically update statistics"""
        if self.connected:
            stats = self.receiver.get_stats()
            self.update_display(None, stats)
            
            if not stats['connected']:
                self.connected = False
                self.connect_btn.config(text="Connect")
                self.connection_status.config(text="🔴 CONNECTION LOST", foreground="red")
                self.log("❌ Connection lost with host")
        
        self.root.after(1000, self.update_stats)
    
    def cleanup(self):
        """Cleanup resources"""
        self.connected = False
        self.receiver.disconnect()
        self.input_sender.disconnect()

# ========== MAIN ENTRY POINT ==========
def main():
    """Main entry point"""
    print(f"🌍 Platform: {platform.system()} {platform.release()}")
    print(f"🐍 Python: {platform.python_version()}")
    print("🚀 Starting EdgeLite FFmpeg H.264 Client")
    
    if not CV2_AVAILABLE:
        print("❌ CRITICAL: OpenCV and PIL are required for video display")
        response = input("   Install now? (y/n): ")
        if response.lower() == 'y':
            os.system("pip install opencv-python Pillow")
            print("✅ Please restart the application")
            return
    
    try:
        app = EdgeLiteClient()
        app.run()
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to exit...")

if __name__ == "__main__":
    main()
