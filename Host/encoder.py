import av
import numpy as np
import threading
import queue
import time
from typing import Optional, Callable
import platform

class CrossPlatformEncoder:
    def __init__(self, width: int, height: int, fps: int = 60, bitrate: str = "2M"):
        self.width = width
        self.height = height
        self.fps = fps
        self.bitrate = bitrate
        self.running = False
        self.platform = platform.system().lower()
        
        # Performance tracking
        self.frame_count = 0
        self.encode_times = []
        self.average_encode_time = 0
        
        # Queues for frame input and packet output
        self.frame_queue = queue.Queue(maxsize=3)
        self.packet_queue = queue.Queue(maxsize=10)
        
        # Hardware encoder selection
        self.encoder_name = self._select_platform_encoder()
        self.codec_context = None
        
        print(f"Platform: {self.platform}, Using encoder: {self.encoder_name}")
    
    def _select_platform_encoder(self) -> str:
        """Select the best available hardware encoder for the platform"""
        if self.platform == "windows":
            return self._select_windows_encoder()
        elif self.platform == "darwin":
            return self._select_macos_encoder()
        elif self.platform == "linux":
            return self._select_linux_encoder()
        else:
            return 'libx264'  # Software fallback
    
    def _select_windows_encoder(self) -> str:
        """Select encoder for Windows"""
        encoders_to_try = [
            'h264_nvenc',    # NVIDIA
            'h264_amf',      # AMD
            'h264_qsv',      # Intel QuickSync
            'h264_mf',       # Media Foundation
        ]
        
        for encoder in encoders_to_try:
            try:
                codec = av.CodecContext.create(encoder, 'w')
                codec.close()
                return encoder
            except:
                continue
        
        return 'libx264'
    
    def _select_macos_encoder(self) -> str:
        """Select encoder for macOS"""
        try:
            codec = av.CodecContext.create('h264_videotoolbox', 'w')
            codec.close()
            return 'h264_videotoolbox'
        except:
            return 'libx264'
    
    def _select_linux_encoder(self) -> str:
        """Select encoder for Linux"""
        encoders_to_try = [
            'h264_vaapi',    # Intel/AMD VA-API
            'h264_nvenc',    # NVIDIA
            'h264_omx',      # Raspberry Pi
        ]
        
        for encoder in encoders_to_try:
            try:
                codec = av.CodecContext.create(encoder, 'w')
                codec.close()
                return encoder
            except:
                continue
        
        return 'libx264'
    
    def _setup_codec(self):
        """Setup hardware-optimized codec configuration"""
        try:
            self.codec_context = av.CodecContext.create(self.encoder_name, 'w')
            
            # Basic configuration
            self.codec_context.width = self.width
            self.codec_context.height = self.height
            self.codec_context.framerate = self.fps
            self.codec_context.pix_fmt = 'yuv420p'
            
            # Parse bitrate
            if 'M' in self.bitrate:
                bitrate_int = int(float(self.bitrate.replace('M', '')) * 1000000)
            elif 'K' in self.bitrate:
                bitrate_int = int(float(self.bitrate.replace('K', '')) * 1000)
            else:
                bitrate_int = int(self.bitrate)
            
            self.codec_context.bit_rate = bitrate_int
            
            # Platform-specific optimizations
            self._setup_platform_encoder_options()
            
            # Open codec
            self.codec_context.open()
            
        except Exception as e:
            print(f"Encoder setup failed: {e}")
            raise
    
    def _setup_platform_encoder_options(self):
        """Setup platform-specific encoder options"""
        if self.encoder_name in ['h264_nvenc', 'h264_amf', 'h264_qsv']:
            # Windows hardware encoders
            self.codec_context.options = {
                'preset': 'p1',           # Fastest preset
                'tune': 'ull',           # Ultra low latency
                'rc': 'cbr',             # Constant bitrate
                'zerolatency': '1',
                'delay': '0',
                'forced-idr': '1',
                'b_ref_mode': 'disabled' # No B-frames for lower latency
            }
        elif self.encoder_name == 'h264_videotoolbox':
            # macOS VideoToolbox
            self.codec_context.options = {
                'realtime': 'true',
                'latency': '0',
                'profile': 'high',
                'level': '4.1'
            }
        elif self.encoder_name == 'h264_vaapi':
            # Linux VA-API
            self.codec_context.options = {
                'low_power': '1',
                'idr_interval': '1',
                'bframes': '0',
                'rc_mode': 'CBR'
            }
        else:
            # Software x264
            self.codec_context.options = {
                'preset': 'ultrafast',
                'tune': 'zerolatency',
                'x264-params': 'keyint=30:min-keyint=30:scenecut=0:bframes=0'
            }
    
    def start_encoding(self):
        """Start encoding loop"""
        self._setup_codec()
        self.running = True
        
        # Start encoding thread
        self.encode_thread = threading.Thread(target=self._encode_loop, daemon=True)
        self.encode_thread.start()
    
    def _encode_loop(self):
        """High-performance encoding loop"""
        while self.running:
            try:
                # Get frame from queue with timeout
                frame = self.frame_queue.get(timeout=0.001)
                if frame is None:
                    continue
                
                encode_start = time.perf_counter()
                
                # Convert numpy array to AV frame
                av_frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
                av_frame = av_frame.reformat(width=self.width, height=self.height)
                
                # Encode frame
                packets = self.codec_context.encode(av_frame)
                
                # Store encode time
                encode_time = time.perf_counter() - encode_start
                self.encode_times.append(encode_time)
                if len(self.encode_times) > 60:
                    self.encode_times.pop(0)
                self.average_encode_time = np.mean(self.encode_times)
                
                # Put packets in output queue
                for packet in packets:
                    if packet:
                        if not self.packet_queue.full():
                            self.packet_queue.put_nowait(packet)
                
                self.frame_count += 1
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Encoding error: {e}")
                time.sleep(0.001)
    
    def add_frame(self, frame: np.ndarray):
        """Add frame to encoding queue"""
        if self.running and not self.frame_queue.full():
            try:
                self.frame_queue.put_nowait(frame)
            except queue.Full:
                pass
    
    def get_packet(self) -> Optional[av.Packet]:
        """Get encoded packet from queue"""
        try:
            return self.packet_queue.get_nowait()
        except queue.Empty:
            return None
    
    def get_stats(self) -> dict:
        """Get encoding statistics"""
        return {
            'encoded_frames': self.frame_count,
            'average_encode_time_ms': self.average_encode_time * 1000,
            'encoder': self.encoder_name,
            'platform': self.platform,
            'input_queue_size': self.frame_queue.qsize(),
            'output_queue_size': self.packet_queue.qsize()
        }
    
    def stop_encoding(self):
        """Stop encoding and flush remaining frames"""
        self.running = False
        
        # Flush encoder
        if self.codec_context:
            try:
                packets = self.codec_context.encode(None)
                for packet in packets:
                    if packet:
                        self.packet_queue.put(packet)
            except:
                pass
            
            self.codec_context.close()