# Manipulator API Reference

The `Manipulator` class represents a gripper tool with a vertical axis (V-axis) used for picking and placing molds.

## Overview

The Manipulator is a custom toolhead that provides:

- **Gripper**: moves up/down to hold objects
- **V-Axis**: Vertical movement independent of machine Z-axis
- **State Integration**: Automatically updates state machine context

## Class Reference

::: src.Manipulator.Manipulator
    options:
      members: true
      show_root_heading: true
      show_source: false
      filters:
        - "!^_[^_]"  # Hide private methods (except __init__)

## Exceptions

### ToolStateError

```python
class ToolStateError(Exception)
```

Exception raised when a tool operation is attempted in an invalid state.

This error is raised when trying to perform operations that require specific tool or payload states that are not currently met.

**Common Scenarios**:
- Attempting to pick a mold when already holding one
- Trying to place a mold when not holding one
- Operating at wrong position for the requested action

**Example**:
```python
from src.Manipulator import Manipulator, ToolStateError

try:
    manipulator.pick_mold("0")
except ToolStateError as e:
    print(f"Operation failed: {e}")
```

## Usage Examples

### Creating a Manipulator

```python
from src.Manipulator import Manipulator
from src.MotionPlatformStateMachine import MotionPlatformStateMachine

# Assume state_machine is already created
manipulator = Manipulator(
    index=0,                      # Tool index on Jubilee
    name="manipulator",           # Tool name
    state_machine=state_machine   # Reference to state machine
)
```

### Picking and Placing Molds

```python
# Pick up a mold from a well
manipulator.pick_mold(well_id="0")

# Place mold on scale
manipulator.place_mold_on_scale()

# Pick mold from scale
manipulator.pick_mold_from_scale()

# Place mold back in well
manipulator.place_mold(well_id="0")
```

### V-Axis Movement and Homing

```python
# Move V-axis to specific position
manipulator.move_v_axis(position=50.0)  # 50mm

# Home V-axis
manipulator.home_tamper()  # or home_v_axis()
```

**Homing with a Mold**:

The V-axis can be homed while holding a mold, **as long as the mold does not have a top piston**. During homing:

- **Start position**: `v=2` - Tamper is inserted into the mold
- **End position**: `v=-7` - Tamper touches the bottom of the mold
- This allows the system to establish accurate positioning reference using the mold itself

```python
# Example: Homing after picking up a mold without top piston
manipulator.pick_mold(well_id="0")
manipulator.home_tamper()  # Valid - mold has no top piston

# After tamping, V-axis is automatically re-homed
manipulator.tamp()  # Automatically homes V-axis after completion
```

**Important**: Do not attempt to home the V-axis when:
- The mold already has a top piston inserted
- Not holding a mold (should home before picking up mold)

## Pick and Place Operations

### Pick Mold

The `pick_mold()` operation:



1. Validates current position (must be at mold slot)
2. Moves V-axis down to mold height
3. Moves manipulator under mold
4. Moves V-axis up with mold
5. Moves back to mold ready position
6. Updates payload state to `"mold_without_top_piston"`

```python
try:
    manipulator.pick_mold(well_id="0")
    print("Mold picked successfully")
except ToolStateError as e:
    print(f"Pick failed: {e}")
```

**Requirements**:
- Must be at the correct mold slot position
- Payload must be `"empty"`
- V-axis must be homed

### Place Mold

The `place_mold()` operation:

1. Validates current position
2. Moves V-axis down
3. Moves manipulator out from under mold
4. Moves V-axis up
5. Updates payload state to `"empty"`

```python
try:
    manipulator.place_mold(well_id="0")
    print("Mold placed successfully")
except ToolStateError as e:
    print(f"Place failed: {e}")
```

**Requirements**:
- Must be at the correct mold slot position
- Payload must be `"mold_without_top_piston"` or `"mold_with_top_piston"`

### Scale Operations

Special methods for scale interaction:

```python
# Place on scale
manipulator.place_mold_on_scale()

# Pick from scale
manipulator.pick_mold_from_scale()
```

These are very similar to regular pick/place for scale interaction.

## Tamping Operations

### Tamp Mold

The `tamp()` method compresses powder in a mold held by the manipulator. This is typically done at the `scale_ready` position after filling a mold with powder and before inserting the top piston.

**Purpose of Tamping**:

1. **Reduce powder volume** - Allows the top piston to fit if the powder volume would otherwise prevent insertion
2. **Minimize airborne powder** - Compressing the powder reduces the amount that becomes airborne when the top piston is inserted

```python
# After filling mold with powder
manipulator.pick_mold_from_scale()

# Tamp the powder to compress it
manipulator.tamp(tamp_depth=40.0, tamp_speed=2000)

# Now safe to insert top piston
manager.move_to_dispenser()
manipulator.place_top_piston(piston_dispenser)
```

**Parameters**:

- `tamp_depth` (float): Target depth for tamping movement in mm (default: 40.0)
  - Valid range configured in `system_config.json` (default: 10-60 mm)
- `tamp_speed` (int): Speed for tamping movement in mm/min (default: 2000)
  - Valid range configured in `system_config.json` (default: 500-5000 mm/min)

**Requirements**:

- Must be carrying a mold (not empty)
- Mold must NOT have a top piston yet
- Typically performed at `scale_ready` position (but can be done at `mold_ready` positions too)

**How It Works**:

After tamping completes, the V axis is automatically re-homed to ensure axis accuracy. The homing process uses the mold itself as a reference:

- Homing starts at `v=2` (tamper inserted into mold)
- Homing ends at `v=-7` (tamper touching bottom of mold)
- This establishes an accurate position reference for subsequent operations

Since the mold does not have a top piston during tamping, the V-axis homing is safe and provides precise positioning.

**Example with Error Handling**:

```python
try:
    # Pick mold after filling
    manipulator.pick_mold_from_scale()
    
    # Tamp the powder
    manipulator.tamp(tamp_depth=40.0, tamp_speed=2000)
    print("Tamping successful")
    
except ToolStateError as e:
    print(f"Tamping failed: {e}")
    # Handle error - maybe skip tamping and try inserting piston anyway
```

**Common Errors**:

```python
# Error: Trying to tamp when not holding a mold
manipulator.tamp()  # ToolStateError: Must be carrying a mold

# Error: Trying to tamp after piston is already inserted
manipulator.place_top_piston(piston_dispenser)
manipulator.tamp()  # ToolStateError: Cannot tamp mold that has a top piston

# Error: Tamp depth out of bounds (bounds from system_config.json)
manipulator.tamp(tamp_depth=5.0)   # ToolStateError: Tamp depth out of bounds
manipulator.tamp(tamp_depth=70.0)  # ToolStateError: Tamp depth out of bounds

# Error: Tamp speed out of bounds (bounds from system_config.json)
manipulator.tamp(tamp_speed=100)    # ToolStateError: Tamp speed out of bounds
manipulator.tamp(tamp_speed=10000)  # ToolStateError: Tamp speed out of bounds
```

**Configuring Bounds**:

Tamping parameter bounds can be customized in `system_config.json`:

```json
{
  "manipulator": {
    "tamper_axis": "V",
    "tamp_depth_min": 10.0,
    "tamp_depth_max": 60.0,
    "tamp_speed_min": 500,
    "tamp_speed_max": 5000
  }
}
```

## State Management

### Automatic State Updates

The Manipulator automatically updates the state machine's payload state:

```python
# Initially empty
print(manipulator.state_machine.context.payload_state)  # "empty"

# Pick mold
manipulator.pick_mold("0")
print(manipulator.state_machine.context.payload_state)  # "mold_without_top_piston"

# Place mold
manipulator.place_mold("0")
print(manipulator.state_machine.context.payload_state)  # "empty"
```

### Payload States

| State | Description | Set By |
|-------|-------------|--------|
| `empty` | Nothing held | `place_mold()`, `place_mold_on_scale()` |
| `mold_without_top_piston` | Holding mold without top piston | `pick_mold()`, `pick_mold_from_scale()` |
| `mold_with_top_piston` | Holding mold with top piston | Piston retrieval workflow |

## Configuration

### Loading Configuration

The Manipulator loads its configuration from `system_config.json`:

```json
{
  "tools": {
    "manipulator": {
      "index": 0,
      "park_position": {"x": 0, "y": 0, "z": 100},
      "v_axis_offset": 50.0,
      "gripper_config": {
        "open_position": 5.0,
        "close_position": 0.0,
        "grip_force": 10.0
      },
      "mold_heights": {
        "pickup_height": 15.0,
        "clearance_height": 50.0
      }
    }
  }
}
```

### Configuration Parameters

- **`index`**: Tool index on Jubilee (usually 0)
- **`park_position`**: Where tool parks when not in use
- **`v_axis_offset`**: V-axis offset from machine zero
- **`gripper_config`**: Gripper open/close positions and force
- **`mold_heights`**: Heights for mold pickup and clearance

### Accessing Configuration

```python
# Get current configuration as dict
config = manipulator._get_config_dict()
print(config)

# Configuration is loaded automatically from ConfigLoader
```

## Error Handling

### Common Error Scenarios

**Picking when not empty**:
```python
# This will raise ToolStateError
manipulator.pick_mold("0")
manipulator.pick_mold("1")  # Error: already holding mold
```

**Placing when empty**:
```python
# This will raise ToolStateError
manipulator.place_mold("0")  # Error: not holding anything
```

**Wrong position**:
```python
# Move to wrong position
state_machine.validated_move_to_scale()

# This will raise ToolStateError
manipulator.pick_mold("0")  # Error: not at mold slot
```

## Advanced Usage

### Integration with State Machine

The Manipulator is tightly integrated with the state machine:

```python
# Create manipulator with state machine reference
manipulator = Manipulator(
    index=0,
    name="manipulator",
    state_machine=state_machine
)

# Manipulator automatically updates state machine context
manipulator.pick_mold("0")

# State machine knows about the payload
result = state_machine.validated_move_to_scale()
if not result.valid:
    print(f"Move failed: {result.reason}")
    # Might fail if payload not allowed at scale
```

## Best Practices

### Use Try-Except Blocks

Always handle `ToolStateError`:

```python
try:
    manipulator.pick_mold("0")
    manipulator.place_mold_on_scale()
except ToolStateError as e:
    print(f"Operation failed: {e}")
    # Handle error appropriately
    # Maybe release gripper, move to safe position, etc.
```

### Coordinate with State Machine

Don't bypass state machine validation:

```python
# GOOD: Use state machine for movements
result = state_machine.validated_move_to_mold_slot("0")
if result.valid:
    manipulator.pick_mold("0")

# BAD: Direct machine control bypasses validation
machine.move_to(x=100, y=100, z=50)  # Not validated!
manipulator.pick_mold("0")          # May fail or cause collision
```

## See Also

- [JubileeManager](jubilee-manager.md) - High-level interface using Manipulator
- [MotionPlatformStateMachine](motion-platform.md) - State tracking and validation
- [PistonDispenser](piston-dispenser.md) - Related component
- [Quick Start Guide](../getting-started/quickstart.md) - Basic usage examples

