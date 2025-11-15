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
from typing import Optional, Callable

# ========== PLATFORM-SPECIFIC IMPORTS ==========
try:
    import av
    AV_AVAILABLE = True
except ImportError:
    AV_AVAILABLE = False
    print("PyAV not available - video streaming disabled")

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
        self.fps = 60
        self.bitrate = "2M"

class NetworkConfig:
    def __init__(self):
        self.video_port = 5555
        self.control_port = 5556
        self.discovery_port = 5557

class ConfigManager:
    def __init__(self):
        self.stream_config = StreamConfig()
        self.network_config = NetworkConfig()

# ========== VIDEO RECEIVER ==========
class CrossPlatformVideoReceiver:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.connected = False
        self.input_stream = None
        self.video_stream = None
        self.frame_queue = queue.Queue(maxsize=2)
        self.current_frame = None
        self.fps = 0
        self.frame_count = 0
        self.fps_update_time = time.time()
        self.on_frame_callback = None
        
        self.platform = platform.system().lower()
        self.decoder_name = self._get_platform_decoder()
        print(f"Platform: {self.platform}, Using decoder: {self.decoder_name}")
    
    def _get_platform_decoder(self):
        """Select appropriate hardware decoder based on platform"""
        if not AV_AVAILABLE:
            return "none"
            
        if self.platform == "darwin":  # macOS
            return self._get_macos_decoder()
        elif self.platform == "linux":
            return self._get_linux_decoder()
        elif self.platform == "windows":
            return self._get_windows_decoder()
        else:
            return "h264"  # Software fallback
    
    def _get_macos_decoder(self):
        """Get hardware decoder for macOS"""
        try:
            codec = av.CodecContext.create('h264_videotoolbox', 'r')
            codec.close()
            return 'h264_videotoolbox'
        except:
            print("VideoToolbox not available, using software decoder")
            return 'h264'
    
    def _get_linux_decoder(self):
        """Get hardware decoder for Linux"""
        decoders_to_try = [
            'h264_vaapi',    # Intel/AMD VA-API
            'h264_v4l2m2m',  # V4L2 Memory-to-Memory
            'h264_cuvid',    # NVIDIA CUDA
        ]
        
        for decoder in decoders_to_try:
            try:
                codec = av.CodecContext.create(decoder, 'r')
                codec.close()
                return decoder
            except:
                continue
        
        return 'h264'
    
    def _get_windows_decoder(self):
        """Get hardware decoder for Windows"""
        decoders_to_try = [
            'h264_cuvid',    # NVIDIA CUDA
            'h264_d3d11va',  # DirectX 11
        ]
        
        for decoder in decoders_to_try:
            try:
                codec = av.CodecContext.create(decoder, 'r')
                codec.close()
                return decoder
            except:
                continue
        
        return 'h264'
    
    def connect(self, host_ip: str) -> bool:
        """Connect to host video stream"""
        if not AV_AVAILABLE:
            print("ERROR: PyAV not installed. Video streaming disabled.")
            return False
            
        try:
            stream_url = f"udp://{host_ip}:{self.config_manager.network_config.video_port}"
            
            # Platform-specific options
            options = {
                'fflags': 'nobuffer',
                'flags': 'low_delay',
                'framedrop': '1',
                'strict': 'experimental'
            }
            
            self.input_stream = av.open(stream_url, mode='r', options=options)
            self.video_stream = next(s for s in self.input_stream.streams if s.type == 'video')
            
            # Use hardware acceleration if available
            if self.decoder_name != "h264" and self.decoder_name != "none":
                try:
                    codec = av.CodecContext.create(self.decoder_name, 'r')
                    self.video_stream.codec_context = codec
                except Exception as e:
                    print(f"Hardware decoder failed: {e}")
                    self.decoder_name = "h264"
            
            self.connected = True
            thread = threading.Thread(target=self._receive_loop, daemon=True)
            thread.start()
            
            return True
            
        except Exception as e:
            print(f"Video connection error: {e}")
            return False
    
    def _receive_loop(self):
        """Main reception and decoding loop"""
        try:
            for packet in self.input_stream.demux(self.video_stream):
                if not self.connected:
                    break
                    
                for frame in packet.decode():
                    if frame:
                        # Convert to numpy array (BGR for OpenCV)
                        img = frame.to_ndarray(format='bgr24')
                        
                        # Update frame statistics
                        current_time = time.time()
                        self.frame_count += 1
                        if current_time - self.fps_update_time >= 1.0:
                            self.fps = self.frame_count
                            self.frame_count = 0
                            self.fps_update_time = current_time
                        
                        self.current_frame = img
                        
                        # Call callback if set
                        if self.on_frame_callback:
                            self.on_frame_callback(img)
                        
                        # Put in queue (non-blocking)
                        if not self.frame_queue.full():
                            try:
                                self.frame_queue.put_nowait(img)
                            except queue.Full:
                                pass
                                
        except Exception as e:
            if self.connected:
                print(f"Receive loop error: {e}")
    
    def get_frame(self):
        """Get the latest video frame"""
        try:
            # Get latest frame from queue
            while not self.frame_queue.empty():
                self.current_frame = self.frame_queue.get_nowait()
            return self.current_frame
        except:
            return self.current_frame
    
    def get_stats(self) -> dict:
        """Get streaming statistics"""
        return {
            'fps': self.fps,
            'connected': self.connected,
            'decoder': self.decoder_name,
            'queue_size': self.frame_queue.qsize(),
            'platform': self.platform,
            'av_available': AV_AVAILABLE,
            'cv2_available': CV2_AVAILABLE
        }
    
    def set_frame_callback(self, callback: Callable):
        """Set callback for new frames"""
        self.on_frame_callback = callback
    
    def disconnect(self):
        """Disconnect from stream"""
        self.connected = False
        if self.input_stream:
            self.input_stream.close()
            self.input_stream = None

# ========== INPUT SENDER ==========
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
    
    def _send_input_event(self, event_data: dict):
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
        scaled_x, scaled_y = self._scale_coordinates(x, y)
        button_name = str(button).replace('Button.', '')
        
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
        """Convert key to string representation with platform mapping"""
        if hasattr(key, 'char') and key.char is not None:
            return key.char
        else:
            key_str = str(key).replace('Key.', '')
            # Apply platform-specific mappings
            return self.key_mappings.get(key_str, key_str)
    
    def disconnect(self):
        """Disconnect input sender"""
        self.running = False
        
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.socket:
            self.socket.close()

# ========== NETWORK DISCOVERY ==========
class NetworkDiscovery:
    def __init__(self, port: int = 5557):
        self.port = port
        self.running = False
        self.socket = None
        self.on_host_discovered = None
    
    def start_discovery(self, on_host_discovered: Callable):
        """Start listening for host broadcasts"""
        self.on_host_discovered = on_host_discovered
        self.running = True
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # Enable broadcast
        
        try:
            self.socket.bind(('', self.port))
            print(f"Discovery service started on port {self.port}")
        except Exception as e:
            print(f"Failed to bind discovery socket: {e}")
            try:
                self.socket.bind(('', 0))
                self.port = self.socket.getsockname()[1]
                print(f"Discovery service started on random port {self.port}")
            except Exception as e2:
                print(f"Failed to bind discovery socket to random port: {e2}")
                return
        
        thread = threading.Thread(target=self._discovery_loop, daemon=True)
        thread.start()
    
    def _discovery_loop(self):
        """Discovery loop to find hosts on network"""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(1024)
                message = self._parse_broadcast_message(data)
                if message and self.on_host_discovered:
                    self.on_host_discovered(message, addr[0])
            except Exception as e:
                if self.running:
                    print(f"Discovery error: {e}")
    
    def _parse_broadcast_message(self, data: bytes) -> Optional[dict]:
        """Parse broadcast message from host"""
        try:
            message = json.loads(data.decode())
            if message.get('type') == 'discovery':
                return message
        except:
            pass
        return None
    
    def stop_discovery(self):
        """Stop discovery service"""
        self.running = False
        if self.socket:
            self.socket.close()

# ========== VIDEO DISPLAY ==========
class CrossPlatformVideoDisplay:
    def __init__(self, parent, width=1280, height=720):
        self.parent = parent
        self.width = width
        self.height = height
        self.current_image = None
        self.platform = platform.system().lower()
        
        self.setup_tkinter_display()
    
    def setup_tkinter_display(self):
        """Setup Tkinter-based video display (works on all platforms)"""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Video label
        self.video_label = ttk.Label(
            self.frame, 
            text="Waiting for video stream...\n\n" +
                 "To start: Enter host IP and click Connect\n" +
                 "For input control: Click this window to focus",
            background='black',
            foreground='white',
            font=('Arial', 12),
            anchor='center',
            justify='center'
        )
        self.video_label.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # Status bar
        self.status_frame = ttk.Frame(self.frame)
        self.status_frame.pack(fill=tk.X, padx=2, pady=2)
        
        self.fps_label = ttk.Label(self.status_frame, text="FPS: 0")
        self.fps_label.pack(side=tk.LEFT, padx=5)
        
        self.decoder_label = ttk.Label(self.status_frame, text="Decoder: None")
        self.decoder_label.pack(side=tk.LEFT, padx=5)
        
        # Platform info
        platform_info = f"{platform.system()} {platform.release()}"
        self.platform_label = ttk.Label(self.status_frame, text=platform_info)
        self.platform_label.pack(side=tk.RIGHT, padx=5)
        
        self.resolution_label = ttk.Label(self.status_frame, text=f"{self.width}x{self.height}")
        self.resolution_label.pack(side=tk.RIGHT, padx=5)
    
    def update_frame(self, frame, stats):
        """Update the video display with new frame"""
        if frame is None or not CV2_AVAILABLE:
            return
        
        self._update_tkinter_frame(frame, stats)
    
    def _update_tkinter_frame(self, frame, stats):
        """Update Tkinter display with new frame"""
        try:
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Convert to PIL Image
            img = Image.fromarray(rgb_frame)
            
            # Get display dimensions
            display_width = self.video_label.winfo_width()
            display_height = self.video_label.winfo_height()
            
            # Use reasonable defaults if dimensions aren't available yet
            if display_width <= 1 or display_height <= 1:
                display_width = self.width
                display_height = self.height
            
            # Resize for display while maintaining aspect ratio
            img.thumbnail((display_width, display_height), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            imgtk = ImageTk.PhotoImage(image=img)
            
            # Update display
            self.video_label.configure(image=imgtk)
            self.video_label.image = imgtk
            
            # Update stats
            self.fps_label.config(text=f"FPS: {stats.get('fps', 0)}")
            self.decoder_label.config(text=f"Decoder: {stats.get('decoder', 'None')}")
            
        except Exception as e:
            print(f"Frame update error: {e}")
    
    def destroy(self):
        """Cleanup resources"""
        pass

# ========== MAIN CLIENT GUI ==========
class EdgeLiteClient:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.receiver = CrossPlatformVideoReceiver(self.config_manager)
        self.input_sender = CrossPlatformInputSender(self.config_manager.network_config.control_port)
        self.discovery = NetworkDiscovery(self.config_manager.network_config.discovery_port)
        
        # Initialize these after creating the root window
        self.connected = False
        self.host_ip = None  # Will be initialized in setup_gui
        self.discovered_hosts = []
        
        # Initialize GUI components to None
        self.log_text = None
        self.connect_btn = None
        self.connection_status = None
        self.hosts_combo = None
        self.video_display = None
        
        self.setup_gui()
        
        # Set frame callback for real-time updates
        self.receiver.set_frame_callback(self.on_new_frame)
    
    def setup_gui(self):
        """Setup the main client GUI with cross-platform compatibility"""
        self.root = tk.Tk()
        self.setup_window()
        
        # Initialize Tkinter variables AFTER creating root window
        self.host_ip = tk.StringVar()
        
        self.setup_gui_elements()
        
        self.log(f"✅ EdgeLite Client started on {platform.system()} {platform.release()}")
        self.log("🔍 Ready to connect to host")
        self.log("💡 Tip: Use 'Discover Hosts' to find available streaming servers")
        
        # Show dependency status
        if not AV_AVAILABLE:
            self.log("❌ WARNING: PyAV not installed - video streaming disabled")
            self.log("   Install with: pip install av")
        if not CV2_AVAILABLE:
            self.log("❌ WARNING: OpenCV/PIL not installed - video display disabled")
            self.log("   Install with: pip install opencv-python Pillow")
        if not PYNPUT_AVAILABLE:
            self.log("❌ WARNING: pynput not installed - input forwarding disabled")
            self.log("   Install with: pip install pynput")
    
    def setup_window(self):
        """Setup the main window with platform-specific settings"""
        self.root.title("EdgeLite Client - Cross Platform")
        self.root.geometry("900x700")
        
        # Platform-specific window settings
        platform_name = platform.system().lower()
        
        if platform_name == "darwin":
            # macOS specific settings
            self.root.configure(background='systemWindowBackgroundColor')
        elif platform_name == "linux":
            # Linux specific settings
            self.root.configure(background='#f0f0f0')
        else:
            # Windows and others
            self.root.configure(background='systemButtonFace')
    
    def setup_gui_elements(self):
        """Setup all GUI elements"""
        # Configure root window
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        
        # Control panel
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # Connection controls
        ttk.Label(control_frame, text="Host IP:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        ip_entry = ttk.Entry(control_frame, textvariable=self.host_ip, width=20)
        ip_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))
        
        self.connect_btn = ttk.Button(control_frame, text="Connect", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=2, padx=(0, 5))
        
        ttk.Button(control_frame, text="Discover Hosts", command=self.start_discovery).grid(row=0, column=3, padx=(0, 5))
        
        # Discovered hosts dropdown
        self.hosts_combo = ttk.Combobox(control_frame, values=[], state="readonly", width=25)
        self.hosts_combo.grid(row=0, column=4, padx=(5, 5))
        self.hosts_combo.bind('<<ComboboxSelected>>', self.on_host_selected)
        
        # Stats display
        stats_frame = ttk.Frame(control_frame)
        stats_frame.grid(row=0, column=5, sticky=(tk.W, tk.E), padx=(10, 0))
        
        self.connection_status = ttk.Label(stats_frame, text="Disconnected", foreground="red")
        self.connection_status.pack(side=tk.LEFT, padx=(0, 10))
        
        self.av_status = ttk.Label(stats_frame, text=f"AV: {'✅' if AV_AVAILABLE else '❌'}")
        self.av_status.pack(side=tk.LEFT, padx=(0, 10))
        
        self.cv2_status = ttk.Label(stats_frame, text=f"CV2: {'✅' if CV2_AVAILABLE else '❌'}")
        self.cv2_status.pack(side=tk.LEFT, padx=(0, 10))
        
        self.input_status = ttk.Label(stats_frame, text=f"Input: {'✅' if PYNPUT_AVAILABLE else '❌'}")
        self.input_status.pack(side=tk.LEFT)
        
        control_frame.columnconfigure(4, weight=1)
        
        # Video display area
        self.video_display = CrossPlatformVideoDisplay(self.root)
        self.video_display.frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Status log
        log_frame = ttk.LabelFrame(self.root, text="Connection Log", padding="5")
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=10, pady=5)
        
        self.log_text = tk.Text(log_frame, height=8, width=80)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        log_scrollbar = ttk.Scrollbar(self.log_text, orient="vertical", command=self.log_text.yview)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        # Platform-specific input handling
        self.setup_platform_input()
    
    def setup_platform_input(self):
        """Setup input forwarding with platform-specific considerations"""
        if hasattr(self.video_display, 'video_label'):
            self.video_display.video_label.bind('<FocusIn>', self.on_video_focus)
            self.video_display.video_label.bind('<FocusOut>', self.on_video_blur)
            self.video_display.video_label.focus_set()
            
            # Platform-specific input hints
            platform_name = platform.system().lower()
            if platform_name == "darwin":
                self.log("💡 macOS: Ensure accessibility permissions for input forwarding")
                self.log("   System Preferences > Security & Privacy > Accessibility")
            elif platform_name == "linux":
                self.log("💡 Linux: Input forwarding should work out of the box")
            elif platform_name == "windows":
                self.log("💡 Windows: Input forwarding should work automatically")
    
    def on_video_focus(self, event):
        """When video display gets focus"""
        self.log("🎯 Video display focused - input forwarding active")
        self.log("🖱️  You can now control the host computer")
    
    def on_video_blur(self, event):
        """When video display loses focus"""
        self.log("🎯 Video display unfocused - input forwarding inactive")
    
    def on_new_frame(self, frame):
        """Callback for new video frames"""
        if hasattr(self, 'video_display'):
            stats = self.receiver.get_stats()
            # Schedule GUI update in main thread
            self.root.after(0, self.update_display, frame, stats)
    
    def update_display(self, frame, stats):
        """Update video display and stats in main thread"""
        if self.video_display:
            self.video_display.update_frame(frame, stats)
        
        # Update connection status
        if stats['connected']:
            if self.connection_status:
                self.connection_status.config(text="Connected", foreground="green")
        else:
            if self.connection_status:
                self.connection_status.config(text="Disconnected", foreground="red")
    
    def start_discovery(self):
        """Start network host discovery"""
        try:
            self.discovery.start_discovery(self.on_host_discovered)
            self.log("🔍 Started host discovery...")
            self.log("   Searching for EdgeLite hosts on the network...")
            self.log("   Make sure the host is running and on the same network")
        except Exception as e:
            self.log(f"❌ Failed to start discovery: {e}")
    
    def on_host_discovered(self, host_info: dict, ip: str):
        """Handle discovered hosts"""
        try:
            host_str = f"{host_info['host_name']} ({ip})"
            if host_str not in self.discovered_hosts:
                self.discovered_hosts.append(host_str)
                if self.hosts_combo:
                    self.hosts_combo['values'] = self.discovered_hosts
                self.log(f"✅ Discovered host: {host_str}")
        except Exception as e:
            print(f"Error in on_host_discovered: {e}")
    
    def on_host_selected(self, event):
        """Handle host selection from dropdown"""
        try:
            selected = self.hosts_combo.get()
            if selected and '(' in selected:
                # Extract IP from string like "HostName (192.168.1.100)"
                ip = selected.split('(')[1].rstrip(')')
                self.host_ip.set(ip)
                self.log(f"📍 Selected host: {ip}")
        except Exception as e:
            self.log(f"❌ Error selecting host: {e}")
    
    def toggle_connection(self):
        """Connect or disconnect from host"""
        if not self.connected:
            self.connect_to_host()
        else:
            self.disconnect_from_host()
    
    def connect_to_host(self):
        """Connect to selected host"""
        if not self.host_ip.get():
            messagebox.showerror("Error", "Please enter host IP address")
            return
        
        if not AV_AVAILABLE:
            messagebox.showerror("Error", 
                "PyAV not installed!\n\n"
                "Video streaming requires PyAV.\n"
                "Install with: pip install av")
            return
        
        if not CV2_AVAILABLE:
            messagebox.showerror("Error",
                "OpenCV/PIL not installed!\n\n"
                "Video display requires OpenCV and PIL.\n"
                "Install with: pip install opencv-python Pillow")
            return
        
        self.log(f"🔗 Connecting to {self.host_ip.get()}...")
        
        if self.receiver.connect(self.host_ip.get()):
            self.connected = True
            if self.connect_btn:
                self.connect_btn.config(text="Disconnect")
            
            # Setup input forwarding
            display_width = self.root.winfo_screenwidth()
            display_height = self.root.winfo_screenheight()
            stream_config = self.config_manager.stream_config
            self.input_sender.set_scaling(
                display_width, display_height,
                stream_config.width,
                stream_config.height
            )
            self.input_sender.connect(self.host_ip.get())
            
            self.log(f"✅ Connected to {self.host_ip.get()}")
            self.log(f"🔧 Using {self.receiver.decoder_name} decoder")
            self.log("🎯 Click the video display to start controlling the host")
            
        else:
            messagebox.showerror("Error", 
                f"Failed to connect to {self.host_ip.get()}\n\n"
                "Check:\n"
                "• Host IP address is correct\n"
                "• Host computer is running EdgeLite\n"
                "• Both computers are on same network\n"
                "• Firewall allows port 5555")
            self.log(f"❌ Failed to connect to {self.host_ip.get()}")
    
    def disconnect_from_host(self):
        """Disconnect from host"""
        self.receiver.disconnect()
        self.input_sender.disconnect()
        self.connected = False
        if self.connect_btn:
            self.connect_btn.config(text="Connect")
        if self.connection_status:
            self.connection_status.config(text="Disconnected", foreground="red")
        self.log("🔌 Disconnected from host")
    
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
            # Start periodic stats update
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
            self.update_display(None, stats)  # Update stats only
        
        # Schedule next update
        self.root.after(1000, self.update_stats)
    
    def cleanup(self):
        """Cleanup resources"""
        self.connected = False
        self.receiver.disconnect()
        self.input_sender.disconnect()
        self.discovery.stop_discovery()
        if hasattr(self, 'video_display'):
            self.video_display.destroy()

# ========== PLATFORM-SPECIFIC INSTALLATION GUIDE ==========
def show_installation_guide():
    """Show installation instructions for current platform"""
    platform_name = platform.system().lower()
    
    print("\n" + "="*60)
    print("🎮 EdgeLite Client - Cross Platform Streaming")
    print("="*60)
    
    if platform_name == "darwin":
        print("📋 macOS Installation:")
        print("   pip install av opencv-python pillow pynput")
        print("\n🔧 Additional Steps:")
        print("   1. Enable accessibility permissions:")
        print("      System Preferences > Security & Privacy > Accessibility")
        print("      Add Terminal/iTerm to the allowed apps")
        print("   2. Enable screen recording permissions if needed")
        
    elif platform_name == "linux":
        print("📋 Linux Installation:")
        print("   # Ubuntu/Debian:")
        print("   sudo apt-get install python3-tk")
        print("   pip install av opencv-python pillow pynput")
        print("\n   # Fedora:")
        print("   sudo dnf install python3-tkinter")
        print("   pip install av opencv-python pillow pynput")
        print("\n   # Arch Linux:")
        print("   sudo pacman -S tk")
        print("   pip install av opencv-python pillow pynput")
        
    elif platform_name == "windows":
        print("📋 Windows Installation:")
        print("   pip install av opencv-python pillow pynput")
        print("\n🔧 Note: No special permissions needed on Windows")
        
    else:
        print("📋 General Installation:")
        print("   pip install av opencv-python pillow pynput")
    
    print("\n🚀 Usage:")
    print("   1. Run the host on the streaming computer")
    print("   2. Run this client and enter the host IP")
    print("   3. Click Connect and enjoy!")
    print("="*60)
    print()

# ========== MAIN ENTRY POINT ==========
def main():
    """Main entry point with platform detection and error handling"""
    print(f"🌍 Platform: {platform.system()} {platform.release()}")
    print(f"🐍 Python: {platform.python_version()}")
    
    # Show installation guide if dependencies are missing
    if not all([AV_AVAILABLE, CV2_AVAILABLE, PYNPUT_AVAILABLE]):
        show_installation_guide()
    
    # Check critical dependencies
    if not AV_AVAILABLE:
        print("❌ CRITICAL: PyAV is required for video streaming")
        response = input("   Install now? (y/n): ")
        if response.lower() == 'y':
            os.system("pip install av")
            print("✅ Please restart the application")
            return
    
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