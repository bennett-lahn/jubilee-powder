# PistonDispenser

The `PistonDispenser` class tracks piston inventory for one side-mounted dispenser station. Physical retrieval is executed by the motion platform and manipulator; this class decrements the count after each successful retrieval.

=== "Operator Guide"

    !!! warning "Prefer JubileeManager"
        Production workflows should call `JubileeManager.move_to_dispenser()` and `get_piston_from_dispenser()` rather than manipulating dispenser state directly.

    ## Overview

    Each `PistonDispenser` instance:

    - Tracks remaining piston count for one dispenser index
    - Exposes the motion platform ready position name (`dispenser_ready_N`)
    - Decrements count via `remove_piston()` after validated retrieval

    ## Usage Examples

    ### Creating a Dispenser

    ```python
    from src.PistonDispenser import PistonDispenser

    dispenser = PistonDispenser(
        index=0,
        num_pistons=10,
    )
    print(dispenser.ready_pos)  # "dispenser_ready_0"
    ```

    ### Basic Operations

    ```python
    print(f"Pistons available: {dispenser.num_pistons}")

    dispenser.remove_piston()
    print(f"Pistons remaining: {dispenser.num_pistons}")

    if dispenser.num_pistons == 0:
        print("Dispenser is empty!")
    ```

    `remove_piston()` raises `ValueError` when the dispenser is already empty.

    ### Integration with JubileeManager

    ```python
    from src.JubileeManager import JubileeManager

    manager = JubileeManager(
        num_piston_dispensers=2,
        num_pistons_per_dispenser=10,
    )
    manager.connect()

    manager.move_to_dispenser()
    manager.get_piston_from_dispenser()

    for dispenser in manager.piston_dispensers:
        print(f"Dispenser {dispenser.index}: {dispenser.num_pistons} pistons")
    ```

    ## Piston Tracking

    The count decrements only after the state machine completes a validated retrieval:

    ```python
    dispenser = PistonDispenser(index=0, num_pistons=5)
    print(dispenser.num_pistons)  # 5
    dispenser.remove_piston()
    print(dispenser.num_pistons)  # 4
    ```

    Before attempting retrieval, check availability:

    ```python
    if dispenser.num_pistons > 0:
        dispenser.remove_piston()
    else:
        print("Dispenser empty - needs refilling")
    ```

    ## Position Configuration

    Dispenser ready positions live in `motion_platform_positions.json`. Each entry uses the `DISPENSER_READY` type and requires the manipulator tool with a mold that has no top piston:

    ```json
    {
      "id": "dispenser_ready_0",
      "type": "DISPENSER_READY",
      "description": "Ready position for dispenser station 0.",
      "coordinates": {
        "x": 298.0,
        "y": 140.0,
        "z": 95.0,
        "v": 34.0
      },
      "requirements": {
        "active_tool_id": "manipulator",
        "payload_state": "mold_without_top_piston"
      }
    }
    ```

    Initial dispenser counts are set at connection time via `system_config.json`:

    ```json
    {
      "machine": {
        "num_dispensers": 2,
        "pistons_per_dispenser": 10
      }
    }
    ```

    See [Position Configuration](position-config.md) for adding new dispenser stations.

    ## Retrieval Workflow

    When `JubileeManager.get_piston_from_dispenser()` runs:

    1. Validates the machine is at `dispenser_ready_N` for the target dispenser
    2. Confirms manipulator tool is active and payload is `mold_without_top_piston`
    3. Executes the `retrieve_piston` motion action
    4. Decrements `num_pistons` on success

    ## Multiple Dispensers

    ```python
    manager = JubileeManager(
        num_piston_dispensers=3,
        num_pistons_per_dispenser=10,
    )
    manager.connect()

    for dispenser in manager.piston_dispensers:
        if dispenser.num_pistons > 0:
            manager.move_to_dispenser()
            manager.get_piston_from_dispenser()
            break
    ```

    ## State Machine Integration

    Advanced callers can invoke validation directly after moving to a dispenser ready position:

    ```python
    result = state_machine.validated_retrieve_piston(
        manipulator_config=manipulator._get_config_dict()
    )

    if result.valid:
        print("Piston retrieved successfully")
    else:
        print(f"Retrieval failed: {result.reason}")
    ```

    Requirements:

    - Current position must be `dispenser_ready_N`
    - Manipulator tool must be active
    - Payload must be `mold_without_top_piston`
    - Dispenser must have pistons available

    ## Error Handling

    ```python
    try:
        dispenser.remove_piston()
    except ValueError as e:
        print(f"Cannot dispense: {e}")
    ```

    Common `validated_retrieve_piston` failure reasons:

    - Dispenser has no pistons
    - Not at a `dispenser_ready` position
    - Wrong payload state or tool active

    ## Refilling Dispensers

    ```python
    def refill_dispenser(dispenser, num_pistons):
        dispenser.num_pistons = num_pistons
        print(f"Dispenser {dispenser.index} refilled with {num_pistons} pistons")
    ```

    !!! note "Physical refill required"
        Software only tracks inventory. Load pistons into the physical dispenser, then update `num_pistons` via the refill helper or the web UI `PUT /api/dispensers/{index}` endpoint.

    ## Best Practices

    - Check `num_pistons > 0` before retrieval; never call `remove_piston()` on an empty dispenser.
    - Monitor levels during batch jobs; stop when all dispensers are empty.
    - Prefer the fullest dispenser when multiple stations are available.

=== "API Reference"

    ## Class Reference

    ::: src.PistonDispenser.PistonDispenser
        options:
          members: true
          show_root_heading: true
          show_source: false
          filters:
            - "!^_[^_]"

---

## See Also

- [JubileeManager](jubilee-manager.md) - High-level dispenser operations
- [MotionPlatformStateMachine](motion-platform.md) - Validated piston retrieval
- [Manipulator](manipulator.md) - Gripper operations
- [Position Configuration](position-config.md) - Adding dispenser ready positions
- [Configuration Guide](../how-to/configuration.md) - Machine setup
