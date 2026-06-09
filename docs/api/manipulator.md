# Manipulator API Reference

The `Manipulator` class represents a gripper tool with a vertical axis (V-axis) used for picking and placing molds.

## Overview

The Manipulator is a custom toolhead that provides:

- **Gripper**: moves up/down to hold objects
- **V-Axis**: Vertical movement independent of machine Z-axis
- **State Integration**: Automatically updates state machine context

!!! warning "State machine required"
    Pass a connected `MotionPlatformStateMachine` to `__init__`. Methods that move or change payload raise `RuntimeError` if `state_machine` is missing.

!!! tip "Prefer JubileeManager for workflows"
    Construct a `Manipulator` when extending low-level tool behavior. For dispense and tamp sequences, use [JubileeManager](jubilee-manager.md) so movements and payload state stay synchronized.

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
# Home V-axis (tamper axis) through the state machine
manipulator.home_tamper()
```

Direct V-axis positioning is not exposed on `Manipulator`; use validated moves to
`scale_ready` or `mold_ready_N` positions and let pick/place/tamp sequences drive V.

**Homing with a Mold**:

The V-axis can be homed while holding a mold, **as long as the mold does not have a top piston**. During homing:

- **Start position**: `v=2` - Tamper is inserted into the mold
- **End position**: `v=-7` - Tamper touches the bottom of the mold
- This allows the system to establish accurate positioning reference using the mold itself

```python
from src.ConfigLoader import config

tamp_depth, tamp_speed = config.get_tamp_defaults()

# Example: Homing after picking up a mold without top piston
manipulator.pick_mold(well_id="0")
manipulator.home_tamper()  # Valid - mold has no top piston

# After tamping, V-axis is automatically re-homed
manipulator.tamp(tamp_depth=tamp_depth, tamp_speed=tamp_speed)
```

**Important**: Do not attempt to home the V-axis when:

- The mold already has a top piston inserted
- Not holding a mold (home before picking up a mold)

!!! warning "Homing with a top piston risks collision"
    V-axis homing uses the mold cavity as a mechanical reference (`v=2` to `v=-7`). A mold with a top piston blocks that travel and can damage the tamper or piston.

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
from src.ConfigLoader import config
from src.JubileeManager import JubileeManager

tamp_depth, tamp_speed = config.get_tamp_defaults()

# After filling mold with powder (mold picked up from scale at scale_ready)
manipulator.pick_mold_from_scale()

# Tamp the powder to compress it
manipulator.tamp(tamp_depth=tamp_depth, tamp_speed=tamp_speed)

# Now safe to insert top piston
manager.move_to_dispenser()
manager.get_piston_from_dispenser()
```

**Parameters**:

- `tamp_depth` (float): Target depth for tamping movement in mm (required)
- `tamp_speed` (int): Speed for tamping movement in mm/min (required)

Valid ranges and defaults are defined in `system_config.json` under `manipulator` (loaded at startup by `ConfigLoader`). Use `config.get_tamp_defaults()` rather than hardcoding values.

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
from src.ConfigLoader import config

tamp_depth, tamp_speed = config.get_tamp_defaults()

try:
    manipulator.pick_mold_from_scale()
    manipulator.tamp(tamp_depth=tamp_depth, tamp_speed=tamp_speed)
    print("Tamping successful")
except ToolStateError as e:
    print(f"Tamping failed: {e}")
```

**Common Errors**:

```python
from src.ConfigLoader import config

tamp_depth, tamp_speed = config.get_tamp_defaults()

# Error: Trying to tamp when not holding a mold
manipulator.tamp(tamp_depth=tamp_depth, tamp_speed=tamp_speed)  # ToolStateError

# Error: Trying to tamp after piston is already inserted
state_machine.validated_retrieve_piston(
    manipulator_config=manipulator._get_config_dict()
)  # sets has_top_piston on the carried mold
manipulator.tamp(tamp_depth=tamp_depth, tamp_speed=tamp_speed)  # ToolStateError

# Error: Tamp depth or speed out of bounds (bounds from system_config.json)
manipulator.tamp(tamp_depth=999.0, tamp_speed=tamp_speed)   # ToolStateError
manipulator.tamp(tamp_depth=tamp_depth, tamp_speed=99999)   # ToolStateError
```

### Configuring Bounds

=== "Config"

    Tamping bounds and defaults live in `jubilee_api_config/system_config.json`:

    ```json
    {
      "manipulator": {
        "tamper_axis": "V",
        "tamp_depth_min": 0.0,
        "tamp_depth_max": 9.0,
        "tamp_speed_min": 500,
        "tamp_speed_max": 5000,
        "tamp_depth_default": 9.0,
        "tamp_speed_default": 500
      }
    }
    ```

    Values shown are from the checked-in config; adjust bounds in JSON and restart the process after changes.

=== "Python"

    Read defaults and bounds through `ConfigLoader`:

    ```python
    from src.ConfigLoader import config

    tamp_depth, tamp_speed = config.get_tamp_defaults()
    depth_min = config.get_tamp_depth_min()
    depth_max = config.get_tamp_depth_max()
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

The manipulator reads tool registration and tamping limits from `system_config.json` via `ConfigLoader` at construction time. Mold heights, gripper offsets, and named motion positions are defined in `motion_platform_positions.json`, not on the `Manipulator` class.

=== "Config"

    Tool index and name (under `tools`):

    ```json
    {
      "tools": {
        "manipulator": {
          "index": 0,
          "name": "manipulator"
        }
      }
    }
    ```

    Tamping axis and parameter bounds (top-level `manipulator`):

    ```json
    {
      "manipulator": {
        "tamper_axis": "V",
        "tamp_depth_min": 0.0,
        "tamp_depth_max": 9.0,
        "tamp_speed_min": 500,
        "tamp_speed_max": 5000,
        "tamp_depth_default": 9.0,
        "tamp_speed_default": 500
      }
    }
    ```

=== "Python"

    ```python
    from src.ConfigLoader import config

    tool_index = config.system.tools.manipulator.index
    tamper_axis = config.system.manipulator.tamper_axis
    tamp_depth, tamp_speed = config.get_tamp_defaults()

    # Passed to state machine validated actions
    manipulator_config = manipulator._get_config_dict()
    # {"tamper_axis": "V"}
    ```

!!! note "Motion positions are separate"
    Pick/place heights and XY coordinates come from [Position Configuration](position-config.md). Edit `motion_platform_positions.json` for layout changes; edit `system_config.json` for tamp limits and tool index, and meta system configuration.

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

???+ note "State machine integration"
    The manipulator updates payload context on pick/place; the state machine validates whether the next move is allowed.

    ```python
    manipulator = Manipulator(
        index=0,
        name="manipulator",
        state_machine=state_machine,
    )

    manipulator.pick_mold("0")

    result = state_machine.validated_move_to_scale()
    if not result.valid:
        print(f"Move failed: {result.reason}")
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
```

### Coordinate with State Machine

!!! tip "Validate moves before manipulator actions"
    ```python
    result = state_machine.validated_move_to_mold_slot("0")
    if result.valid:
        manipulator.pick_mold("0")
    ```

!!! warning "Direct machine moves bypass safety"
    ```python
    machine.move_to(x=100, y=100, z=50)  # Not validated
    manipulator.pick_mold("0")             # May fail or collide
    ```

## See Also

- [JubileeManager](jubilee-manager.md) - High-level interface using Manipulator
- [MotionPlatformStateMachine](motion-platform.md) - State tracking and validation
- [PistonDispenser](piston-dispenser.md) - Related component
- [Quick Start Guide](../getting-started/quickstart.md) - Basic usage examples

