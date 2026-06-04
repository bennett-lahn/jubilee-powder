"""
Configuration loader for Jubilee automation system.
Loads system-wide configuration parameters from JSON files.
"""

import json
from pathlib import Path

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

    # --- Trickler / powder dispensing ---

    def get_trickler(self, key: str, default=None):
        """Get a trickler configuration value by key name."""
        return self.get(f"trickler.{key}", default)

    def get_trickler_flow_ema_alpha(self) -> float:
        return self.get_trickler("flow_ema_alpha", 0.3)

    def get_trickler_yield_ema_alpha(self) -> float:
        return self.get_trickler("yield_ema_alpha", 0.2)

    def get_trickler_jam_yield_threshold(self) -> float:
        return self.get_trickler("jam_yield_threshold", 0.001)

    def get_trickler_jam_iter_threshold(self) -> int:
        return int(self.get_trickler("jam_iter_threshold", 40))

    def get_trickler_max_step_size_mm(self) -> float:
        return self.get_trickler("max_step_size_mm", 4.0)

    def get_trickler_min_step_size_mm(self) -> float:
        return self.get_trickler("min_step_size_mm", 0.2)

    def get_trickler_warmup_steps(self) -> int:
        return int(self.get_trickler("warmup_steps", 3))

    def get_trickler_warmup_max_step_mm(self) -> float:
        return self.get_trickler("warmup_max_step_mm", 0.5)

    def get_trickler_coarse_threshold_pct(self) -> float:
        return self.get_trickler("coarse_threshold_pct", 0.9)

    def get_trickler_finish_threshold_pct(self) -> float:
        return self.get_trickler("finish_threshold_pct", 0.99)

    def get_trickler_coarse_target_steps(self) -> int:
        return int(self.get_trickler("coarse_target_steps", 8))

    def get_trickler_coarse_feedrate(self) -> int:
        return int(self.get_trickler("coarse_feedrate", 200))

    def get_trickler_fine_feedrate(self) -> int:
        return int(self.get_trickler("fine_feedrate", 300))

    def get_trickler_coarse_vibration_amplitude(self) -> float:
        return self.get_trickler("coarse_vibration_amplitude", 0.5)

    def get_trickler_fine_vibration_amplitude(self) -> float:
        return self.get_trickler("fine_vibration_amplitude", 0.2)

    def get_trickler_max_dribble_step_mm(self) -> float:
        return self.get_trickler("max_dribble_step_mm", 0.5)

# Global config instance
config = ConfigLoader()
