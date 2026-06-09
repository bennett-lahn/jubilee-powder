# JubileeManager API Reference

The `JubileeManager` class is the primary interface for controlling the Jubilee powder dispensing system. It provides high-level methods for common operations and coordinates multiple hardware components.

!!! tip "Recommended entry point"
    Use `JubileeManager` for routine automation. Reach for [MotionPlatformStateMachine](motion-platform.md) directly only when you need unexposed operations.

## Overview

`JubileeManager` is designed to be the main entry point for:

- Connecting to and managing hardware
- Performing dispense operations
- Reading scale weights
- Coordinating complex multi-step movements

All movements are validated through an internal `MotionPlatformStateMachine` which cannot be bypassed, ensuring safety and consistency.

## Class Reference

Public methods delegate to the internal state machine. Longer workflow notes
and examples live in the sections below; docstrings focus on signatures and
safety callouts.

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
        - move_to_mold_slot
        - move_to_scale
        - move_to_dispenser
        - fill_powder
        - get_piston_from_dispenser
        - dispense_to_well
        - test_sample
        - hardness_turn_on
        - hardness_turn_off
        - hardness_zero
        - move_to_global_ready
        - set_dispenser_pistons
        - abort
      show_root_heading: true
      show_source: false

## Usage Examples

=== "Connect and read weight"

    ```python
    from src.JubileeManager import JubileeManager

    manager = JubileeManager(
        num_piston_dispensers=2,
        num_pistons_per_dispenser=10,
    )

    if manager.connect(machine_address="192.168.1.100"):
        print("Connected successfully!")

        weight = manager.get_weight_stable()
        print(f"Current weight: {weight}g")

        manager.disconnect()
    ```

=== "Dispense to well"

    ```python
    # After connecting...
    success = manager.dispense_to_well(
        well_id="0",
        target_weight=0.5,
    )

    if success:
        print("Dispense completed successfully!")
    else:
        print("Dispense failed - check logs for details")
    ```

=== "Hardware access"

    ```python
    # Read-only access to machine (for queries, not movements)
    if manager.machine_read_only:
        position = manager.machine_read_only.get_position()
        print(f"Current position: {position}")

    # Access deck for labware information
    if manager.deck:
        loaded_slots = [
            slot_key
            for slot_key, slot in manager.deck.slots.items()
            if slot.has_labware
        ]
        print(f"Slots with labware: {loaded_slots}")

    # Access piston dispensers
    for dispenser in manager.piston_dispensers:
        print(f"Dispenser {dispenser.index}: {dispenser.num_pistons} pistons")
    ```

=== "Hardness testing"

    ```python
    # After connecting with hardness testers configured in system_config.json...

    manager.hardness_turn_on(mode="shore_a")   # actuate power button via servo
    manager.hardness_zero(mode="shore_a")      # actuate zero button via servo

    success = manager.test_sample(tray_index=0, sample_index=3, mode="shore_a")
    if success:
        print(f"Hardness: {manager.last_hardness_result}")   # e.g. 42.5
        print(f"Error:    {manager.last_hardness_error}")    # None if clean read

    manager.hardness_turn_off(mode="shore_a")
    ```

    To target Shore-D instead of Shore-A, pass `mode="shore_d"` to any hardness method.

=== "Error handling"

    ```python
    from src.JubileeManager import JubileeManager

    manager = JubileeManager()

    try:
        if not manager.connect():
            raise ConnectionError("Failed to connect to Jubilee")

        success = manager.dispense_to_well("0", 0.5)
        if not success:
            print("Operation failed but system is still connected")

    except Exception as e:
        print(f"Error occurred: {e}")

    finally:
        manager.disconnect()
    ```

## Internal Validation and Execution Methods

!!! warning "Internal API"
    The symbols below document the state-machine path `JubileeManager` delegates to. Use `JubileeManager` instead in application code unless you are extending movement validation.

JubileeManager delegates movement validation and execution to the state machine.
The symbols below document the current internal execution path:

::: src.MotionPlatformStateMachine.MotionPlatformStateMachine.validated_move_to_mold_slot
    options:
      show_root_heading: true
      show_source: false

::: src.MotionPlatformStateMachine.MotionPlatformStateMachine.validated_move_to_scale
    options:
      show_root_heading: true
      show_source: false

::: src.MotionPlatformStateMachine.MotionPlatformStateMachine.validated_move_to_dispenser
    options:
      show_root_heading: true
      show_source: false

::: src.MotionPlatformStateMachine.MotionPlatformStateMachine.validated_fill_powder
    options:
      show_root_heading: true
      show_source: false

::: src.MotionPlatformStateMachine.MotionPlatformStateMachine.validated_retrieve_piston
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

The `machine_read_only` property provides access to the underlying `Machine` object for read operations only.

!!! danger "Do not move axes through machine_read_only"
    While it is possible to issue movement commands using this property, doing so bypasses safety validation and corrupts `JubileeManager`'s internal state.

Use `machine_read_only` only for:

- Querying current position
- Reading sensor values
- Checking machine state

Never use it for:

- Moving axes
- Picking or parking tools
- Any operation that changes machine state

### Connection Sequence

The `connect()` method performs several initialization steps:

1. Connects to the Duet controller
2. Connects to the scale
3. Initializes the state machine with configuration from [Position Configuration](position-config.md) and [ConfigLoader](config-loader.md)
4. Initializes the deck and dispensers
5. Homes all axes (X, Y, Z, U)
6. Leaves tools parked for on-demand pickup during operations

This ensures the system is in a known, safe state before operations begin.

## See Also

- [MotionPlatformStateMachine](motion-platform.md) - advanced movement control and validation
- [Position Configuration](position-config.md) - named positions and transition rules
- [ConfigLoader](config-loader.md) - `system_config.json` loading
- [Manipulator](manipulator.md) - gripper tool details
- [Scale](scale.md) - scale interface
- [Quick Start Guide](../getting-started/quickstart.md) - getting started tutorial
