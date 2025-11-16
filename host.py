import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import queue
import json
import os
import platform
import socket
import mss
import numpy as np
import av
import logging
logging.basicConfig(level=logging.DEBUG)
# ========== CONFIGURATION ==========
class StreamConfig:
    def __init__(self):
        self.width = 1280
        self.height = 720
        self.fps = 60
        self.bitrate = "2M"
        self.encoder = "auto"

class NetworkConfig:
    def __init__(self):
        self.video_port = 5555
        self.control_port = 5556
        self.discovery_port = 5557
        self.buffer_size = 65536

class ConfigManager:
    def __init__(self):
        self.stream_config = StreamConfig()
        self.network_config = NetworkConfig()

# ========== CAPTURE ==========
class HighPerformanceCapture:
    def __init__(self, target_fps=60):
        self.target_fps = target_fps
        self.running = False
        self.frame_queue = queue.Queue(maxsize=2)
        self.thread = None
        self.frame_count = 0
        
    def start_capture(self, on_frame_callback=None):
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, args=(on_frame_callback,), daemon=True)
        self.thread.start()
    
    def _capture_loop(self, on_frame_callback=None):
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            target_frame_time = 1.0 / self.target_fps
            
            while self.running:
                frame_start = time.perf_counter()
                
                try:
                    screenshot = sct.grab(monitor)
                    frame = np.array(screenshot)
                    
                    self.frame_count += 1
                    
                    if on_frame_callback:
                        on_frame_callback(frame)
                    
                    if not self.frame_queue.full():
                        try:
                            self.frame_queue.put_nowait(frame)
                        except queue.Full:
                            pass
                    
                    elapsed = time.perf_counter() - frame_start
                    sleep_time = target_frame_time - elapsed
                    
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                        
                except Exception as e:
                    print(f"Capture error: {e}")
                    time.sleep(0.001)
    
    def stop_capture(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

# ========== ENCODER ==========
class HardwareEncoder:
    def __init__(self, width, height, fps=60, bitrate="2M"):
        self.width = width
        self.height = height
        self.fps = fps
        self.bitrate = bitrate
        self.running = False
        
        self.frame_queue = queue.Queue(maxsize=3)
        self.packet_queue = queue.Queue(maxsize=10)
        
        self.encoder_name = self._select_hardware_encoder()
        self.codec_context = None
        
        print(f"Using encoder: {self.encoder_name}")
    
    def _select_hardware_encoder(self):
        system = platform.system().lower()
        if system == "windows":
            return "h264_nvenc"
        elif system == "darwin":
            return "h264_videotoolbox"
        else:
            return "libx264"
    
    def _setup_codec(self):
        try:
            self.codec_context = av.CodecContext.create(self.encoder_name, 'w')
            self.codec_context.width = self.width
            self.codec_context.height = self.height
            self.codec_context.framerate = self.fps
            self.codec_context.pix_fmt = 'yuv420p'
            
            if 'M' in self.bitrate:
                bitrate_int = int(float(self.bitrate.replace('M', '')) * 1000000)
            else:
                bitrate_int = int(self.bitrate)
            
            self.codec_context.bit_rate = bitrate_int
            
            if self.encoder_name in ['h264_nvenc']:
                self.codec_context.options = {
                    'preset': 'p1',
                    'tune': 'ull',
                    'rc': 'cbr',
                }
            
            self.codec_context.open()
            
        except Exception as e:
            print(f"Encoder setup failed: {e}")
            raise
    
    def start_encoding(self):
        self._setup_codec()
        self.running = True
        self.encode_thread = threading.Thread(target=self._encode_loop, daemon=True)
        self.encode_thread.start()
    
    def _encode_loop(self):
        while self.running:
            try:
                frame = self.frame_queue.get(timeout=0.001)
                if frame is None:
                    continue
                
                av_frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
                av_frame = av_frame.reformat(width=self.width, height=self.height)
                
                packets = self.codec_context.encode(av_frame)
                
                for packet in packets:
                    if packet:
                        if not self.packet_queue.full():
                            self.packet_queue.put_nowait(packet)
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Encoding error: {e}")
                time.sleep(0.001)
    
    def add_frame(self, frame):
        if self.running and not self.frame_queue.full():
            try:
                self.frame_queue.put_nowait(frame)
            except queue.Full:
                pass
    
    def get_packet(self):
        try:
            return self.packet_queue.get_nowait()
        except queue.Empty:
            return None
    
    def stop_encoding(self):
        self.running = False
        # Don't call close() on codec_context - it doesn't exist
        # The context will be garbage collected automatically
        self.codec_context = None

# ========== NETWORK ==========
class Streamer:
    def __init__(self, video_port=5555, control_port=5556):
        self.video_port = video_port
        self.control_port = control_port
        self.running = False
        self.video_socket = None
        self.client_address = None
        self.packet_queue = queue.Queue(maxsize=20)
        self.sent_packets = 0
    
    def start_streaming(self, client_ip):
        try:
            self.client_address = (client_ip, self.video_port)
            self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536 * 4)
            
            self.running = True
            self.stream_thread = threading.Thread(target=self._streaming_loop, daemon=True)
            self.stream_thread.start()
            
            return True
            
        except Exception as e:
            print(f"Stream start error: {e}")
            return False
    
    def _streaming_loop(self):
        while self.running:
            try:
                packet = self.packet_queue.get(timeout=0.001)
                if packet is None:
                    continue
                
                packet_data = packet.to_bytes()
                self.video_socket.sendto(packet_data, self.client_address)
                self.sent_packets += 1
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Streaming error: {e}")
                time.sleep(0.001)
    
    def send_packet(self, packet):
        if self.running and not self.packet_queue.full():
            try:
                self.packet_queue.put_nowait(packet)
            except queue.Full:
                pass
    
    def stop_streaming(self):
        self.running = False
        if self.video_socket:
            self.video_socket.close()

# ========== INPUT ==========
try:
    from pynput import mouse, keyboard
    import pyautogui
    INPUT_AVAILABLE = True
except ImportError:
    INPUT_AVAILABLE = False
    print("Input libraries not available - input forwarding disabled")

class InputForwarder:
    def __init__(self, control_port=5556):
        self.control_port = control_port
        self.running = False
        self.socket = None
        self.client_address = None
        self.mouse_listener = None
        self.keyboard_listener = None
        
    def connect(self, client_ip):
        try:
            self.client_address = (client_ip, self.control_port)
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            if INPUT_AVAILABLE:
                self._start_input_listeners()
            
            return True
        except Exception as e:
            print(f"Input forwarder connection error: {e}")
            return False
    
    def _start_input_listeners(self):
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
    
    def _send_input_event(self, event_data):
        if self.socket and self.client_address:
            try:
                data = json.dumps(event_data).encode('utf-8')
                self.socket.sendto(data, self.client_address)
            except Exception as e:
                print(f"Input send error: {e}")
    
    def _on_mouse_move(self, x, y):
        event = {
            'type': 'mouse',
            'action': 'move',
            'x': x,
            'y': y,
            'timestamp': time.time()
        }
        self._send_input_event(event)
    
    def _on_mouse_click(self, x, y, button, pressed):
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
        
        if INPUT_AVAILABLE:
            try:
                if pressed:
                    pyautogui.mouseDown(x, y, button=button_name)
                else:
                    pyautogui.mouseUp(x, y, button=button_name)
            except Exception as e:
                print(f"Mouse simulation error: {e}")
    
    def _on_mouse_scroll(self, x, y, dx, dy):
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
        
        if INPUT_AVAILABLE:
            try:
                pyautogui.scroll(dy)
            except Exception as e:
                print(f"Scroll simulation error: {e}")
    
    def _on_key_press(self, key):
        try:
            key_str = self._key_to_string(key)
            
            event = {
                'type': 'keyboard',
                'action': 'press',
                'key': key_str,
                'timestamp': time.time()
            }
            self._send_input_event(event)
            
            if INPUT_AVAILABLE:
                try:
                    pyautogui.keyDown(key_str)
                except Exception as e:
                    print(f"Key press simulation error: {e}")
            
        except Exception as e:
            print(f"Key press error: {e}")
    
    def _on_key_release(self, key):
        try:
            key_str = self._key_to_string(key)
            
            event = {
                'type': 'keyboard',
                'action': 'release',
                'key': key_str,
                'timestamp': time.time()
            }
            self._send_input_event(event)
            
            if INPUT_AVAILABLE:
                try:
                    pyautogui.keyUp(key_str)
                except Exception as e:
                    print(f"Key release simulation error: {e}")
            
        except Exception as e:
            print(f"Key release error: {e}")
    
    def _key_to_string(self, key):
        if hasattr(key, 'char') and key.char is not None:
            return key.char
        else:
            return str(key).replace('Key.', '')
    
    def disconnect(self):
        self.running = False
        
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        if self.socket:
            self.socket.close()

# ========== MAIN HOST GUI ==========
class EdgeLiteHost:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.capture = None
        self.encoder = None
        self.streamer = None
        self.input_forwarder = None
        
        self.streaming = False
        self.client_ip = None
        
        self.setup_gui()
    
    def setup_gui(self):
        self.root = tk.Tk()
        self.root.title("EdgeLite Host")
        self.root.geometry("500x400")
        
        # Main container
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(main_frame, text="🎮 EdgeLite Streaming Host", font=('Arial', 16, 'bold'))
        title_label.pack(pady=(0, 20))
        
        # Connection section
        conn_frame = ttk.LabelFrame(main_frame, text="Client Connection", padding="10")
        conn_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(conn_frame, text="Client IP:").pack(side=tk.LEFT)
        self.client_ip_var = tk.StringVar()
        ip_entry = ttk.Entry(conn_frame, textvariable=self.client_ip_var, width=20)
        ip_entry.pack(side=tk.LEFT, padx=(5, 10))
        
        self.connect_btn = ttk.Button(conn_frame, text="Start Streaming", command=self.toggle_streaming)
        self.connect_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # Connection status
        self.connection_status = ttk.Label(conn_frame, text="Disconnected", foreground="red")
        self.connection_status.pack(side=tk.LEFT, padx=(10, 0))
        
        # Settings
        settings_frame = ttk.LabelFrame(main_frame, text="Stream Settings", padding="10")
        settings_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Resolution
        res_frame = ttk.Frame(settings_frame)
        res_frame.pack(fill=tk.X, pady=5)
        ttk.Label(res_frame, text="Resolution:").pack(side=tk.LEFT)
        self.resolution = tk.StringVar(value=f"{self.config_manager.stream_config.width}x{self.config_manager.stream_config.height}")
        res_combo = ttk.Combobox(res_frame, textvariable=self.resolution, values=["1280x720", "1920x1080"], width=15)
        res_combo.pack(side=tk.LEFT, padx=(5, 0))
        
        # Frame rate
        fps_frame = ttk.Frame(settings_frame)
        fps_frame.pack(fill=tk.X, pady=5)
        ttk.Label(fps_frame, text="Frame Rate:").pack(side=tk.LEFT)
        self.fps = tk.StringVar(value=str(self.config_manager.stream_config.fps))
        fps_combo = ttk.Combobox(fps_frame, textvariable=self.fps, values=["30", "60"], width=15)
        fps_combo.pack(side=tk.LEFT, padx=(5, 0))
        
        # Bitrate
        bitrate_frame = ttk.Frame(settings_frame)
        bitrate_frame.pack(fill=tk.X, pady=5)
        ttk.Label(bitrate_frame, text="Bitrate:").pack(side=tk.LEFT)
        self.bitrate = tk.StringVar(value=self.config_manager.stream_config.bitrate)
        bitrate_combo = ttk.Combobox(bitrate_frame, textvariable=self.bitrate, values=["1M", "2M", "5M"], width=15)
        bitrate_combo.pack(side=tk.LEFT, padx=(5, 0))
        
        # Status
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.status_text = tk.Text(status_frame, height=10)
        self.status_text.pack(fill=tk.BOTH, expand=True)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Apply Settings", command=self.apply_settings).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Quit", command=self.quit_app).pack(side=tk.LEFT)
        
        self.log("Host started. Ready to stream.")
        self.log(f"Your IP: {self.get_local_ip()}")
        self.log("Enter client IP and click 'Start Streaming'")
    
    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def toggle_streaming(self):
        if not self.streaming:
            self.start_streaming()
        else:
            self.stop_streaming()
    
    def start_streaming(self):
        client_ip = self.client_ip_var.get().strip()
        if not client_ip:
            messagebox.showerror("Error", "Please enter client IP address")
            return
        
        try:
            width, height = map(int, self.resolution.get().split('x'))
            fps = int(self.fps.get())
            bitrate = self.bitrate.get()
            
            self.capture = HighPerformanceCapture(fps)
            self.encoder = HardwareEncoder(width, height, fps, bitrate)
            self.streamer = Streamer()
            self.input_forwarder = InputForwarder()
            
            self.encoder.start_encoding()
            
            if not self.streamer.start_streaming(client_ip):
                raise Exception("Failed to start streaming")
            
            if not self.input_forwarder.connect(client_ip):
                self.log("Warning: Input forwarding not available")
            
            self.capture.start_capture(on_frame_callback=self.encoder.add_frame)
            
            self.streaming = True
            self.stream_thread = threading.Thread(target=self._stream_packets, daemon=True)
            self.stream_thread.start()
            
            self.client_ip = client_ip
            self.connect_btn.config(text="Stop Streaming")
            self.connection_status.config(text="Connected", foreground="green")
            
            self.log(f"Started streaming to {client_ip}")
            self.log(f"Resolution: {width}x{height} {fps}fps")
            self.log(f"Encoder: {self.encoder.encoder_name}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start streaming: {e}")
            self.log(f"Stream start error: {e}")
            self.cleanup_components()
    
    def _stream_packets(self):
        while self.streaming:
            try:
                packet = self.encoder.get_packet()
                if packet:
                    self.streamer.send_packet(packet)
                else:
                    time.sleep(0.001)
            except Exception as e:
                self.log(f"Packet streaming error: {e}")
                time.sleep(0.001)
    
    def stop_streaming(self):
        self.streaming = False
        self.cleanup_components()
        
        self.connect_btn.config(text="Start Streaming")
        self.connection_status.config(text="Disconnected", foreground="red")
        self.log("Streaming stopped")
    
    def cleanup_components(self):
        if self.capture:
            self.capture.stop_capture()
            self.capture = None
        
        if self.encoder:
            self.encoder.stop_encoding()
            self.encoder = None
        
        if self.streamer:
            self.streamer.stop_streaming()
            self.streamer = None
        
        if self.input_forwarder:
            self.input_forwarder.disconnect()
            self.input_forwarder = None
    
    def apply_settings(self):
        try:
            width, height = map(int, self.resolution.get().split('x'))
            self.config_manager.stream_config.width = width
            self.config_manager.stream_config.height = height
            self.config_manager.stream_config.fps = int(self.fps.get())
            self.config_manager.stream_config.bitrate = self.bitrate.get()
            
            self.log("Settings applied")
            
        except Exception as e:
            messagebox.showerror("Error", f"Invalid settings: {e}")
    
    def log(self, message):
        self.status_text.insert(tk.END, f"{time.strftime('%H:%M:%S')} - {message}\n")
        self.status_text.see(tk.END)
    
    def clear_log(self):
        self.status_text.delete(1.0, tk.END)
    
    def quit_app(self):
        self.streaming = False
        self.cleanup_components()
        self.root.quit()
    
    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit_app()
        finally:
            self.quit_app()

if __name__ == "__main__":
    print("Starting EdgeLite Host...")
    app = EdgeLiteHost()
    app.run()
