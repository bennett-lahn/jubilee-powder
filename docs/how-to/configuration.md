# Configuration Guide

This guide explains how to configure the Jubilee Powder system for your specific setup.

## Overview

The Jubilee Automation system uses JSON configuration files to define:

- Physical positions and movements
- Deck layout and labware
- System parameters and hardware settings
- Operational constraints and safety zones

All configuration files are located in the `jubilee_api_config/` directory.

## Configuration Files

### motion_platform_positions.json

Defines named positions, their coordinates, and valid transitions.

**Purpose**: State machine position definitions and movement validation

**Location**: `jubilee_api_config/motion_platform_positions.json`

#### Structure

```json
{
  "positions": {
    "position_name": {
      "coordinates": {
        "x": 100.0,
        "y": 150.0,
        "z": 200.0,
        "safe_z": 250.0
      },
      "description": "Human-readable description",
      "requires_tool": "manipulator",
      "allowed_payloads": ["empty", "mold", "mold_with_piston"],
      "constraints": {
        "min_z": 50.0,
        "max_z": 300.0
      }
    }
  },
  "transitions": {
    "position_name": {
      "to": ["other_position", "another_position"],
      "requires_payload": null
    }
  }
}
```

#### Key Fields

- **`coordinates`**: Physical X, Y, Z positions in millimeters
- **`safe_z`**: Height for safe travel over obstacles
- **`requires_tool`**: Tool that must be active (or `null` for any/none)
- **`allowed_payloads`**: List of valid payload states for this position
- **`transitions.to`**: List of positions directly reachable from here

#### Example: Adding a New Position

```json
{
  "positions": {
    "my_custom_position": {
      "coordinates": {
        "x": 120.0,
        "y": 180.0,
        "z": 100.0,
        "safe_z": 200.0
      },
      "description": "Custom position for special labware",
      "requires_tool": "manipulator",
      "allowed_payloads": ["empty"]
    }
  },
  "transitions": {
    "global_ready": {
      "to": ["my_custom_position"]
    },
    "my_custom_position": {
      "to": ["global_ready"]
    }
  }
}
```

### system_config.json

Defines system-level parameters and hardware settings.

**Purpose**: Global system configuration

**Location**: `jubilee_api_config/system_config.json`

#### Structure

```json
{
  "system": {
    "duet_ip": "192.168.1.100",
    "scale_port": "/dev/ttyUSB0",
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

#### Key Sections

- **`system`**: Global system settings (IPs, ports, defaults)
- **`tools`**: Tool-specific configurations
- **`safety`**: Safety parameters and limits

### mold_labware.json

Defines deck layout, labware positions, and well configurations.

**Purpose**: Physical deck layout and labware definitions

**Location**: `jubilee_api_config/mold_labware.json`

#### Structure

```json
{
  "deck": {
    "name": "Main Deck",
    "dimensions": {
      "width": 300,
      "height": 300
    },
    "labware": {
      "well_plate_1": {
        "type": "well_plate",
        "name": "24-Well Plate",
        "rows": 4,
        "columns": 6,
        "well_spacing_x": 20.0,
        "well_spacing_y": 20.0,
        "origin": {"x": 50, "y": 50, "z": 10},
        "wells": {
          "A1": {
            "position": {"x": 50, "y": 50, "z": 10},
            "ready_pos": "mold_slot_A1",
            "capacity_ml": 10.0,
            "description": "Top-left well"
          }
        }
      }
    }
  }
}
```

#### Key Fields

- **`labware`**: Dictionary of all labware on the deck
- **`wells`**: Individual well definitions with positions
- **`ready_pos`**: Links to named position in motion_platform_positions.json

### weight_well_deck.json

Defines well-specific weight parameters and tolerances.

**Purpose**: Weight-related configuration for dispense operations

**Location**: `jubilee_api_config/weight_well_deck.json`

#### Structure

```json
{
  "weight_config": {
    "A1": {
      "tare_weight": 5.2,
      "target_tolerance": 0.1,
      "max_fill_time": 120,
      "trickler_speed": "medium"
    },
    "A2": {
      "tare_weight": 5.3,
      "target_tolerance": 0.05,
      "max_fill_time": 180,
      "trickler_speed": "slow"
    }
  }
}
```

#### Key Fields

- **`tare_weight`**: Empty mold weight in grams
- **`target_tolerance`**: Acceptable deviation from target in grams
- **`max_fill_time`**: Maximum seconds to attempt filling
- **`trickler_speed`**: Powder dispense rate

## Common Configuration Tasks

### Task 1: Change Jubilee IP Address

Edit `system_config.json`:

```json
{
  "system": {
    "duet_ip": "192.168.1.200"
  }
}
```

### Task 2: Add a New Well Plate

1. **Add labware definition** to `mold_labware.json`:

```json
{
  "deck": {
    "labware": {
      "my_new_plate": {
        "type": "well_plate",
        "name": "12-Well Plate",
        "rows": 3,
        "columns": 4,
        "well_spacing_x": 25.0,
        "well_spacing_y": 25.0,
        "origin": {"x": 100, "y": 100, "z": 15},
        "wells": {}
      }
    }
  }
}
```

2. **Generate well positions** (use a script or manually):

```python
import json

rows = ['A', 'B', 'C']
cols = range(1, 5)  # 1-4
origin_x, origin_y = 100, 100
spacing_x, spacing_y = 25, 25

wells = {}
for i, row in enumerate(rows):
    for j, col in enumerate(cols):
        well_id = f"{row}{col}"
        wells[well_id] = {
            "position": {
                "x": origin_x + (j * spacing_x),
                "y": origin_y + (i * spacing_y),
                "z": 15
            },
            "ready_pos": f"mold_slot_{well_id}",
            "capacity_ml": 5.0
        }

print(json.dumps(wells, indent=2))
```

3. **Add positions** to `motion_platform_positions.json` for each well

4. **Add weight config** to `weight_well_deck.json` if using for dispense

### Task 3: Adjust Movement Speed

Edit `system_config.json`:

```json
{
  "system": {
    "default_feedrate": "FAST"
  }
}
```

Or in your code:

```python
from jubilee_api_config.constants import FeedRate

manager = JubileeManager(
    num_piston_dispensers=2,
    num_pistons_per_dispenser=10,
    feedrate=FeedRate.FAST
)
```

### Task 4: Configure Piston Dispensers

Add dispenser configuration to `mold_labware.json`:

```json
{
  "deck": {
    "labware": {
      "piston_dispenser_1": {
        "type": "piston_dispenser",
        "name": "Dispenser 1",
        "position": {"x": 200, "y": 50, "z": 20},
        "ready_pos": "dispenser_0_ready",
        "capacity": 20,
        "piston_height": 50.0,
        "piston_diameter": 10.0
      }
    }
  }
}
```

Add corresponding position to `motion_platform_positions.json`:

```json
{
  "positions": {
    "dispenser_0_ready": {
      "coordinates": {"x": 200, "y": 50, "z": 100, "safe_z": 150},
      "description": "Ready position for piston dispenser 0",
      "requires_tool": "manipulator",
      "allowed_payloads": ["mold_with_piston"]
    }
  }
}
```

## Configuration Best Practices

### 1. Use Version Control

Always commit configuration changes to git:

```bash
git add jubilee_api_config/
git commit -m "Add new well plate configuration"
```

### 2. Keep Backups

Before making major changes:

```bash
cp -r jubilee_api_config/ jubilee_api_config_backup_$(date +%Y%m%d)/
```

### 3. Validate Configurations

Create a validation script:

```python
import json
from pathlib import Path

def validate_config():
    """Validate all configuration files."""
    config_dir = Path("jubilee_api_config")
    
    # Check all required files exist
    required_files = [
        "motion_platform_positions.json",
        "system_config.json",
        "mold_labware.json"
    ]
    
    for file in required_files:
        path = config_dir / file
        if not path.exists():
            print(f"❌ Missing: {file}")
            return False
        
        # Validate JSON syntax
        try:
            with open(path) as f:
                json.load(f)
            print(f"✅ Valid: {file}")
        except json.JSONDecodeError as e:
            print(f"❌ Invalid JSON in {file}: {e}")
            return False
    
    return True

if __name__ == "__main__":
    if validate_config():
        print("\n✅ All configurations valid!")
    else:
        print("\n❌ Configuration validation failed!")
```

### 4. Document Custom Values

Add comments in JSON (non-standard but helpful):

```json
{
  "_comment": "Custom configuration for 24-well plate setup",
  "deck": {
    "labware": {}
  }
}
```

Or maintain a separate README:

```markdown
# Configuration Notes

## Well Plate Layout
- Origin measured from front-left corner of deck
- Z=10mm is the pickup height
- safe_z=150mm clears all obstacles

## Last Updated
2025-01-06: Added new dispenser position
```

### 5. Test After Changes

Always test configuration changes:

```python
# Test script
from src.JubileeManager import JubileeManager

manager = JubileeManager()
if manager.connect():
    print("✅ Connection successful with new config")
    manager.disconnect()
else:
    print("❌ Connection failed - check configuration")
```

## Troubleshooting Configuration Issues

### Configuration Not Loading

**Symptom**: "Config file not found" error

**Solutions**:
- Check file paths are correct
- Verify files are in `jubilee_api_config/` directory
- Check file permissions

### Invalid JSON Syntax

**Symptom**: `JSONDecodeError` when loading

**Solutions**:
- Use a JSON validator (jsonlint.com)
- Check for missing commas, braces, quotes
- Ensure no trailing commas (not valid in JSON)

### Position Not Found

**Symptom**: "Position 'X' not found in state machine"

**Solutions**:
- Verify position is defined in `motion_platform_positions.json`
- Check spelling and case sensitivity
- Ensure `ready_pos` in labware matches position name

### Transition Validation Failed

**Symptom**: "Cannot transition from A to B"

**Solutions**:
- Check that transition is defined in `transitions` section
- Verify transitions are bidirectional if needed
- Add intermediate positions if direct transition not safe

## Next Steps

- [Run operations on your configured setup](run-new-data.md)
- [Use Web UI to test positions](web-ui.md)
- [Review API reference for configuration usage](../api/config-loader.md)

