# PistonDispenser API Reference

The `PistonDispenser` class manages containers that hold and dispense cylindrical pistons. It tracks the number of available pistons and their positions.

## Overview

PistonDispensers:

- Hold multiple pistons in a vertical stack
- Dispense pistons one at a time from the top
- Track remaining piston count
- Integrate with the state machine for validated retrieval

## Class Reference

::: src.PistonDispenser.PistonDispenser
    options:
      members: true
      show_root_heading: true
      show_source: false
      filters:
        - "!^_[^_]"  # Hide private methods (except __init__)

## Usage Examples

### Creating a Dispenser

```python
from src.PistonDispenser import PistonDispenser

# Create dispenser with state machine reference
dispenser = PistonDispenser(
    index=0,                      # Dispenser index (0, 1, etc.)
    num_pistons=10,              # Initial piston count
    state_machine=state_machine   # Reference to state machine
)
```

### Basic Operations

```python
# Check piston count
print(f"Pistons available: {dispenser.num_pistons}")

# Dispense a piston (decrements count)
dispenser.dispense_piston()
print(f"Pistons remaining: {dispenser.num_pistons}")

# Check if empty
if dispenser.num_pistons == 0:
    print("Dispenser is empty!")
```

### Integration with JubileeManager

Typically used through JubileeManager:

```python
from src.JubileeManager import JubileeManager

manager = JubileeManager(
    num_piston_dispensers=2,
    num_pistons_per_dispenser=10
)

manager.connect()

# Get piston from dispenser 0
manager._move_to_dispenser(dispenser_index=0)
manager.get_piston_from_dispenser(dispenser_index=0)

# Check remaining pistons
for dispenser in manager.piston_dispensers:
    print(f"Dispenser {dispenser.index}: {dispenser.num_pistons} pistons")
```

## Piston Tracking

### Automatic Count Management

The dispenser automatically decrements the piston count:

```python
dispenser = PistonDispenser(index=0, num_pistons=5, state_machine=sm)

print(dispenser.num_pistons)  # 5
dispenser.dispense_piston()
print(dispenser.num_pistons)  # 4
dispenser.dispense_piston()
print(dispenser.num_pistons)  # 3
```

### Checking Availability

Before attempting to retrieve a piston:

```python
if dispenser.num_pistons > 0:
    dispenser.dispense_piston()
    print("Piston retrieved")
else:
    print("Dispenser empty - needs refilling")
```

## Position Configuration

Dispenser positions are configured in `mold_labware.json`:

```json
{
  "deck": {
    "labware": {
      "piston_dispenser_0": {
        "type": "piston_dispenser",
        "name": "Dispenser 0",
        "position": {"x": 200, "y": 50, "z": 20},
        "ready_pos": "dispenser_0_ready",
        "capacity": 20,
        "piston_height": 50.0,
        "piston_diameter": 10.0,
        "stack_spacing": 2.0
      }
    }
  }
}
```

Corresponding state machine position in `motion_platform_positions.json`:

```json
{
  "positions": {
    "dispenser_0_ready": {
      "coordinates": {"x": 200, "y": 50, "z": 100, "safe_z": 150},
      "description": "Ready position for piston dispenser 0",
      "requires_tool": "manipulator",
      "allowed_payloads": ["mold"]
    }
  }
}
```

## Height Calculations

### Stack Height

The dispenser calculates the height of the top piston based on:

- Base position
- Number of remaining pistons
- Piston height
- Stack spacing

```python
# Internal calculation (simplified)
top_piston_z = base_z + (num_pistons * piston_height) + ((num_pistons - 1) * stack_spacing)
```

### Retrieval Position

When retrieving a piston:

1. Calculate current top piston height
2. Move V-axis to approach height (slightly above piston)
3. Descend to grip height
4. Close gripper
5. Ascend with piston
6. Decrement count

## Multiple Dispensers

### Working with Multiple Dispensers

```python
# Initialize multiple dispensers via JubileeManager
manager = JubileeManager(
    num_piston_dispensers=3,
    num_pistons_per_dispenser=10
)

manager.connect()

# Access all dispensers
for dispenser in manager.piston_dispensers:
    print(f"Dispenser {dispenser.index}: {dispenser.num_pistons} pistons")

# Get piston from specific dispenser
manager._move_to_dispenser(dispenser_index=0)
manager.get_piston_from_dispenser(dispenser_index=0)

# Check which dispenser has pistons
for dispenser in manager.piston_dispensers:
    if dispenser.num_pistons > 0:
        print(f"Dispenser {dispenser.index} has pistons available")
        break
```

### Load Balancing

Distribute piston usage across dispensers:

```python
def get_piston_from_any_dispenser(manager):
    """Get piston from first available dispenser."""
    for dispenser in manager.piston_dispensers:
        if dispenser.num_pistons > 0:
            manager._move_to_dispenser(dispenser.index)
            manager.get_piston_from_dispenser(dispenser.index)
            return dispenser.index
    
    raise RuntimeError("No dispensers have pistons available")
```

## State Machine Integration

### Validated Retrieval

Piston retrieval goes through state machine validation:

```python
from src.MotionPlatformStateMachine import MotionPlatformStateMachine

# Retrieve piston with validation
result = state_machine.validated_retrieve_piston(
    piston_dispenser=dispenser,
    manipulator_config=manipulator._get_config_dict()
)

if result.valid:
    print("Piston retrieved successfully")
else:
    print(f"Retrieval failed: {result.reason}")
```

### Requirements for Retrieval

- Must be at dispenser ready position
- Manipulator tool must be active
- Payload must be `"mold"` (retrieving into a mold)
- Dispenser must have pistons available

## Error Handling

### Empty Dispenser

```python
try:
    if dispenser.num_pistons == 0:
        raise RuntimeError("Dispenser is empty")
    
    dispenser.dispense_piston()
    
except RuntimeError as e:
    print(f"Cannot dispense: {e}")
    # Handle refill or switch dispenser
```

### Failed Retrieval

```python
result = state_machine.validated_retrieve_piston(
    piston_dispenser=dispenser,
    manipulator_config=config
)

if not result.valid:
    print(f"Retrieval failed: {result.reason}")
    
    # Common reasons:
    # - "Dispenser has no pistons"
    # - "Not at dispenser position"
    # - "Wrong payload state"
    # - "Wrong tool active"
```

## Refilling Dispensers

### Manual Refill

```python
def refill_dispenser(dispenser, num_pistons):
    """Manually refill a dispenser."""
    dispenser.num_pistons = num_pistons
    print(f"Dispenser {dispenser.index} refilled with {num_pistons} pistons")

# Refill when empty
for dispenser in manager.piston_dispensers:
    if dispenser.num_pistons == 0:
        refill_dispenser(dispenser, 10)
```

!!! note "Physical Refill Required"
    The software doesn't physically refill the dispenser. You must manually add pistons to the physical dispenser, then update the count in software.

### Tracking Usage

```python
def track_dispenser_usage(manager, operation_count):
    """Track piston usage statistics."""
    initial_counts = {d.index: d.num_pistons for d in manager.piston_dispensers}
    
    # Perform operations...
    
    final_counts = {d.index: d.num_pistons for d in manager.piston_dispensers}
    
    print("Piston Usage:")
    for index in initial_counts:
        used = initial_counts[index] - final_counts[index]
        print(f"  Dispenser {index}: {used} pistons used")
```

## Best Practices

### Check Before Dispensing

Always verify pistons are available:

```python
# GOOD
if dispenser.num_pistons > 0:
    dispenser.dispense_piston()
else:
    print("Need to refill")

# BAD
dispenser.dispense_piston()  # Might go negative!
```

### Monitor Levels

Track dispenser levels during operations:

```python
def dispense_with_monitoring(manager, well_list):
    """Dispense to wells with dispenser monitoring."""
    for well_id in well_list:
        # Check dispenser levels
        available = sum(d.num_pistons for d in manager.piston_dispensers)
        
        if available == 0:
            print("All dispensers empty - stopping")
            break
        
        if available < 5:
            print(f"Warning: Only {available} pistons remaining")
        
        # Perform dispense
        manager.dispense_to_well(well_id, target_weight=50.0)
```

### Coordinate Multiple Dispensers

Use all dispensers efficiently:

```python
def select_dispenser(manager):
    """Select dispenser with most pistons."""
    return max(manager.piston_dispensers, key=lambda d: d.num_pistons)

# Use the fullest dispenser
dispenser = select_dispenser(manager)
if dispenser.num_pistons > 0:
    manager._move_to_dispenser(dispenser.index)
    manager.get_piston_from_dispenser(dispenser.index)
```

## Configuration Examples

### Single Dispenser Setup

```json
{
  "deck": {
    "labware": {
      "main_dispenser": {
        "type": "piston_dispenser",
        "name": "Main Piston Dispenser",
        "position": {"x": 200, "y": 50, "z": 20},
        "ready_pos": "dispenser_0_ready",
        "capacity": 30,
        "piston_height": 45.0,
        "piston_diameter": 8.0,
        "stack_spacing": 1.5
      }
    }
  }
}
```

### Multiple Dispenser Setup

```json
{
  "deck": {
    "labware": {
      "dispenser_0": {
        "type": "piston_dispenser",
        "position": {"x": 200, "y": 50, "z": 20},
        "ready_pos": "dispenser_0_ready",
        "capacity": 20
      },
      "dispenser_1": {
        "type": "piston_dispenser",
        "position": {"x": 250, "y": 50, "z": 20},
        "ready_pos": "dispenser_1_ready",
        "capacity": 20
      }
    }
  }
}
```

## See Also

- [JubileeManager](jubilee-manager.md) - High-level dispenser operations
- [MotionPlatformStateMachine](motion-platform.md) - Validated piston retrieval
- [Manipulator](manipulator.md) - Gripper operations
- [Configuration Guide](../how-to/configuration.md) - Setting up dispensers

