import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import cv2
import numpy as np
from PIL import Image, ImageTk
import platform
import os
import sys

class CrossPlatformVideoDisplay:
    def __init__(self, parent, width=1280, height=720):
        self.parent = parent
        self.width = width
        self.height = height
        self.current_image = None
        self.platform = platform.system().lower()
        
        # Choose rendering method based on platform
        self.use_sdl = self._setup_display_method()
        
        if self.use_sdl:
            self.setup_sdl_display()
        else:
            self.setup_tkinter_display()
    
    def _setup_display_method(self):
        """Determine the best display method for the platform"""
        # On all platforms, prefer Tkinter for simplicity and compatibility
        # SDL2 can be problematic on some Linux distributions and macOS
        return False  # Default to Tkinter for maximum compatibility
    
    def setup_sdl_display(self):
        """Setup SDL2 window for high-performance rendering (optional)"""
        try:
            import sdl2
            import sdl2.ext
            
            sdl2.ext.init()
            self.sdl_window = sdl2.ext.Window(
                "EdgeLite Client", 
                size=(self.width, self.height)
            )
            self.sdl_renderer = sdl2.ext.Renderer(self.sdl_window)
            self.sdl_window.show()
            print("Using SDL2 for high-performance rendering")
        except ImportError:
            print("SDL2 not available, using Tkinter")
            self.setup_tkinter_display()
        except Exception as e:
            print(f"SDL2 setup failed: {e}, using Tkinter")
            self.setup_tkinter_display()
    
    def setup_tkinter_display(self):
        """Setup Tkinter-based video display (cross-platform)"""
        self.frame = ttk.Frame(self.parent)
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # Video label with platform-specific styling
        self.video_label = ttk.Label(
            self.frame, 
            text="Waiting for video stream...",
            background='black',
            foreground='white',
            font=('Arial', 12),
            anchor='center'
        )
        self.video_label.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # Status bar with platform-appropriate layout
        self.status_frame = ttk.Frame(self.frame)
        self.status_frame.pack(fill=tk.X, padx=2, pady=2)
        
        self.fps_label = ttk.Label(self.status_frame, text="FPS: 0")
        self.fps_label.pack(side=tk.LEFT, padx=5)
        
        self.latency_label = ttk.Label(self.status_frame, text="Latency: 0ms")
        self.latency_label.pack(side=tk.LEFT, padx=5)
        
        # Platform-specific info
        platform_info = f"{platform.system()} {platform.release()}"
        self.platform_label = ttk.Label(self.status_frame, text=platform_info)
        self.platform_label.pack(side=tk.RIGHT, padx=5)
        
        self.resolution_label = ttk.Label(self.status_frame, text=f"{self.width}x{self.height}")
        self.resolution_label.pack(side=tk.RIGHT, padx=5)
    
    def update_frame(self, frame, stats):
        """Update the video display with new frame"""
        if frame is None:
            return
        
        if self.use_sdl:
            self._update_sdl_frame(frame, stats)
        else:
            self._update_tkinter_frame(frame, stats)
    
    def _update_sdl_frame(self, frame, stats):
        """Update SDL2 display"""
        try:
            import sdl2
            
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Resize if needed
            if frame.shape[:2] != (self.height, self.width):
                rgb_frame = cv2.resize(rgb_frame, (self.width, self.height))
            
            # Create SDL surface from frame
            surface = sdl2.SDL_CreateRGBSurfaceFrom(
                rgb_frame.ctypes.data, 
                rgb_frame.shape[1], rgb_frame.shape[0], 
                24, rgb_frame.shape[1] * 3,
                0x0000FF, 0x00FF00, 0xFF0000, 0
            )
            
            # Render to window
            texture = sdl2.SDL_CreateTextureFromSurface(self.sdl_renderer.sdlrenderer, surface)
            sdl2.SDL_RenderCopy(self.sdl_renderer.sdlrenderer, texture, None, None)
            sdl2.SDL_RenderPresent(self.sdl_renderer.sdlrenderer)
            sdl2.SDL_DestroyTexture(texture)
            sdl2.SDL_FreeSurface(surface)
            
        except Exception as e:
            print(f"SDL frame update error: {e}")
    
    def _update_tkinter_frame(self, frame, stats):
        """Update Tkinter display (cross-platform)"""
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
            latency_ms = int(stats.get('latency', 0) * 1000)
            self.latency_label.config(text=f"Latency: {latency_ms}ms")
            
        except Exception as e:
            print(f"Tkinter frame update error: {e}")
    
    def destroy(self):
        """Cleanup resources"""
        if hasattr(self, 'sdl_window'):
            try:
                import sdl2
                self.sdl_window.close()
            except:
                pass

class CrossPlatformClientGUI:
    def __init__(self, config_manager, video_receiver, input_sender, discovery):
        self.config_manager = config_manager
        self.receiver = video_receiver
        self.input_sender = input_sender
        self.discovery = discovery
        
        self.root = tk.Tk()
        self.setup_window()
        
        self.connected = False
        self.host_ip = tk.StringVar()
        self.discovered_hosts = []
        
        self.setup_gui()
        
        # Set frame callback for real-time updates
        self.receiver.set_frame_callback(self.on_new_frame)
    
    def setup_window(self):
        """Setup the main window with platform-specific settings"""
        self.root.title("EdgeLite Client")
        self.root.geometry("1024x768")
        
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
    
    def setup_gui(self):
        """Setup the main client GUI with cross-platform compatibility"""
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
        self.hosts_combo = ttk.Combobox(control_frame, values=[], state="readonly", width=30)
        self.hosts_combo.grid(row=0, column=4, padx=(5, 5))
        self.hosts_combo.bind('<<ComboboxSelected>>', self.on_host_selected)
        
        # Stats display
        stats_frame = ttk.Frame(control_frame)
        stats_frame.grid(row=0, column=5, sticky=(tk.W, tk.E), padx=(10, 0))
        
        self.connection_status = ttk.Label(stats_frame, text="Disconnected", foreground="red")
        self.connection_status.pack(side=tk.LEFT, padx=(0, 10))
        
        self.decoder_label = ttk.Label(stats_frame, text="Decoder: None")
        self.decoder_label.pack(side=tk.LEFT, padx=(0, 10))
        
        control_frame.columnconfigure(4, weight=1)
        
        # Video display area
        self.video_display = CrossPlatformVideoDisplay(self.root)
        if hasattr(self.video_display, 'frame'):
            self.video_display.frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Status log
        log_frame = ttk.LabelFrame(self.root, text="Log", padding="5")
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=10, pady=5)
        
        self.log_text = tk.Text(log_frame, height=6, width=80)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        log_scrollbar = ttk.Scrollbar(self.log_text, orient="vertical", command=self.log_text.yview)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        # Platform-specific input handling
        self.setup_platform_input()
        
        self.log(f"Client initialized on {platform.system()} {platform.release()}")
        self.log("Ready to connect to host.")
    
    def setup_platform_input(self):
        """Setup input forwarding with platform-specific considerations"""
        if hasattr(self.video_display, 'video_label'):
            self.video_display.video_label.bind('<FocusIn>', self.on_video_focus)
            self.video_display.video_label.bind('<FocusOut>', self.on_video_blur)
            self.video_display.video_label.focus_set()
            
            # Platform-specific input hints
            platform_name = platform.system().lower()
            if platform_name == "darwin":
                self.log("macOS: Ensure accessibility permissions for input forwarding")
            elif platform_name == "linux":
                self.log("Linux: Input forwarding should work out of the box")
    
    def on_video_focus(self, event):
        """When video display gets focus"""
        self.log("Video display focused - input forwarding active")
    
    def on_video_blur(self, event):
        """When video display loses focus"""
        self.log("Video display unfocused - input forwarding inactive")
    
    def on_new_frame(self, frame):
        """Callback for new video frames"""
        if hasattr(self, 'video_display'):
            stats = self.receiver.get_stats()
            # Schedule GUI update in main thread
            self.root.after(0, self.update_display, frame, stats)
    
    def update_display(self, frame, stats):
        """Update video display and stats in main thread"""
        self.video_display.update_frame(frame, stats)
        
        # Update connection status
        if stats['connected']:
            self.connection_status.config(text="Connected", foreground="green")
            self.decoder_label.config(text=f"Decoder: {stats['decoder']}")
        else:
            self.connection_status.config(text="Disconnected", foreground="red")
    
    def start_discovery(self):
        """Start network host discovery"""
        self.discovery.start_discovery(self.on_host_discovered)
        self.log("Started host discovery...")
    
    def on_host_discovered(self, host_info: dict, ip: str):
        """Handle discovered hosts"""
        host_str = f"{host_info['host_name']} ({ip})"
        if host_str not in self.discovered_hosts:
            self.discovered_hosts.append(host_str)
            self.hosts_combo['values'] = self.discovered_hosts
            self.log(f"Discovered host: {host_str}")
    
    def on_host_selected(self, event):
        """Handle host selection from dropdown"""
        selected = self.hosts_combo.get()
        # Extract IP from string like "HostName (192.168.1.100)"
        ip = selected.split('(')[1].rstrip(')')
        self.host_ip.set(ip)
        self.log(f"Selected host: {ip}")
    
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
        
        if self.receiver.connect(self.host_ip.get()):
            self.connected = True
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
            
            self.log(f"Connected to {self.host_ip.get()}")
            self.log(f"Using {self.receiver.decoder_name} decoder")
            
            # Platform-specific connection message
            if platform.system().lower() == "darwin":
                self.log("macOS: Input forwarding requires accessibility permissions")
        else:
            messagebox.showerror("Error", "Failed to connect to host")
    
    def disconnect_from_host(self):
        """Disconnect from host"""
        self.receiver.disconnect()
        self.input_sender.disconnect()
        self.connected = False
        self.connect_btn.config(text="Connect")
        self.connection_status.config(text="Disconnected", foreground="red")
        self.log("Disconnected from host")
    
    def log(self, message: str):
        """Add message to log"""
        timestamp = time.strftime('%H:%M:%S')
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
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
        self.root.quit()