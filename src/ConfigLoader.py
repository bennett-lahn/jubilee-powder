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
        return self.get("safety.safe_z", None)
    
    def get_safe_z_offset(self) -> float:
        """Get safe Z offset"""
        return self.get("safety.safe_z_offset", None)
    
    def get_max_weight_per_well(self) -> float:
        """Get maximum weight per well"""
        return self.get("safety.max_weight_per_well", 1.0)
    
    def get_weight_tolerance(self) -> float:
        """Get weight tolerance"""
        return self.get("safety.weight_tolerance", 0.001)
    
    def get_duet_ip(self) -> str:
        """Get DUET IP address"""
        return self.get("machine.duet_ip", "192.168.1.2")
    
    def get_tamp_depth_min(self) -> float:
        """Get minimum tamp depth in mm"""
        return self.get("manipulator.tamp_depth_min", None)
    
    def get_tamp_depth_max(self) -> float:
        """Get maximum tamp depth in mm"""
        return self.get("manipulator.tamp_depth_max", None)
    
    def get_tamp_speed_min(self) -> int:
        """Get minimum tamp speed in mm/min"""
        return self.get("manipulator.tamp_speed_min", None)
    
    def get_tamp_speed_max(self) -> int:
        """Get maximum tamp speed in mm/min"""
        return self.get("manipulator.tamp_speed_max", None)

    def get_tool_offsets(self) -> Dict[str, Dict[str, float]]:
        """
        Get the tool-offset table from system config.

        Returns a dict mapping offset_id (e.g. "manipulator", "durometer",
        "durometer_z_probe") to a dict with float x/y/z components. The
        'description' key, if present in the config, is filtered out so
        callers can iterate offsets safely.
        """
        offsets = self.get("tool_offsets", {}) or {}
        result: Dict[str, Dict[str, float]] = {}
        for offset_id, value in offsets.items():
            if offset_id == "description":
                continue
            if not isinstance(value, dict):
                continue
            result[offset_id] = {
                "x": float(value.get("x")),
                "y": float(value.get("y")),
                "z": float(value.get("z")),
            }
        return result

    def get_default_offset_for_tool(self, tool_name: str) -> str:
        """
        Get the default tool-offset id associated with a given tool name.

        Falls back to "manipulator" (zero offset) when the tool does not
        explicitly declare a default_offset, so the system always has a
        well-defined offset to assume.
        """
        tools_cfg = self.get("tools", {}) or {}
        for tool_cfg in tools_cfg.values():
            if not isinstance(tool_cfg, dict):
                continue
            if tool_cfg.get("name") == tool_name:
                offset_id = tool_cfg.get("default_offset")
                if isinstance(offset_id, str) and offset_id:
                    return offset_id
                break
        return "manipulator"

# Global config instance
config = ConfigLoader()
