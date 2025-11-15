import time
import psutil
import threading
from typing import Dict, Any
import platform

class PerformanceMonitor:
    def __init__(self):
        self.running = False
        self.stats = {}
        self.thread = None
        self.platform = platform.system().lower()
        
    def start_monitoring(self):
        """Start performance monitoring"""
        self.running = True
        self.thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.thread.start()
    
    def _monitoring_loop(self):
        """Performance monitoring loop"""
        while self.running:
            try:
                # System-wide stats
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory = psutil.virtual_memory()
                disk_io = psutil.disk_io_counters()
                net_io = psutil.net_io_counters()
                
                # Process-specific stats
                process = psutil.Process()
                process_memory = process.memory_info()
                process_cpu = process.cpu_percent()
                process_threads = process.num_threads()
                
                self.stats = {
                    'timestamp': time.time(),
                    'system': {
                        'cpu_percent': cpu_percent,
                        'memory_percent': memory.percent,
                        'memory_used_gb': memory.used / (1024**3),
                        'disk_read_mb': disk_io.read_bytes / (1024**2) if disk_io else 0,
                        'disk_write_mb': disk_io.write_bytes / (1024**2) if disk_io else 0,
                        'net_sent_mb': net_io.bytes_sent / (1024**2) if net_io else 0,
                        'net_recv_mb': net_io.bytes_recv / (1024**2) if net_io else 0,
                    },
                    'process': {
                        'cpu_percent': process_cpu,
                        'memory_mb': process_memory.rss / (1024**2),
                        'thread_count': process_threads,
                    },
                    'platform': self.platform
                }
                
                time.sleep(1.0)  # Update every second
                
            except Exception as e:
                print(f"Performance monitoring error: {e}")
                time.sleep(5.0)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current performance statistics"""
        return self.stats
    
    def stop_monitoring(self):
        """Stop performance monitoring"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)