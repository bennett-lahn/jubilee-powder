"""
Configuration loader for Jubilee automation system.
Loads system-wide configuration parameters from JSON files.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any

class ConfigLoader:
    """Loads and manages system configuration"""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            self._load_config()
    
    def _load_config(self):
        """Load configuration from JSON file"""
        # Get project root (parent of src directory)
        project_root = Path(__file__).parent.parent
        config_path = project_root / "jubilee_api_config" / "system_config.json"
        with open(config_path, "r") as f:
            self._config = json.load(f)

    
    def get(self, key_path: str, default=None):
        """Get configuration value using dot notation (e.g., 'safety.safe_z')"""
        keys = key_path.split('.')
        value = self._config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_safe_z(self) -> float:
        """Get safe Z height"""
        return self.get("safety.safe_z", 195)
    
    def get_safe_z_offset(self) -> float:
        """Get safe Z offset"""
        return self.get("safety.safe_z_offset", 20)
    
    def get_max_weight_per_well(self) -> float:
        """Get maximum weight per well"""
        return self.get("safety.max_weight_per_well", 10.0)
    
    def get_weight_tolerance(self) -> float:
        """Get weight tolerance"""
        return self.get("safety.weight_tolerance", 0.001)
    
    def get_duet_ip(self) -> str:
        """Get DUET IP address"""
        return self.get("machine.duet_ip", "192.168.1.2")

# Global config instance
config = ConfigLoader()
