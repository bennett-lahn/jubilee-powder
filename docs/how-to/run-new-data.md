# How to Run Operations on New Data

This guide explains how to set up and run Jubilee operations with your own data and configurations.

## Overview

Running operations on "new data" typically means:

1. Setting up a new deck layout with your labware
2. Defining new well positions and identifiers
3. Running dispense operations on your custom configuration
4. Processing results

## Prerequisites

- [ ] Jubilee Automation installed and tested
- [ ] Hardware connected and functional
- [ ] Understanding of your deck layout requirements

## Step 1: Plan Your Deck Layout

Before configuring anything, plan your physical deck layout:

1. **Identify all labware** you'll use:
   - Mold/well plates
   - Piston dispensers
   - Scale
   - Any other equipment

2. **Measure positions** on the Jubilee deck:
   - Physical X, Y, Z coordinates
   - Clearance heights for safe movement
   - Tool approach angles

3. **Assign identifiers** to each well/position:
   - Use numerical indexing (e.g., "0", "1", "2")
   - Be consistent with naming conventions

## Step 2: Configure Deck Layout

Edit `jubilee_api_config/mold_labware.json` to define your labware:

### Example Configuration

```json
{
  "deck": {
    "labware": {
      "my_well_plate": {
        "type": "well_plate",
        "name": "My Custom Well Plate",
        "rows": 4,
        "columns": 6,
        "well_spacing_x": 20.0,
        "well_spacing_y": 20.0,
        "origin": {
          "x": 50.0,
          "y": 50.0,
          "z": 10.0
        },
        "wells": {
          "0": {
            "position": {"x": 50.0, "y": 50.0, "z": 10.0},
            "ready_pos": "mold_ready_0",
            "capacity_ml": 10.0
          },
          "1": {
            "position": {"x": 70.0, "y": 50.0, "z": 10.0},
            "ready_pos": "mold_ready_1",
            "capacity_ml": 10.0
          }
        }
      }
    }
  }
}
```

### Key Fields

- **`origin`**: The (0,0) position of your well plate
- **`well_spacing_x/y`**: Distance between wells in mm
- **`ready_pos`**: The named position in the state machine config

## Step 3: Configure State Machine Positions

Edit `jubilee_api_config/motion_platform_positions.json` to add your new positions:

```json
{
  "positions": {
    "mold_ready_0": {
      "coordinates": {
        "x": 50.0,
        "y": 50.0,
        "z": 100.0,
        "safe_z": 150.0
      },
      "description": "Ready position for mold 0",
      "requires_tool": "manipulator",
      "allowed_payloads": ["empty", "mold", "mold_with_piston"]
    },
    "mold_ready_1": {
      "coordinates": {
        "x": 70.0,
        "y": 50.0,
        "z": 100.0,
        "safe_z": 150.0
      },
      "description": "Ready position for mold 1",
      "requires_tool": "manipulator",
      "allowed_payloads": ["empty", "mold", "mold_with_piston"]
    }
  },
  "transitions": {
    "global_ready": {
      "to": ["mold_ready_0", "mold_ready_1", "scale_ready"]
    },
    "mold_ready_0": {
      "to": ["global_ready", "scale_ready"]
    },
    "mold_ready_1": {
      "to": ["global_ready", "scale_ready"]
    }
  }
}
```

### Key Fields

- **`coordinates`**: Physical position in mm
- **`safe_z`**: Height for safe travel
- **`requires_tool`**: Which tool must be active
- **`allowed_payloads`**: Valid payload states
- **`transitions`**: Which positions can be reached directly

## Step 4: Create a Processing Script

Create a Python script to process your data:

```python
from src.JubileeManager import JubileeManager
import json
from pathlib import Path

def load_target_weights(data_file):
    """
    Load target weights from your data file.
    
    Args:
        data_file: Path to JSON file with well IDs and target weights
        
    Returns:
        Dictionary mapping well IDs to target weights
    """
    with open(data_file, 'r') as f:
        return json.load(f)

def process_wells(manager, target_weights, use_tamping=False):
    """
    Process all wells with their target weights.
    
    Args:
        manager: Connected JubileeManager instance
        target_weights: Dict of {well_id: target_weight}
        use_tamping: Whether to tamp powder before inserting top piston
        
    Returns:
        Dictionary with results for each well
    """
    results = {}
    
    for well_id, target_weight in target_weights.items():
        print(f"Processing {well_id} with target weight {target_weight}g...")
        
        success = manager.dispense_to_well(
            well_id=well_id,
            target_weight=target_weight,
            use_tamping=use_tamping  # Enable tamping if desired
        )
        
        # Get final weight for verification
        if success:
            # Move back to scale to verify (optional)
            final_weight = manager.get_weight_stable()
        else:
            final_weight = None
            
        results[well_id] = {
            "success": success,
            "target_weight": target_weight,
            "final_weight": final_weight,
            "error": None if success else "Dispense failed",
            "tamped": use_tamping
        }
        
        print(f"  Result: {'SUCCESS' if success else 'FAILED'}")
    
    return results

def save_results(results, output_file):
    """Save processing results to JSON file."""
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {output_file}")

def main():
    # Configuration
    DATA_FILE = "my_target_weights.json"  # Your input data
    OUTPUT_FILE = "processing_results.json"  # Results output
    JUBILEE_IP = "192.168.1.100"
    
    # Load target weights
    target_weights = load_target_weights(DATA_FILE)
    print(f"Loaded {len(target_weights)} wells to process")
    
    # Create and connect manager
    manager = JubileeManager(
        num_piston_dispensers=2,
        num_pistons_per_dispenser=10
    )
    
    if not manager.connect(machine_address=JUBILEE_IP):
        print("Failed to connect to Jubilee!")
        return
    
    try:
        # Process all wells
        # Set use_tamping=True to compress powder before inserting piston
        results = process_wells(manager, target_weights, use_tamping=True)
        
        # Save results
        save_results(results, OUTPUT_FILE)
        
        # Print summary
        successful = sum(1 for r in results.values() if r["success"])
        print(f"\nProcessing complete:")
        print(f"  Successful: {successful}/{len(results)}")
        print(f"  Failed: {len(results) - successful}/{len(results)}")
        
    finally:
        manager.disconnect()
        print("Disconnected from hardware")

if __name__ == "__main__":
    main()
```

## Step 5: Prepare Your Input Data

Create a JSON file with your target weights (`my_target_weights.json`):

```json
{
  "0": 50.5,
  "1": 45.0,
  "2": 52.3,
  "3": 48.7,
  "4": 51.2
}
```

## Step 6: Run Your Script

1. **Test with one mold first**:
```python
target_weights = {"0": 50.0}  # Start with just one
```

2. **Monitor the first run**:
   - Watch the Jubilee physically
   - Be ready to emergency stop if needed
   - Verify positions are correct

3. **Run full batch** after successful test:
```bash
python process_my_data.py
```

## Step 7: Verify Results

Check the output file (`processing_results.json`):

```json
{
  "0": {
    "success": true,
    "target_weight": 50.5,
    "final_weight": 50.48,
    "error": null
  },
  "1": {
    "success": true,
    "target_weight": 45.0,
    "final_weight": 45.02,
    "error": null
  }
}
```

## Expected Output

During a successful run, you should see:

```
Loaded 5 molds to process
Connected successfully!
Processing 0 with target weight 50.5g...
  Result: SUCCESS
Processing 1 with target weight 45.0g...
  Result: SUCCESS
...
Results saved to processing_results.json

Processing complete:
  Successful: 5/5
  Failed: 0/5
Disconnected from hardware
```

## Troubleshooting

### Well ID Not Found

**Symptom**: Error "Well ID 'X1' not found"

**Solution**:
- Check that the well ID exists in `mold_labware.json`
- Verify the well ID spelling/case matches exactly
- Ensure the labware is loaded in the configuration

### Position Validation Failed

**Symptom**: "Move to mold slot failed: validation error"

**Solution**:
- Check that the position is defined in `motion_platform_positions.json`
- Verify the `ready_pos` field in the well configuration matches the position name
- Ensure transitions are defined from current position to target position

### Incorrect Physical Position

**Symptom**: Jubilee moves to wrong location

**Solution**:
- Verify coordinates in configuration are correct
- Check that you're using the right coordinate system (absolute vs relative)
- Home the Jubilee before starting
- Use the Duet Web Control to manually verify positions

### Dispense Fails

**Symptom**: `dispense_to_well()` returns False

**Solution**:
- Check that pistons are available in dispenser
- Verify scale is connected and responding
- Ensure trickler/powder source is configured
- Check logs for specific error messages

## Advanced Features

### Using Tamping

Tamping compresses the powder in a mold before inserting the top piston. This is useful for:

1. **Ensuring safe top piston placement** when powder volume is high
2. **Reducing airborne powder** when inserting the piston

To enable tamping in your workflow:

```python
# Enable tamping for all wells
results = process_wells(manager, target_weights, use_tamping=True)
```

Or, for finer control with the low-level API:

```python
# Manual control over tamping
manager.pick_mold_from_scale()  # After filling with powder

# Tamp the powder
manager.manipulator.tamp(
    tamp_depth=40.0,    # Depth in mm (valid range from system_config.json)
    tamp_speed=2000     # Speed in mm/min (valid range from system_config.json)
)

# Continue with piston insertion
manager.move_to_dispenser(dispenser_index=0)
manager.manipulator.place_top_piston(manager.piston_dispensers[0])
```

**When to use tamping**:

- High powder volumes that might prevent piston insertion
- Fine powders that easily become airborne
- When consistent compression is required for your application

**Parameter Bounds**:

Parameter bounds are configured in `system_config.json` under the `manipulator` section and can be customized for your application:

```json
{
  "manipulator": {
    "tamp_depth_min": 10.0,   // mm - minimum depth to ensure meaningful compression
    "tamp_depth_max": 60.0,   // mm - maximum depth to prevent damage
    "tamp_speed_min": 500,    // mm/min - minimum speed for controlled movement
    "tamp_speed_max": 5000    // mm/min - maximum speed to prevent impact damage
  }
}
```

Default bounds:
- **Tamp Depth**: 10-60 mm (default value: 40 mm)
- **Tamp Speed**: 500-5000 mm/min (default value: 2000 mm/min)

**Note**: After tamping, the V axis is automatically re-homed to ensure axis accuracy. The homing process uses the mold itself as a reference (starting at v=2 with tamper inserted, ending at v=-7 with tamper touching the mold bottom). This is safe because the mold does not have a top piston during tamping. Parameter bounds are enforced by the state machine to ensure safe operation.

## Tips

!!! tip "Start Small"
    Always test with a single well before running large batches.

!!! tip "Backup Configurations"
    Keep backup copies of working configurations before making changes.

!!! tip "Use Relative Positions"
    Define well positions relative to a reference point for easier reconfiguration.

!!! warning "Verify Physically"
    Always verify that configured positions match physical reality before running automated operations.

## Next Steps

- [Configure advanced parameters](configuration.md)
- [Interpret and analyze results](results.md)
- [Use the Web UI for monitoring](web-ui.md)

