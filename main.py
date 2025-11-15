#!/usr/bin/env python3
"""
EdgeLite Client - Cross-Platform Game Streaming Client
Supports Windows, macOS, and Linux
"""

import sys
import os
import platform

# Add shared directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

def check_dependencies():
    """Check for required dependencies and provide platform-specific guidance"""
    missing_deps = []
    
    try:
        import av
    except ImportError:
        missing_deps.append("PyAV (av)")
    
    try:
        import tkinter
    except ImportError:
        # tkinter is usually included with Python, but on some Linux distros it's separate
        if platform.system().lower() == "linux":
            missing_deps.append("tkinter (install: sudo apt-get install python3-tk)")
        else:
            missing_deps.append("tkinter")
    
    try:
        import PIL.Image
    except ImportError:
        missing_deps.append("Pillow (PIL)")
    
    if missing_deps:
        print("Missing dependencies:")
        for dep in missing_deps:
            print(f"  - {dep}")
        print("\nInstall with: pip install -r requirements.txt")
        return False
    
    return True

def main():
    """Main client application entry point"""
    print(f"EdgeLite Client - {platform.system()} {platform.release()}")
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    try:
        from config import ConfigManager
        from networking import NetworkDiscovery
        from receive import CrossPlatformVideoReceiver
        from input import CrossPlatformInputSender
        from gui import CrossPlatformClientGUI
        
        # Initialize components
        config_manager = ConfigManager()
        receiver = CrossPlatformVideoReceiver(config_manager)
        input_sender = CrossPlatformInputSender(config_manager.network_config.control_port)
        discovery = NetworkDiscovery(config_manager.network_config.discovery_port)
        
        # Create and run GUI
        app = CrossPlatformClientGUI(config_manager, receiver, input_sender, discovery)
        app.run()
        
    except Exception as e:
        print(f"Client error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()