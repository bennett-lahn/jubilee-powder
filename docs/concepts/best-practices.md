# Best Practices

This page covers must-know information for safely operating the Jubilee system. Read this before your first run and refer back to it whenever you modify hardware or configuration.

---

## Duet3D Controller

The Jubilee uses a Duet3D board (typically Duet 3 Mini or Duet 3 MB6HC) running RepRapFirmware. The Duet3D is a precision motion controller and requires careful handling.

### Critical Rules

**Never connect or disconnect stepper motor cables while the Duet3D is powered.**
Doing so can permanently damage the stepper drivers on the board. Always power off the Duet3D completely before swapping or re-seating motor connectors.

**Never connect or disconnect endstop cables while the Duet3D is powered.**
Hot-plugging endstops can damage the input pins. Power off before making any endstop wiring changes

**Wait for the board to fully boot before sending commands.**
After powering on, wait for the Duet3D's status LED to stabilize and for the web interface to become responsive before connecting or issuing G-code.

### Web Interface

The Duet3D exposes a web interface (Duet Web Control, DWC) at the machine's IP address. Keep this open in a browser tab during operation - it lets you:

- Issue an immediate emergency stop (the red stop button)
- Monitor real-time axis positions and speeds
- View the console for firmware error messages
- Check motor current and driver status

If you cannot reach the web interface, the machine should be considered unreachable and you should not attempt to run scripts against it.

### Homing

The Jubilee must be homed after every power cycle. The software calls `homeall` automatically during `connect()`, but be aware:

- **Check the deck before homing.** Homing moves axes to their endstops at high speed. Any obstruction on the deck can cause a collision.

---

## Jubilee Hardware

### General Mechanical Safety

- **Keep hands and tools clear of the motion envelope during any move.** The Jubilee has no collision detection - it will drive into an obstruction without stopping.
- **Do not place items on the deck outside of their designated positions** defined in the configuration. The state machine validates moves against named positions, not arbitrary coordinates. Objects outside those positions are invisible to the software.
- **Secure all cables with sufficient slack** to cover the full range of motion. A taut cable can be torn loose, damaging connectors or the board.
- **Inspect the tool-changer coupling** before each session. The Jubilee uses a kinematic tool-changer; if the tool is not fully seated, it can fall or move unpredictably during operation.

### Tool Changes

- Only one tool can be active at a time. This is enforced by software, but physically ensure the tools are always returned to the correct rack position.
- If a tool drop is suspected (the carriage moved without the tool following), issue an emergency stop immediately and inspect before resuming.
- In normal operation, never manually push a tool onto the carriage while the machine is powered and connected. Use the software-driven pickup sequence.

### Deck Layout

!!! warning
    The deck configuration (`jubilee_api_config/motion_platform_positions.json`) defines exact positions for wells, scale, dispensers, and the tool dock. **If you move any labware, you MUST update the configuration to match.** Otherwise, the machine will not detect the change.
- Position calibration is required maintenance. Re-verify positions after any significant physical disturbance to the machine (e.g. machine was diassembled and reassembled, new deck/labware, collisions).

---

## Operational Best Practices

### Before Every Run

1. Confirm the Jubilee user interface is connected and homed with the appropriate number of pistons in each dispenser.
2. Confirm the deck is clear of any items that should not be there.
3. Confirm the scale is powered on and responding.
4. Confirm the piston dispensers are loaded with the correct number of pistons.

### First Run of a New Script

- **Always supervise the first run.** Sit at the machine with your hand near the emergency stop (either the power switch or user interface button).
- **Run at reduced feedrate** during the first execution to give yourself time to react. You can lower feedrates by adjusting the speed multiplier in configuration or by issuing `M220 S50` (50% speed) via Duet3D Web Interface before starting.
- **Run a single operation before a full batch.** Verify one well completes correctly before running all wells.

### Emergency Stop

There are several ways to stop the machine mid-run:

1. Click the red stop button in the Duet Web Control interface (immediate, stops all motion).
2. Press the red stop button on the user interface home screen.
3. Turn off the Jubilee power switch.

After an emergency stop, the machine is in an unknown position. **You must manually park the tool, cycle power to the Jubilee, and re-home all axes before resuming operation.**

### Long Runs and Unattended Operation

- Do not leave the machine fully unattended for long runs until you have validated the full sequence multiple times.
- If you must leave, verify the first several wells completed correctly and check that the dispenser has enough pistons for the remaining wells.

---

## Software and Scripting

### Check Return Values

Most `JubileeManager` methods return `True` on success and `False` on failure (or sometimes `MoveValidationResult`). Do not assume success - check the return value and handle failures explicitly.

```python
success = manager.dispense_to_well("0", 50.0)
if not success:
    print("Dispense failed - inspect before continuing")
    manager.disconnect()
    raise RuntimeError("Dispense operation failed")
```

### Do Not Bypass the State Machine

The `MotionPlatformStateMachine` validates all movements for safety. Do not send raw G-code moves through the science-jubilee library in parallel with the state machine - the state machine will not process these moves and its internal position will become incorrect.

### Configuration Changes

When modifying `motion_platform_positions.json` or other configuration files, restart the Python process before the next run. The configuration is loaded once at launch and is not reloaded automatically.

If you adjust physical positions on the machine, update the configuration and verify the new positions by jogging to them manually via Duet Web Interface before running the full automation.
