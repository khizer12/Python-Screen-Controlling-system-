import mss
import numpy as np
import threading
import time
import queue
from typing import Optional, Tuple, Callable
import platform
import psutil
import os

class CrossPlatformCapture:
    def __init__(self, target_fps: int = 60, capture_region: Optional[Tuple[int, int, int, int]] = None):
        self.target_fps = target_fps
        self.capture_region = capture_region
        self.running = False
        self.frame_queue = queue.Queue(maxsize=2)
        self.thread = None
        self.frame_count = 0
        self.last_capture_time = 0
        self.average_capture_time = 0
        self.capture_times = []
        self.platform = platform.system().lower()
        
        # Platform-specific optimizations
        self._setup_platform_optimizations()
    
    def _setup_platform_optimizations(self):
        """Platform-specific performance optimizations"""
        try:
            if self.platform == "windows":
                self._setup_windows_optimizations()
            elif self.platform == "darwin":
                self._setup_macos_optimizations()
            elif self.platform == "linux":
                self._setup_linux_optimizations()
                
            print(f"Platform optimizations applied for {self.platform}")
        except Exception as e:
            print(f"Platform optimizations failed: {e}")
    
    def _setup_windows_optimizations(self):
        """Windows-specific optimizations"""
        try:
            import win32api
            import win32con
            import win32process
            
            # Increase thread priority
            handle = win32api.GetCurrentThread()
            win32api.SetThreadPriority(handle, win32con.THREAD_PRIORITY_TIME_CRITICAL)
            
            # High-performance power plan
            import subprocess
            subprocess.run([
                'powercfg', '/setactive', '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c'
            ], capture=True, timeout=1, check=False)
            
        except Exception as e:
            print(f"Windows optimizations partial failure: {e}")
    
    def _setup_macos_optimizations(self):
        """macOS-specific optimizations"""
        try:
            # Increase process priority on macOS
            import os
            os.nice(-10)
            
            # Disable App Nap for this process
            import subprocess
            subprocess.run([
                'defaults', 'write', 'NSGlobalDomain', 'NSAppSleepDisabled', '-bool', 'YES'
            ], capture=True, check=False)
            
        except Exception as e:
            print(f"macOS optimizations partial failure: {e}")
    
    def _setup_linux_optimizations(self):
        """Linux-specific optimizations"""
        try:
            # Increase process priority
            import os
            os.nice(-10)
            
            # Set real-time scheduling if possible
            try:
                import psutil
                psutil.Process().nice(-20)
            except:
                pass
            
            # Optimize for low latency
            os.environ['DISPLAY'] = ':0'
            
        except Exception as e:
            print(f"Linux optimizations partial failure: {e}")
    
    def find_game_window(self, window_name: str = None) -> Optional[Tuple[int, int, int, int]]:
        """Find and return game window coordinates (cross-platform)"""
        if self.platform == "windows":
            return self._find_windows_window(window_name)
        elif self.platform == "darwin":
            return self._find_macos_window(window_name)
        elif self.platform == "linux":
            return self._find_linux_window(window_name)
        return None
    
    def _find_windows_window(self, window_name: str = None):
        """Find window on Windows"""
        try:
            import win32gui
            import win32process
            
            def callback(hwnd, extra):
                if win32gui.IsWindowVisible(hwnd):
                    window_text = win32gui.GetWindowText(hwnd)
                    if window_name and window_name.lower() in window_text.lower():
                        rect = win32gui.GetWindowRect(hwnd)
                        extra.append(rect)
                return True
            
            windows = []
            win32gui.EnumWindows(callback, windows)
            
            if windows:
                left, top, right, bottom = windows[0]
                return (left, top, right - left, bottom - top)
        except Exception as e:
            print(f"Windows window finding failed: {e}")
        return None
    
    def _find_macos_window(self, window_name: str = None):
        """Find window on macOS"""
        try:
            import subprocess
            
            # Use AppleScript to find window (basic implementation)
            script = f'''
            tell application "System Events"
                set windowList to every window of every process whose visible is true
                repeat with aWindow in windowList
                    if name of aWindow contains "{window_name}" then
                        return (position of aWindow) & (size of aWindow)
                    end if
                end repeat
            end tell
            '''
            
            result = subprocess.run(['osascript', '-e', script], 
                                  capture_output=True, text=True, check=False)
            if result.returncode == 0:
                coords = result.stdout.strip().split(', ')
                if len(coords) == 4:
                    x, y, width, height = map(int, coords)
                    return (x, y, width, height)
        except Exception as e:
            print(f"macOS window finding failed: {e}")
        return None
    
    def _find_linux_window(self, window_name: str = None):
        """Find window on Linux using xdotool"""
        try:
            import subprocess
            
            # Try to find window ID using xdotool
            result = subprocess.run([
                'xdotool', 'search', '--name', window_name
            ], capture_output=True, text=True, check=False)
            
            if result.returncode == 0 and result.stdout.strip():
                window_id = result.stdout.strip().split('\n')[0]
                
                # Get window geometry
                geometry = subprocess.run([
                    'xdotool', 'getwindowgeometry', window_id
                ], capture_output=True, text=True, check=False)
                
                if geometry.returncode == 0:
                    # Parse geometry output (this is simplified)
                    lines = geometry.stdout.strip().split('\n')
                    for line in lines:
                        if 'Position:' in line:
                            pos = line.split('Position:')[1].strip().split(',')
                            x, y = int(pos[0]), int(pos[1])
                        elif 'Geometry:' in line:
                            geom = line.split('Geometry:')[1].strip().split('x')
                            width, height = int(geom[0]), int(geom[1])
                    
                    return (x, y, width, height)
                    
        except Exception as e:
            print(f"Linux window finding failed: {e}")
        return None
    
    def start_capture(self, on_frame_callback: Callable = None):
        """Start high-performance capture loop"""
        self.running = True
        
        if self.capture_region is None:
            # Capture primary monitor
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                self.capture_region = {
                    'left': monitor['left'],
                    'top': monitor['top'],
                    'width': monitor['width'],
                    'height': monitor['height']
                }
        
        self.thread = threading.Thread(target=self._capture_loop, args=(on_frame_callback,), daemon=True)
        self.thread.start()
    
    def _capture_loop(self, on_frame_callback: Callable = None):
        """High-performance capture loop with timing control"""
        with mss.mss() as sct:
            target_frame_time = 1.0 / self.target_fps
            
            while self.running:
                frame_start = time.perf_counter()
                
                try:
                    # Capture screen
                    screenshot = sct.grab(self.capture_region)
                    
                    # Convert to numpy array efficiently
                    frame = np.array(screenshot)
                    
                    # Update statistics
                    self.frame_count += 1
                    capture_time = time.perf_counter() - frame_start
                    
                    # Maintain performance statistics
                    self.capture_times.append(capture_time)
                    if len(self.capture_times) > 60:
                        self.capture_times.pop(0)
                    self.average_capture_time = np.mean(self.capture_times)
                    
                    # Call callback if provided
                    if on_frame_callback:
                        on_frame_callback(frame)
                    
                    # Add to queue (non-blocking)
                    if not self.frame_queue.full():
                        try:
                            self.frame_queue.put_nowait(frame)
                        except queue.Full:
                            pass
                    
                    # Precise timing control
                    elapsed = time.perf_counter() - frame_start
                    sleep_time = target_frame_time - elapsed
                    
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    else:
                        # We're behind schedule
                        if sleep_time < -target_frame_time * 0.5:
                            print(f"Capture behind schedule: {-sleep_time*1000:.1f}ms")
                
                except Exception as e:
                    print(f"Capture error: {e}")
                    time.sleep(0.001)
    
    def get_frame(self) -> Optional[np.ndarray]:
        """Get latest frame from queue"""
        try:
            while not self.frame_queue.empty():
                frame = self.frame_queue.get_nowait()
            return frame
        except queue.Empty:
            return None
    
    def get_stats(self) -> dict:
        """Get capture performance statistics"""
        return {
            'frame_count': self.frame_count,
            'average_capture_time_ms': self.average_capture_time * 1000,
            'current_fps': self.target_fps,
            'queue_size': self.frame_queue.qsize(),
            'platform': self.platform
        }
    
    def stop_capture(self):
        """Stop capture loop"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)