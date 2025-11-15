import time
import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class PerformanceStats:
    fps: int = 0
    latency: float = 0
    bandwidth: float = 0
    frame_count: int = 0
    dropped_frames: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'fps': self.fps,
            'latency': self.latency,
            'bandwidth': self.bandwidth,
            'frame_count': self.frame_count,
            'dropped_frames': self.dropped_frames
        }
    
    def update(self, new_stats: Dict[str, Any]):
        for key, value in new_stats.items():
            if hasattr(self, key):
                setattr(self, key, value)

class FPSCounter:
    def __init__(self, window_size: int = 60):
        self.window_size = window_size
        self.frame_times = []
        self.last_time = time.time()
    
    def update(self):
        current_time = time.time()
        self.frame_times.append(current_time)
        
        # Remove old frame times
        while self.frame_times and current_time - self.frame_times[0] > 1.0:
            self.frame_times.pop(0)
        
        self.last_time = current_time
        return len(self.frame_times)
    
    def get_fps(self) -> int:
        return len(self.frame_times)

def get_system_info() -> Dict[str, str]:
    """Get system information for performance tuning"""
    import psutil
    
    system_info = {
        'platform': platform.system(),
        'platform_version': platform.version(),
        'architecture': platform.architecture()[0],
        'python_version': platform.python_version(),
    }
    
    try:
        system_info.update({
            'processor': platform.processor(),
            'memory_gb': round(psutil.virtual_memory().total / (1024**3), 1),
            'cpu_cores': psutil.cpu_count(),
        })
        
        # Platform-specific info
        if platform.system().lower() == "darwin":
            # macOS specific info
            try:
                result = subprocess.run(['sw_vers', '-productVersion'], 
                                      capture_output=True, text=True, check=True)
                system_info['macos_version'] = result.stdout.strip()
            except:
                pass
                
        elif platform.system().lower() == "linux":
            # Linux specific info
            try:
                result = subprocess.run(['lsb_release', '-d'], 
                                      capture_output=True, text=True, check=True)
                system_info['linux_distro'] = result.stdout.split(':')[1].strip()
            except:
                pass
    
    except Exception:
        pass
    
    return system_info

def optimize_system_settings():
    """Optimize system settings for low-latency streaming"""
    system = platform.system().lower()
    
    if system == "darwin":
        # macOS optimizations
        try:
            # Increase process priority
            import os
            os.nice(-10)
        except:
            pass
    
    elif system == "linux":
        # Linux optimizations
        try:
            # Set high process priority
            import os
            os.nice(-10)
            
            # Set real-time scheduling if possible
            try:
                import psutil
                psutil.Process().nice(-20)
            except:
                pass
        except:
            pass
    
    elif system == "windows":
        # Windows optimizations
        try:
            import ctypes
            # Increase timer resolution
            ctypes.windll.winmm.timeBeginPeriod(1)
        except:
            pass
    
    # Set environment variables for better performance
    os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'fflags|nobuffer;flags|low_delay'
    
    # Platform-specific environment variables
    if system == "linux":
        os.environ['DISPLAY'] = ':0'  # Ensure display is set on Linux

def get_platform_requirements():
    """Get platform-specific requirements and instructions"""
    system = platform.system().lower()
    
    requirements = {
        'windows': {
            'dependencies': ['av', 'opencv-python', 'Pillow', 'pynput'],
            'notes': 'No special requirements'
        },
        'darwin': {
            'dependencies': ['av', 'opencv-python', 'Pillow', 'pynput'],
            'notes': 'Enable accessibility permissions for input forwarding in System Preferences'
        },
        'linux': {
            'dependencies': ['av', 'opencv-python', 'Pillow', 'pynput', 'python3-tk'],
            'notes': 'Install python3-tk package: sudo apt-get install python3-tk'
        }
    }
    
    return requirements.get(system, requirements['linux'])