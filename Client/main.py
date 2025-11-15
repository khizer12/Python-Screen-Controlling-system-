import socket
import threading
import json
import time
from typing import Callable, Optional

class DiscoveryProtocol:
    @staticmethod
    def create_broadcast_message(host_name: str, host_ip: str, port: int) -> bytes:
        message = {
            'type': 'discovery',
            'host_name': host_name,
            'host_ip': host_ip,
            'port': port,
            'timestamp': time.time()
        }
        return json.dumps(message).encode()
    
    @staticmethod
    def parse_broadcast_message(data: bytes) -> Optional[dict]:
        try:
            message = json.loads(data.decode())
            if message.get('type') == 'discovery':
                return message
        except:
            pass
        return None

class NetworkDiscovery:
    def __init__(self, port: int = 5557):
        self.port = port
        self.running = False
        self.socket = None
        self.on_host_discovered = None
    
    def start_discovery(self, on_host_discovered: Callable):
        self.on_host_discovered = on_host_discovered
        self.running = True
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.socket.bind(('', self.port))
        except:
            self.socket.bind(('', 0))
            self.port = self.socket.getsockname()[1]
        
        thread = threading.Thread(target=self._discovery_loop, daemon=True)
        thread.start()
    
    def _discovery_loop(self):
        while self.running:
            try:
                data, addr = self.socket.recvfrom(1024)
                message = DiscoveryProtocol.parse_broadcast_message(data)
                if message and self.on_host_discovered:
                    self.on_host_discovered(message, addr[0])
            except Exception as e:
                if self.running:
                    print(f"Discovery error: {e}")
    
    def stop_discovery(self):
        self.running = False
        if self.socket:
            self.socket.close()
    
    def broadcast_host(self, host_name: str, host_ip: str, port: int, interval: float = 2.0):
        self.running = True
        broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        def broadcast_loop():
            while self.running:
                try:
                    message = DiscoveryProtocol.create_broadcast_message(host_name, host_ip, port)
                    broadcast_socket.sendto(message, ('<broadcast>', self.port))
                    time.sleep(interval)
                except Exception as e:
                    if self.running:
                        print(f"Broadcast error: {e}")
        
        thread = threading.Thread(target=broadcast_loop, daemon=True)
        thread.start()
