import json
import os
from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class StreamConfig:
    width: int = 1280
    height: int = 720
    fps: int = 60
    bitrate: str = "2M"
    encoder: str = "auto"
    low_latency: bool = True
    hardware_acceleration: bool = True
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StreamConfig':
        return cls(
            width=data.get('width', 1280),
            height=data.get('height', 720),
            fps=data.get('fps', 60),
            bitrate=data.get('bitrate', '2M'),
            encoder=data.get('encoder', 'auto'),
            low_latency=data.get('low_latency', True),
            hardware_acceleration=data.get('hardware_acceleration', True)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'width': self.width,
            'height': self.height,
            'fps': self.fps,
            'bitrate': self.bitrate,
            'encoder': self.encoder,
            'low_latency': self.low_latency,
            'hardware_acceleration': self.hardware_acceleration
        }

@dataclass
class NetworkConfig:
    video_port: int = 5555
    control_port: int = 5556
    discovery_port: int = 5557
    buffer_size: int = 65536
    mtu_size: int = 1400
    use_compression: bool = False
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NetworkConfig':
        return cls(
            video_port=data.get('video_port', 5555),
            control_port=data.get('control_port', 5556),
            discovery_port=data.get('discovery_port', 5557),
            buffer_size=data.get('buffer_size', 65536),
            mtu_size=data.get('mtu_size', 1400),
            use_compression=data.get('use_compression', False)
        )

class ConfigManager:
    def __init__(self, config_file: str = "edgelite_config.json"):
        self.config_file = config_file
        self.stream_config = StreamConfig()
        self.network_config = NetworkConfig()
        self.load_config()
    
    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    self.stream_config = StreamConfig.from_dict(data.get('stream', {}))
                    self.network_config = NetworkConfig.from_dict(data.get('network', {}))
            except Exception as e:
                print(f"Error loading config: {e}")
    
    def save_config(self):
        data = {
            'stream': self.stream_config.to_dict(),
            'network': self.network_config.to_dict()
        }
        try:
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
