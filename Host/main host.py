import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import sys
import os
import platform

# Add shared directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from capture import CrossPlatformCapture
from encoder import CrossPlatformEncoder
from network import EnhancedStreamer
from input import CrossPlatformInputForwarder
from performance import PerformanceMonitor
from config import ConfigManager
from networking import NetworkDiscovery

class EdgeLiteHost:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.capture = None
        self.encoder = None
        self.streamer = None
        self.input_forwarder = None
        self.discovery = None
        self.performance_monitor = None
        
        self.streaming = False
        self.client_ip = None
        self.platform = platform.system().lower()
        
        # Performance monitoring
        self.stats_update_interval = 1.0
        self.last_stats_update = 0
        
        # Initialize GUI
        self.setup_gui()
    
    def setup_gui(self):
        """Setup the host control GUI with platform-specific styling"""
        self.root = tk.Tk()
        self.root.title(f"EdgeLite Host - {self.platform.capitalize()}")
        self.root.geometry("600x700")
        
        # Platform-specific styling
        self.setup_platform_styling()
        
        # Main container
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Title
        title_label = ttk.Label(main_frame, text="🎮 EdgeLite Streaming Host", style='Title.TLabel')
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 20))
        
        # Platform info
        platform_label = ttk.Label(main_frame, text=f"Platform: {self.platform}", style='Platform.TLabel')
        platform_label.grid(row=1, column=0, columnspan=3, pady=(0, 10))
        
        # Connection section
        self.setup_connection_section(main_frame, 2)
        
        # Capture settings
        self.setup_capture_section(main_frame, 3)
        
        # Performance stats
        self.setup_stats_section(main_frame, 4)
        
        # System stats
        self.setup_system_stats_section(main_frame, 5)
        
        # Log area
        self.setup_log_section(main_frame, 6)
        
        # Control buttons
        self.setup_control_buttons(main_frame, 7)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(6, weight=1)
        
        # Start services
        self.start_services()
        
        # Start stats update loop
        self.update_stats()
    
    def setup_platform_styling(self):
        """Setup platform-specific styling"""
        style = ttk.Style()
        
        if self.platform == "darwin":
            # macOS styling
            style.configure('Title.TLabel', font=('Helvetica', 16, 'bold'))
            style.configure('Platform.TLabel', font=('Helvetica', 10, 'italic'))
            style.configure('Status.TLabel', font=('Helvetica', 10, 'bold'))
        elif self.platform == "linux":
            # Linux styling
            style.configure('Title.TLabel', font=('DejaVu Sans', 16, 'bold'))
            style.configure('Platform.TLabel', font=('DejaVu Sans', 10, 'italic'))
            style.configure('Status.TLabel', font=('DejaVu Sans', 10, 'bold'))
        else:
            # Windows/default styling
            style.configure('Title.TLabel', font=('Arial', 16, 'bold'))
            style.configure('Platform.TLabel', font=('Arial', 10, 'italic'))
            style.configure('Status.TLabel', font=('Arial', 10, 'bold'))
    
    def setup_connection_section(self, parent, row):
        """Setup connection controls"""
        conn_frame = ttk.LabelFrame(parent, text="Client Connection", padding="10")
        conn_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(conn_frame, text="Client IP:").grid(row=0, column=0, sticky=tk.W)
        self.client_ip_var = tk.StringVar()
        ip_entry = ttk.Entry(conn_frame, textvariable=self.client_ip_var, width=20)
        ip_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(5, 10))
        
        self.connect_btn = ttk.Button(conn_frame, text="Start Streaming", 
                                    command=self.toggle_streaming, width=15)
        self.connect_btn.grid(row=0, column=2, padx=(0, 5))
        
        # Auto-discovery button
        ttk.Button(conn_frame, text="Auto-Detect", 
                  command=self.auto_detect_client).grid(row=0, column=3)
        
        # Connection status
        self.connection_status = ttk.Label(conn_frame, text="Disconnected", 
                                         foreground="red", style='Status.TLabel')
        self.connection_status.grid(row=1, column=0, columnspan=4, pady=(5, 0))
        
        conn_frame.columnconfigure(1, weight=1)
    
    def setup_capture_section(self, parent, row):
        """Setup capture settings"""
        capture_frame = ttk.LabelFrame(parent, text="Capture Settings", padding="10")
        capture_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Resolution
        ttk.Label(capture_frame, text="Resolution:").grid(row=0, column=0, sticky=tk.W)
        self.resolution_var = tk.StringVar(value=f"{self.config_manager.stream_config.width}x{self.config_manager.stream_config.height}")
        res_combo = ttk.Combobox(capture_frame, textvariable=self.resolution_var, 
                                values=["1280x720", "1920x1080", "2560x1440"], state="readonly")
        res_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(5, 10))
        
        # Frame rate
        ttk.Label(capture_frame, text="Frame Rate:").grid(row=0, column=2, sticky=tk.W)
        self.fps_var = tk.StringVar(value=str(self.config_manager.stream_config.fps))
        fps_combo = ttk.Combobox(capture_frame, textvariable=self.fps_var, 
                                values=["30", "60", "120", "144"], state="readonly")
        fps_combo.grid(row=0, column=3, sticky=(tk.W, tk.E), padx=(5, 0))
        
        # Bitrate
        ttk.Label(capture_frame, text="Bitrate:").grid(row=1, column=0, sticky=tk.W, pady=(10, 0))
        self.bitrate_var = tk.StringVar(value=self.config_manager.stream_config.bitrate)
        bitrate_combo = ttk.Combobox(capture_frame, textvariable=self.bitrate_var,
                                    values=["1M", "2M", "5M", "10M", "20M"], state="readonly")
        bitrate_combo.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=(10, 0), padx=(5, 10))
        
        # Encoder
        ttk.Label(capture_frame, text="Encoder:").grid(row=1, column=2, sticky=tk.W, pady=(10, 0))
        self.encoder_var = tk.StringVar(value=self.config_manager.stream_config.encoder)
        
        # Platform-specific encoder options
        if self.platform == "darwin":
            encoder_options = ["auto", "h264_videotoolbox", "libx264"]
        elif self.platform == "linux":
            encoder_options = ["auto", "h264_vaapi", "h264_nvenc", "libx264"]
        else:  # windows
            encoder_options = ["auto", "h264_nvenc", "h264_amf", "h264_qsv", "libx264"]
            
        encoder_combo = ttk.Combobox(capture_frame, textvariable=self.encoder_var,
                                    values=encoder_options, state="readonly")
        encoder_combo.grid(row=1, column=3, sticky=(tk.W, tk.E), pady=(10, 0), padx=(5, 0))
        
        capture_frame.columnconfigure(1, weight=1)
        capture_frame.columnconfigure(3, weight=1)
    
    def setup_stats_section(self, parent, row):
        """Setup performance statistics"""
        stats_frame = ttk.LabelFrame(parent, text="Stream Performance", padding="10")
        stats_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Capture stats
        ttk.Label(stats_frame, text="Capture:").grid(row=0, column=0, sticky=tk.W)
        self.capture_stats_label = ttk.Label(stats_frame, text="0 fps, 0ms")
        self.capture_stats_label.grid(row=0, column=1, sticky=tk.W, padx=(5, 20))
        
        # Encode stats
        ttk.Label(stats_frame, text="Encode:").grid(row=0, column=2, sticky=tk.W)
        self.encode_stats_label = ttk.Label(stats_frame, text="0 fps, 0ms")
        self.encode_stats_label.grid(row=0, column=3, sticky=tk.W, padx=(5, 20))
        
        # Network stats
        ttk.Label(stats_frame, text="Network:").grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.network_stats_label = ttk.Label(stats_frame, text="0 pps, 0 Mbps")
        self.network_stats_label.grid(row=1, column=1, sticky=tk.W, pady=(5, 0), padx=(5, 20))
        
        # Encoder info
        ttk.Label(stats_frame, text="Encoder:").grid(row=1, column=2, sticky=tk.W, pady=(5, 0))
        self.encoder_info_label = ttk.Label(stats_frame, text="None")
        self.encoder_info_label.grid(row=1, column=3, sticky=tk.W, pady=(5, 0), padx=(5, 0))
        
        stats_frame.columnconfigure(1, weight=1)
        stats_frame.columnconfigure(3, weight=1)
    
    def setup_system_stats_section(self, parent, row):
        """Setup system performance statistics"""
        system_frame = ttk.LabelFrame(parent, text="System Performance", padding="10")
        system_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # CPU
        ttk.Label(system_frame, text="CPU:").grid(row=0, column=0, sticky=tk.W)
        self.cpu_label = ttk.Label(system_frame, text="0%")
        self.cpu_label.grid(row=0, column=1, sticky=tk.W, padx=(5, 20))
        
        # Memory
        ttk.Label(system_frame, text="Memory:").grid(row=0, column=2, sticky=tk.W)
        self.memory_label = ttk.Label(system_frame, text="0 MB")
        self.memory_label.grid(row=0, column=3, sticky=tk.W, padx=(5, 20))
        
        # Network
        ttk.Label(system_frame, text="Network:").grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.net_system_label = ttk.Label(system_frame, text="0 MB/s")
        self.net_system_label.grid(row=1, column=1, sticky=tk.W, pady=(5, 0), padx=(5, 20))
        
        # Threads
        ttk.Label(system_frame, text="Threads:").grid(row=1, column=2, sticky=tk.W, pady=(5, 0))
        self.threads_label = ttk.Label(system_frame, text="0")
        self.threads_label.grid(row=1, column=3, sticky=tk.W, pady=(5, 0), padx=(5, 0))
        
        system_frame.columnconfigure(1, weight=1)
        system_frame.columnconfigure(3, weight=1)
    
    def setup_log_section(self, parent, row):
        """Setup logging area"""
        log_frame = ttk.LabelFrame(parent, text="Event Log", padding="10")
        log_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        self.log_text = tk.Text(log_frame, height=8, width=70, state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
    
    def setup_control_buttons(self, parent, row):
        """Setup control buttons"""
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=row, column=0, columnspan=3, pady=(10, 0))
        
        ttk.Button(button_frame, text="Apply Settings", 
                  command=self.apply_settings).grid(row=0, column=0, padx=(0, 10))
        ttk.Button(button_frame, text="Clear Log", 
                  command=self.clear_log).grid(row=0, column=1, padx=(0, 10))
        ttk.Button(button_frame, text="Performance Test", 
                  command=self.run_performance_test).grid(row=0, column=2, padx=(0, 10))
        ttk.Button(button_frame, text="Quit", 
                  command=self.quit_app).grid(row=0, column=3)
    
    def auto_detect_client(self):
        """Auto-detect client on network"""
        self.log("Auto-detection not yet implemented - enter client IP manually")
        # In a full implementation, this would use mDNS or similar for discovery
    
    def start_services(self):
        """Start background services"""
        # Start network discovery
        self.discovery = NetworkDiscovery(self.config_manager.network_config.discovery_port)
        
        # Start performance monitoring
        self.performance_monitor = PerformanceMonitor()
        self.performance_monitor.start_monitoring()
        
        # Get local IP for broadcasting
        local_ip = self.get_local_ip()
        host_name = platform.node()
        
        self.discovery.broadcast_host(host_name, local_ip, self.config_manager.network_config.video_port)
        self.log(f"Host broadcasting as {host_name} ({local_ip}) on {self.platform}")
        
        # Platform-specific startup messages
        if self.platform == "darwin":
            self.log("macOS: Ensure screen recording permissions are granted")
        elif self.platform == "linux":
            self.log("Linux: Input forwarding should work out of the box")
    
    def get_local_ip(self):
        """Get local IP address (cross-platform)"""
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def toggle_streaming(self):
        """Toggle streaming on/off"""
        if not self.streaming:
            self.start_streaming()
        else:
            self.stop_streaming()
    
    def start_streaming(self):
        """Start streaming to client"""
        client_ip = self.client_ip_var.get().strip()
        if not client_ip:
            messagebox.showerror("Error", "Please enter client IP address")
            return
        
        try:
            # Parse settings
            width, height = map(int, self.resolution_var.get().split('x'))
            fps = int(self.fps_var.get())
            bitrate = self.bitrate_var.get()
            
            # Initialize components
            self.capture = CrossPlatformCapture(fps)
            self.encoder = CrossPlatformEncoder(width, height, fps, bitrate)
            self.streamer = EnhancedStreamer()
            self.input_forwarder = CrossPlatformInputForwarder()
            
            # Start encoding
            self.encoder.start_encoding()
            
            # Start streaming
            if not self.streamer.start_streaming(client_ip):
                raise Exception("Failed to start streaming")
            
            # Setup input forwarding
            display_info = self.get_display_info()
            self.input_forwarder.set_scaling(
                display_info['width'], display_info['height'],
                width, height
            )
            if not self.input_forwarder.connect(client_ip):
                self.log("Warning: Input forwarding not available")
            
            # Start capture with direct frame callback to encoder
            self.capture.start_capture(on_frame_callback=self.encoder.add_frame)
            
            # Start packet streaming thread
            self.streaming = True
            self.stream_thread = threading.Thread(target=self._stream_packets, daemon=True)
            self.stream_thread.start()
            
            # Update UI
            self.streaming = True
            self.client_ip = client_ip
            self.connect_btn.config(text="Stop Streaming")
            self.connection_status.config(text=f"Connected to {client_ip}", foreground="green")
            
            self.log(f"Started streaming to {client_ip} at {width}x{height} {fps}fps")
            self.log(f"Using {self.encoder.encoder_name} encoder on {self.platform}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start streaming: {e}")
            self.log(f"Stream start error: {e}")
            self.cleanup_components()
    
    def _stream_packets(self):
        """Stream packets in background thread"""
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
        """Stop streaming"""
        self.streaming = False
        self.cleanup_components()
        
        # Update UI
        self.connect_btn.config(text="Start Streaming")
        self.connection_status.config(text="Disconnected", foreground="red")
        self.log("Streaming stopped")
    
    def cleanup_components(self):
        """Cleanup all streaming components"""
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
    
    def get_display_info(self):
        """Get primary display information"""
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                return {
                    'width': monitor['width'],
                    'height': monitor['height']
                }
        except:
            return {'width': 1920, 'height': 1080}
    
    def apply_settings(self):
        """Apply new settings"""
        try:
            # Update config
            width, height = map(int, self.resolution_var.get().split('x'))
            self.config_manager.stream_config.width = width
            self.config_manager.stream_config.height = height
            self.config_manager.stream_config.fps = int(self.fps_var.get())
            self.config_manager.stream_config.bitrate = self.bitrate_var.get()
            self.config_manager.stream_config.encoder = self.encoder_var.get()
            
            self.config_manager.save_config()
            self.log("Settings applied and saved")
            
        except Exception as e:
            messagebox.showerror("Error", f"Invalid settings: {e}")
    
    def run_performance_test(self):
        """Run a quick performance test"""
        self.log("Running performance test...")
        # In a full implementation, this would measure capture/encode latency
    
    def update_stats(self):
        """Update performance statistics"""
        if self.streaming and self.capture and self.encoder and self.streamer:
            # Get stats from components
            capture_stats = self.capture.get_stats()
            encode_stats = self.encoder.get_stats()
            network_stats = self.streamer.get_stats()
            
            # Update labels
            self.capture_stats_label.config(
                text=f"{capture_stats['current_fps']} fps, {capture_stats['average_capture_time_ms']:.1f}ms"
            )
            self.encode_stats_label.config(
                text=f"{encode_stats['encoded_frames']} frames, {encode_stats['average_encode_time_ms']:.1f}ms"
            )
            self.network_stats_label.config(
                text=f"{network_stats['recent_packet_rate']} pps, {network_stats['average_bandwidth_mbps']:.1f} Mbps"
            )
            self.encoder_info_label.config(
                text=f"{encode_stats['encoder']}"
            )
        
        # Update system stats
        if self.performance_monitor:
            system_stats = self.performance_monitor.get_stats()
            if system_stats:
                self.cpu_label.config(text=f"{system_stats['system']['cpu_percent']:.1f}%")
                self.memory_label.config(text=f"{system_stats['process']['memory_mb']:.1f} MB")
                self.threads_label.config(text=f"{system_stats['process']['thread_count']}")
                
                # Calculate network usage
                net_sent = system_stats['system']['net_sent_mb']
                net_recv = system_stats['system']['net_recv_mb']
                self.net_system_label.config(text=f"↑{net_sent:.1f} ↓{net_recv:.1f} MB/s")
        
        # Schedule next update
        self.root.after(1000, self.update_stats)
    
    def log(self, message: str):
        """Add message to log"""
        self.log_text.config(state=tk.NORMAL)
        timestamp = time.strftime('%H:%M:%S')
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def clear_log(self):
        """Clear log"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def quit_app(self):
        """Cleanup and quit"""
        self.streaming = False
        self.cleanup_components()
        
        if self.discovery:
            self.discovery.stop_discovery()
        
        if self.performance_monitor:
            self.performance_monitor.stop_monitoring()
        
        self.root.quit()
        self.root.destroy()
    
    def run(self):
        """Start the application"""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit_app()
        finally:
            self.quit_app()

def main():
    """Main entry point"""
    app = EdgeLiteHost()
    app.run()

if __name__ == "__main__":
    main()