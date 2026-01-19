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
    manipulator.pick_mold("A1")
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
manipulator.pick_mold(well_id="A1")

# Place mold on scale
manipulator.place_mold_on_scale()

# Pick mold from scale
manipulator.pick_mold_from_scale()

# Place mold back in well
manipulator.place_mold(well_id="A1")
```

### V-Axis Movement

```python
# Move V-axis to specific position
manipulator.move_v_axis(position=50.0)  # 50mm

# Home V-axis
manipulator.home_v_axis()
```

## Pick and Place Operations

### Pick Mold

The `pick_mold()` operation:



1. Validates current position (must be at mold slot)
2. Moves V-axis down to mold height
3. Moves manipulator under mold
4. Moves V-axis up with mold
5. Moves back to mold ready position
6. Updates payload state to `"mold"`

```python
try:
    manipulator.pick_mold(well_id="A1")
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
    manipulator.place_mold(well_id="A1")
    print("Mold placed successfully")
except ToolStateError as e:
    print(f"Place failed: {e}")
```

**Requirements**:
- Must be at the correct mold slot position
- Payload must be `"mold"` or `"mold_with_piston"`

### Scale Operations

Special methods for scale interaction:

```python
# Place on scale
manipulator.place_mold_on_scale()

# Pick from scale
manipulator.pick_mold_from_scale()
```

These are very similar to regular pick/place for scale interaction.

## State Management

### Automatic State Updates

The Manipulator automatically updates the state machine's payload state:

```python
# Initially empty
print(manipulator.state_machine.context.payload_state)  # "empty"

# Pick mold
manipulator.pick_mold("A1")
print(manipulator.state_machine.context.payload_state)  # "mold"

# Place mold
manipulator.place_mold("A1")
print(manipulator.state_machine.context.payload_state)  # "empty"
```

### Payload States

| State | Description | Set By |
|-------|-------------|--------|
| `empty` | Nothing held | `place_mold()`, `place_mold_on_scale()` |
| `mold` | Holding empty mold | `pick_mold()`, `pick_mold_from_scale()` |
| `mold_with_piston` | Holding mold with piston | Manual update after piston insertion |

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
manipulator.pick_mold("A1")
manipulator.pick_mold("B1")  # Error: already holding mold
```

**Placing when empty**:
```python
# This will raise ToolStateError
manipulator.place_mold("A1")  # Error: not holding anything
```

**Wrong position**:
```python
# Move to wrong position
state_machine.validated_move_to_scale()

# This will raise ToolStateError
manipulator.pick_mold("A1")  # Error: not at mold slot
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
manipulator.pick_mold("A1")

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
    manipulator.pick_mold("A1")
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
result = state_machine.validated_move_to_mold_slot("A1")
if result.valid:
    manipulator.pick_mold("A1")

# BAD: Direct machine control bypasses validation
machine.move_to(x=100, y=100, z=50)  # Not validated!
manipulator.pick_mold("A1")          # May fail or cause collision
```

## See Also

- [JubileeManager](jubilee-manager.md) - High-level interface using Manipulator
- [MotionPlatformStateMachine](motion-platform.md) - State tracking and validation
- [PistonDispenser](piston-dispenser.md) - Related component
- [Quick Start Guide](../getting-started/quickstart.md) - Basic usage examples

