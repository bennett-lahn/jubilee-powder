# ConfigLoader API Reference

The `ConfigLoader` module provides centralized access to system configuration from JSON files.

## Overview

ConfigLoader:

- Loads configuration from JSON files
- Provides type-safe access to configuration values
- Handles default values
- Validates configuration data

## Module Reference

::: src.ConfigLoader
    options:
      members: true
      show_root_heading: true
      show_source: false

## Usage Examples

### Basic Configuration Access

```python
from src.ConfigLoader import config

# Get Duet IP address
ip = config.get_duet_ip()
print(f"Jubilee IP: {ip}")

# Get scale port
port = config.get_scale_port()
print(f"Scale port: {port}")

# Get system configuration
sys_config = config.get_system_config()
print(f"System config: {sys_config}")
```

### Loading Custom Configurations

```python
from src.ConfigLoader import ConfigLoader

# Create loader for custom config file
loader = ConfigLoader(config_file="custom_config.json")

# Access configuration
custom_data = loader.get_system_config()
```

## Configuration Files

### system_config.json

Main system configuration file:

```json
{
  "system": {
    "duet_ip": "192.168.1.100",
    "scale_port": "/dev/ttyUSB0",
    "scale_baud_rate": 9600,
    "default_feedrate": "MEDIUM"
  },
  "tools": {
    "manipulator": {
      "index": 0,
      "park_position": {"x": 0, "y": 0, "z": 100},
      "v_axis_offset": 50.0,
      "gripper_config": {
        "open_position": 5.0,
        "close_position": 0.0,
        "grip_force": 10.0
      }
    }
  },
  "safety": {
    "max_speed": 10000,
    "acceleration": 500,
    "work_envelope": {
      "x_min": 0, "x_max": 300,
      "y_min": 0, "y_max": 300,
      "z_min": 0, "z_max": 300
    }
  }
}
```

### motion_platform_positions.json

State machine positions and transitions:

```json
{
  "positions": {
    "global_ready": {
      "coordinates": {"x": 150, "y": 150, "z": 100, "safe_z": 150},
      "description": "Safe global position",
      "requires_tool": null,
      "allowed_payloads": ["empty", "mold", "mold_with_piston"]
    }
  },
  "transitions": {
    "global_ready": {
      "to": ["scale_ready", "mold_slot_A1"]
    }
  }
}
```

### mold_labware.json

Deck layout and labware definitions:

```json
{
  "deck": {
    "name": "Main Deck",
    "dimensions": {"width": 300, "height": 300},
    "labware": {
      "well_plate_1": {
        "type": "well_plate",
        "name": "24-Well Plate",
        "rows": 4,
        "columns": 6,
        "origin": {"x": 50, "y": 50, "z": 10},
        "wells": {
          "A1": {
            "position": {"x": 50, "y": 50, "z": 10},
            "ready_pos": "mold_slot_A1",
            "capacity_ml": 10.0
          }
        }
      }
    }
  }
}
```

## Accessing Configuration Values

### System Settings

```python
from src.ConfigLoader import config

# Network settings
duet_ip = config.get_duet_ip()
duet_port = config.get_value("system.duet_port", default=80)

# Scale settings
scale_port = config.get_scale_port()
scale_baud = config.get_value("system.scale_baud_rate", default=9600)

# Feed rate
feedrate = config.get_value("system.default_feedrate", default="MEDIUM")
```

### Tool Configuration

```python
# Get manipulator configuration
manipulator_config = config.get_value("tools.manipulator")

if manipulator_config:
    index = manipulator_config["index"]
    park_pos = manipulator_config["park_position"]
    gripper = manipulator_config["gripper_config"]
    
    print(f"Manipulator index: {index}")
    print(f"Park position: {park_pos}")
    print(f"Gripper open: {gripper['open_position']}mm")
```

### Safety Parameters

```python
# Get safety limits
safety = config.get_value("safety")

if safety:
    max_speed = safety["max_speed"]
    envelope = safety["work_envelope"]
    
    print(f"Max speed: {max_speed} mm/min")
    print(f"Work envelope: X={envelope['x_min']}-{envelope['x_max']}mm")
```

### Nested Values

```python
# Access deeply nested values using dot notation
gripper_open = config.get_value(
    "tools.manipulator.gripper_config.open_position",
    default=5.0
)

# Or access step by step
tools = config.get_value("tools")
manipulator = tools.get("manipulator", {})
gripper_config = manipulator.get("gripper_config", {})
gripper_open = gripper_config.get("open_position", 5.0)
```

## Default Values

### Providing Defaults

Always provide sensible defaults:

```python
# GOOD - with default
value = config.get_value("optional.setting", default=100)

# RISKY - no default (might be None)
value = config.get_value("optional.setting")
if value is None:
    value = 100
```

### Common Defaults

```python
# Network
duet_ip = config.get_duet_ip() or "192.168.1.100"
duet_port = config.get_value("system.duet_port", default=80)

# Serial
scale_port = config.get_scale_port() or "/dev/ttyUSB0"
scale_baud = config.get_value("system.scale_baud_rate", default=9600)

# Performance
feedrate = config.get_value("system.default_feedrate", default="MEDIUM")
max_speed = config.get_value("safety.max_speed", default=10000)
```

## Configuration Validation

### Validating Required Fields

```python
def validate_system_config(config):
    """Validate that required configuration fields exist."""
    required_fields = [
        "system.duet_ip",
        "system.scale_port",
        "tools.manipulator.index"
    ]
    
    missing = []
    for field in required_fields:
        if config.get_value(field) is None:
            missing.append(field)
    
    if missing:
        raise ValueError(f"Missing required config fields: {missing}")
    
    print("✅ Configuration validation passed")

# Usage
try:
    validate_system_config(config)
except ValueError as e:
    print(f"❌ Configuration error: {e}")
```

### Validating Value Ranges

```python
def validate_safety_limits(config):
    """Validate safety parameters are within acceptable ranges."""
    safety = config.get_value("safety", default={})
    
    max_speed = safety.get("max_speed", 10000)
    if max_speed > 20000:
        print(f"⚠️  Warning: max_speed ({max_speed}) exceeds recommended limit")
    
    envelope = safety.get("work_envelope", {})
    for axis in ["x", "y", "z"]:
        min_val = envelope.get(f"{axis}_min", 0)
        max_val = envelope.get(f"{axis}_max", 300)
        
        if min_val >= max_val:
            raise ValueError(f"Invalid work envelope: {axis}_min >= {axis}_max")
    
    print("✅ Safety limits validation passed")
```

## Configuration Modification

### Runtime Modification

```python
# Modify configuration at runtime (not persistent)
config._config["system"]["duet_ip"] = "192.168.1.200"

# Verify change
new_ip = config.get_duet_ip()
print(f"New IP: {new_ip}")
```

!!! warning "Not Persistent"
    Runtime modifications are **not saved** to the configuration file. They only affect the current program execution.

### Saving Configuration

To make persistent changes, edit the JSON files directly:

```python
import json
from pathlib import Path

def update_duet_ip(new_ip):
    """Update Duet IP in configuration file."""
    config_file = Path("jubilee_api_config/system_config.json")
    
    # Read current config
    with open(config_file, 'r') as f:
        config_data = json.load(f)
    
    # Update value
    config_data["system"]["duet_ip"] = new_ip
    
    # Write back
    with open(config_file, 'w') as f:
        json.dump(config_data, f, indent=2)
    
    print(f"Updated Duet IP to {new_ip}")

# Usage
update_duet_ip("192.168.1.200")
```

## Environment-Specific Configuration

### Multiple Environments

Manage different configurations for different environments:

```python
import os
from src.ConfigLoader import ConfigLoader

# Determine environment
env = os.getenv("JUBILEE_ENV", "production")

# Load environment-specific config
if env == "development":
    config = ConfigLoader(config_file="config/dev_system_config.json")
elif env == "testing":
    config = ConfigLoader(config_file="config/test_system_config.json")
else:
    config = ConfigLoader(config_file="jubilee_api_config/system_config.json")

print(f"Loaded {env} configuration")
```

### Configuration Profiles

```python
CONFIGS = {
    "lab1": {
        "duet_ip": "192.168.1.100",
        "scale_port": "/dev/ttyUSB0"
    },
    "lab2": {
        "duet_ip": "192.168.1.200",
        "scale_port": "/dev/ttyUSB1"
    }
}

def load_profile(profile_name):
    """Load a specific configuration profile."""
    profile = CONFIGS.get(profile_name)
    if not profile:
        raise ValueError(f"Unknown profile: {profile_name}")
    
    # Apply profile settings
    # (This would need to be integrated with ConfigLoader)
    return profile

# Usage
profile = load_profile("lab1")
```

## Best Practices

### Use Centralized Config

```python
# GOOD - use centralized config
from src.ConfigLoader import config

ip = config.get_duet_ip()

# BAD - hardcoded values
ip = "192.168.1.100"
```

### Provide Defaults

```python
# GOOD - safe with default
timeout = config.get_value("system.timeout", default=30)

# BAD - might crash if not set
timeout = config.get_value("system.timeout")
```

### Validate on Startup

```python
def main():
    # Validate configuration before using it
    try:
        validate_system_config(config)
        validate_safety_limits(config)
    except ValueError as e:
        print(f"Configuration error: {e}")
        return
    
    # Continue with validated configuration
    # ...
```

### Document Configuration

Keep documentation of configuration fields:

```python
"""
Configuration Fields:

system.duet_ip: str
    IP address of Jubilee Duet controller
    Default: "192.168.1.100"

system.scale_port: str
    Serial port for scale connection
    Default: "/dev/ttyUSB0"
    
system.default_feedrate: str
    Default movement speed (SLOW, MEDIUM, FAST)
    Default: "MEDIUM"
"""
```

## See Also

- [Configuration Guide](../how-to/configuration.md) - Detailed configuration walkthrough
- [JubileeManager](jubilee-manager.md) - Uses ConfigLoader for initialization
- [System Architecture](../concepts/architecture.md) - Role of configuration in system

