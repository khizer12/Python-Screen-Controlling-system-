import socket
import threading
import queue
import time
import numpy as np
from typing import Optional, Tuple
import pickle
import struct
import platform

class EnhancedStreamer:
    def __init__(self, host: str = "0.0.0.0", video_port: int = 5555, control_port: int = 5556):
        self.host = host
        self.video_port = video_port
        self.control_port = control_port
        self.running = False
        self.platform = platform.system().lower()
        
        # Network sockets
        self.video_socket = None
        self.control_socket = None
        self.client_address = None
        
        # Performance tracking
        self.sent_packets = 0
        self.sent_bytes = 0
        self.start_time = time.time()
        self.packet_times = []
        
        # Packet queue
        self.packet_queue = queue.Queue(maxsize=20)
        
        # MTU optimization
        self.mtu_size = 1400
        
        # Platform-specific buffer sizes
        self._setup_platform_networking()
    
    def _setup_platform_networking(self):
        """Platform-specific network optimizations"""
        if self.platform == "linux":
            self.mtu_size = 1500  # Standard Ethernet MTU
        elif self.platform == "darwin":
            self.mtu_size = 1500
        else:  # Windows
            self.mtu_size = 1400  # Conservative for Windows
    
    def start_streaming(self, client_ip: str):
        """Start streaming to client"""
        try:
            self.client_address = (client_ip, self.video_port)
            
            # Create UDP socket with platform-optimized buffer sizes
            self.video_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            # Platform-specific buffer optimizations
            if self.platform == "linux":
                self.video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)  # 1MB buffer
            else:
                self.video_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536 * 4)    # 256KB buffer
            
            # Set non-blocking
            self.video_socket.setblocking(False)
            
            # Start control server
            self._start_control_server()
            
            # Start streaming thread
            self.running = True
            self.stream_thread = threading.Thread(target=self._streaming_loop, daemon=True)
            self.stream_thread.start()
            
            return True
            
        except Exception as e:
            print(f"Stream start error: {e}")
            return False
    
    def _start_control_server(self):
        """Start control command server"""
        self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.control_socket.bind((self.host, self.control_port))
        self.control_socket.settimeout(0.1)  # Non-blocking with timeout
        
        self.control_thread = threading.Thread(target=self._control_loop, daemon=True)
        self.control_thread.start()
    
    def _control_loop(self):
        """Handle control commands"""
        while self.running:
            try:
                data, addr = self.control_socket.recvfrom(1024)
                self._handle_control_command(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Control error: {e}")
                time.sleep(0.001)
    
    def _handle_control_command(self, data: bytes, addr: Tuple[str, int]):
        """Handle incoming control commands"""
        try:
            command = data.decode('utf-8').strip()
            if command == "STATS":
                stats = self.get_stats()
                response = str(stats).encode('utf-8')
                self.control_socket.sendto(response, addr)
            elif command.startswith("QUALITY:"):
                # Client requesting quality change
                self._handle_quality_change(command, addr)
        except:
            pass
    
    def _handle_quality_change(self, command: str, addr: Tuple[str, int]):
        """Handle client-requested quality changes"""
        try:
            # Parse quality command (e.g., "QUALITY:720p60")
            quality = command.split(':')[1]
            # In a real implementation, you'd adjust encoder settings here
            print(f"Client requested quality change to: {quality}")
            
            # Acknowledge the change
            response = f"QUALITY_ACK:{quality}".encode('utf-8')
            self.control_socket.sendto(response, addr)
        except Exception as e:
            print(f"Quality change error: {e}")
    
    def _streaming_loop(self):
        """High-performance streaming loop"""
        while self.running:
            try:
                # Get packet from queue
                packet = self.packet_queue.get(timeout=0.001)
                if packet is None:
                    continue
                
                send_start = time.perf_counter()
                
                # Convert packet to bytes if it's an AV packet
                if hasattr(packet, 'to_bytes'):
                    packet_data = packet.to_bytes()
                else:
                    packet_data = packet
                
                # Track packet timing
                self.packet_times.append(send_start)
                if len(self.packet_times) > 1000:
                    self.packet_times.pop(0)
                
                # Split large packets to avoid fragmentation
                if len(packet_data) > self.mtu_size:
                    self._send_fragmented(packet_data)
                else:
                    self._send_packet(packet_data)
                
                # Update statistics
                self.sent_packets += 1
                self.sent_bytes += len(packet_data)
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Streaming error: {e}")
                time.sleep(0.001)
    
    def _send_packet(self, data: bytes):
        """Send single packet"""
        if self.client_address and self.video_socket:
            try:
                self.video_socket.sendto(data, self.client_address)
            except BlockingIOError:
                # Socket buffer full, drop packet for low latency
                pass
            except Exception as e:
                print(f"Send error: {e}")
    
    def _send_fragmented(self, data: bytes):
        """Send large packet as fragments"""
        total_size = len(data)
        num_fragments = (total_size + self.mtu_size - 1) // self.mtu_size
        
        for i in range(num_fragments):
            start = i * self.mtu_size
            end = min(start + self.mtu_size, total_size)
            fragment = data[start:end]
            
            # Add fragment header
            header = struct.pack('!HHH', 0, i, num_fragments)
            self._send_packet(header + fragment)
    
    def send_packet(self, packet):
        """Add packet to send queue"""
        if self.running and not self.packet_queue.full():
            try:
                self.packet_queue.put_nowait(packet)
            except queue.Full:
                pass
    
    def get_stats(self) -> dict:
        """Get streaming statistics"""
        elapsed = time.time() - self.start_time
        current_time = time.time()
        
        # Calculate recent packet rate
        recent_packets = [t for t in self.packet_times if current_time - t <= 1.0]
        recent_packet_rate = len(recent_packets)
        
        return {
            'sent_packets': self.sent_packets,
            'sent_bytes': self.sent_bytes,
            'average_bandwidth_mbps': (self.sent_bytes * 8) / (elapsed * 1e6) if elapsed > 0 else 0,
            'recent_packet_rate': recent_packet_rate,
            'queue_size': self.packet_queue.qsize(),
            'client_address': self.client_address,
            'platform': self.platform
        }
    
    def stop_streaming(self):
        """Stop streaming"""
        self.running = False
        if self.video_socket:
            self.video_socket.close()
        if self.control_socket:
            self.control_socket.close()