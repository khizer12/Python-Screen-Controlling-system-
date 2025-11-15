import av
import numpy as np
import threading
import queue
import time
import platform
from typing import Optional, Callable
import sys

class CrossPlatformVideoReceiver:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.connected = False
        self.socket = None
        self.input_stream = None
        self.video_stream = None
        self.frame_queue = queue.Queue(maxsize=2)
        self.current_frame = None
        self.last_frame_time = 0
        self.fps = 0
        self.frame_count = 0
        self.fps_update_time = time.time()
        self.on_frame_callback = None
        
        # Cross-platform hardware decoder selection
        self.decoder_name = self._get_platform_decoder()
        print(f"Platform: {platform.system()}, Using decoder: {self.decoder_name}")
    
    def _get_platform_decoder(self):
        """Select appropriate hardware decoder based on platform"""
        system = platform.system().lower()
        
        if system == "darwin":  # macOS
            return self._get_macos_decoder()
        elif system == "linux":
            return self._get_linux_decoder()
        elif system == "windows":
            return self._get_windows_decoder()
        else:
            return "h264"  # Software fallback
    
    def _get_macos_decoder(self):
        """Get hardware decoder for macOS"""
        try:
            # Test VideoToolbox availability
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
            'h264_v4l2m2m',  # V4L2 Memory-to-Memory (Raspberry Pi)
            'h264_mmal',     # Raspberry Pi MMAL
            'h264_cuvid',    # NVIDIA CUDA
        ]
        
        for decoder in decoders_to_try:
            try:
                codec = av.CodecContext.create(decoder, 'r')
                codec.close()
                print(f"Using Linux decoder: {decoder}")
                return decoder
            except:
                continue
        
        print("No Linux hardware decoder found, using software")
        return 'h264'
    
    def _get_windows_decoder(self):
        """Get hardware decoder for Windows"""
        decoders_to_try = [
            'h264_cuvid',    # NVIDIA CUDA
            'h264_d3d11va',  # DirectX 11
            'h264_dxva2',    # DirectX Video Acceleration
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
        try:
            # UDP stream connection with cross-platform options
            stream_url = f"udp://{host_ip}:{self.config_manager.network_config.video_port}"
            
            # Platform-specific options
            options = {
                'fflags': 'nobuffer',
                'flags': 'low_delay',
                'framedrop': '1',
                'strict': 'experimental'
            }
            
            # Add platform-specific buffer options
            if platform.system().lower() == 'linux':
                options['bufsize'] = '1000000'  # Smaller buffer for Linux
            
            self.input_stream = av.open(stream_url, mode='r', options=options)
            
            # Find video stream
            self.video_stream = next(s for s in self.input_stream.streams if s.type == 'video')
            
            # Use hardware acceleration if available
            if self.decoder_name != "h264":
                try:
                    codec = av.CodecContext.create(self.decoder_name, 'r')
                    self.video_stream.codec_context = codec
                except Exception as e:
                    print(f"Hardware decoder failed, falling back to software: {e}")
                    self.decoder_name = "h264"
            
            self.connected = True
            
            # Start frame processing thread
            thread = threading.Thread(target=self._receive_loop, daemon=True)
            thread.start()
            
            # Start FPS calculation thread
            fps_thread = threading.Thread(target=self._fps_loop, daemon=True)
            fps_thread.start()
            
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
                        self._update_frame_stats()
                        
                        # Store current frame
                        self.current_frame = img
                        
                        # Call callback if set
                        if self.on_frame_callback:
                            self.on_frame_callback(img)
                        
                        # Put in queue (non-blocking)
                        if not self.frame_queue.full():
                            try:
                                self.frame_queue.put_nowait(img)
                            except queue.Full:
                                pass  # Drop frame to maintain low latency
                                
        except Exception as e:
            if self.connected:
                print(f"Receive loop error: {e}")
    
    def _update_frame_stats(self):
        """Update FPS and timing statistics"""
        current_time = time.time()
        self.frame_count += 1
        
        # Update FPS every second
        if current_time - self.fps_update_time >= 1.0:
            self.fps = self.frame_count
            self.frame_count = 0
            self.fps_update_time = current_time
        
        self.last_frame_time = current_time
    
    def _fps_loop(self):
        """Background FPS monitoring"""
        while self.connected:
            time.sleep(1.0)
    
    def get_frame(self) -> Optional[np.ndarray]:
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
        current_time = time.time()
        latency = current_time - self.last_frame_time if self.last_frame_time > 0 else 0
        
        return {
            'fps': self.fps,
            'latency': latency,
            'connected': self.connected,
            'decoder': self.decoder_name,
            'queue_size': self.frame_queue.qsize(),
            'platform': platform.system()
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