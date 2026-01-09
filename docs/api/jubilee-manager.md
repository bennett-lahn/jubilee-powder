# JubileeManager API Reference

The `JubileeManager` class is the primary interface for controlling the Jubilee powder dispensing system. It provides high-level methods for common operations and coordinates multiple hardware components.

## Overview

`JubileeManager` is designed to be your main entry point for:

- Connecting to and managing hardware
- Performing dispense operations
- Reading scale weights
- Coordinating complex multi-step operations

All movements are validated through an internal `MotionPlatformStateMachine` which cannot be bypassed, ensuring safety and consistency.

## Class Reference

::: src.JubileeManager.JubileeManager
    options:
      members:
        - __init__
        - connect
        - disconnect
        - machine_read_only
        - deck
        - piston_dispensers
        - get_weight_stable
        - get_weight_unstable
        - dispense_to_well
      show_root_heading: true
      show_source: false

## Usage Examples

### Basic Connection and Usage

```python
from src.JubileeManager import JubileeManager

# Create manager instance
manager = JubileeManager(
    num_piston_dispensers=2,
    num_pistons_per_dispenser=10
)

# Connect to hardware
if manager.connect(machine_address="192.168.1.100"):
    print("Connected successfully!")
    
    # Use the manager
    weight = manager.get_weight_stable()
    print(f"Current weight: {weight}g")
    
    # Clean up
    manager.disconnect()
```

### Performing Dispense Operations

```python
# After connecting...
success = manager.dispense_to_well(
    well_id="A1",
    target_weight=50.0
)

if success:
    print("Dispense completed successfully!")
else:
    print("Dispense failed - check logs for details")
```

### Accessing Hardware Components

```python
# Read-only access to machine (for queries, not movements)
if manager.machine_read_only:
    position = manager.machine_read_only.get_position()
    print(f"Current position: {position}")

# Access deck for labware information
if manager.deck:
    labware = manager.deck.get_labware()
    print(f"Available labware: {labware}")

# Access piston dispensers
for dispenser in manager.piston_dispensers:
    print(f"Dispenser {dispenser.index}: {dispenser.num_pistons} pistons")
```

### Error Handling

```python
from src.JubileeManager import JubileeManager

manager = JubileeManager()

try:
    if not manager.connect():
        raise ConnectionError("Failed to connect to Jubilee")
    
    # Perform operations
    success = manager.dispense_to_well("A1", 50.0)
    if not success:
        print("Operation failed but system is still connected")
    
except Exception as e:
    print(f"Error occurred: {e}")

finally:
    # Always disconnect
    manager.disconnect()
```

## Internal Methods

The following methods are primarily for internal use but are documented for developers:

::: src.JubileeManager.JubileeManager._move_to_mold_slot
    options:
      show_root_heading: true
      show_source: false

::: src.JubileeManager.JubileeManager._move_to_scale
    options:
      show_root_heading: true
      show_source: false

::: src.JubileeManager.JubileeManager._move_to_dispenser
    options:
      show_root_heading: true
      show_source: false

::: src.JubileeManager.JubileeManager._fill_powder
    options:
      show_root_heading: true
      show_source: false

::: src.JubileeManager.JubileeManager.get_piston_from_dispenser
    options:
      show_root_heading: true
      show_source: false

## Design Notes

### State Machine Ownership

`JubileeManager` owns the `MotionPlatformStateMachine` instance. This design ensures:

- All movements must go through validation
- No external code can bypass safety checks
- Consistent state tracking across the system

### Read-Only Machine Access

The `machine_read_only` property provides access to the underlying `Machine` object for read operations only. While it's technically possible to perform write operations through this property, **doing so bypasses safety validation and is strongly discouraged**.

Use `machine_read_only` only for:
- Querying current position
- Reading sensor values
- Checking machine state

**Never use it for**:
- Moving axes
- Picking/parking tools
- Any operation that changes machine state

### Connection Sequence

The `connect()` method performs several initialization steps:

1. Connects to the Duet controller
2. Connects to the scale
3. Initializes the state machine with configuration
4. Initializes the deck and dispensers
5. Homes all axes (X, Y, Z, U)
6. Picks up the manipulator tool
7. Homes the manipulator axis (V)

This ensures the system is in a known, safe state before operations begin.

## See Also

- [MotionPlatformStateMachine](motion-platform.md) - For advanced movement control
- [Manipulator](manipulator.md) - Gripper tool details
- [Scale](scale.md) - Scale interface
- [Quick Start Guide](../getting-started/quickstart.md) - Getting started tutorial

