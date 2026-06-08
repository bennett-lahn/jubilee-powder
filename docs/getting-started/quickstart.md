# Quick Start Guide

This guide will walk you through creating your first Jubilee powder dispensing script.

## Prerequisites

Before starting, ensure you have:

- [ ] Jubilee Powder installed (see [Overview](overview.md))
- [ ] Jubilee machine powered on and network-accessible
- [ ] Scale connected via USB
- [ ] Configuration files set up in `jubilee_api_config/`

## Your First Script

### Step 1: Import JubileeManager

```python
from src.JubileeManager import JubileeManager
```

The `JubileeManager` class is your primary interface to the Jubilee system.

### Step 2: Create Manager Instance

```python
manager = JubileeManager(
    num_piston_dispensers=2,       # Number of piston dispensers
    num_pistons_per_dispenser=10   # Pistons per dispenser
)
```

### Step 3: Connect to Hardware

```python
from pathlib import Path

# Connect to the system
# Option 1: Use default (automatically finds config in project root)
connected = manager.connect(
    machine_address="192.168.1.100",  # Your Jubilee IP address
    scale_port="/dev/ttyUSB0"         # Scale serial port
    # state_machine_config defaults to project_root/jubilee_api_config/motion_platform_positions.json
)

# Option 2: Specify custom path (absolute or relative to project root)
# project_root = Path(__file__).parent.parent
# connected = manager.connect(
#     machine_address="192.168.1.100",
#     scale_port="/dev/ttyUSB0",
#     state_machine_config=str(project_root / "jubilee_api_config" / "motion_platform_positions.json")
# )

if not connected:
    print("Failed to connect!")
    exit(1)

print("Connected successfully!")
```

!!! warning
    The `connect()` method will automatically:
    
    - Connect to the Jubilee machine
    - Connect to the scale
    - Initialize the state machine
    - Home all axes
    - Leave tools parked until an operation requires one

    **Your Jubilee will move if this command is run. Ensure the deck is clear before connecting.**

### Step 4: Perform Operations

```python
# Dispense to a well with target weight
success = manager.dispense_to_well(
    well_id="0",            # Well identifier (numerical index 0-17)
    target_weight=50.0      # Target weight in grams
)

if success:
    print("Dispense operation completed successfully!")
else:
    print("Dispense operation failed!")
```

### Step 5: Clean Up

```python
# Always disconnect when done
manager.disconnect()
print("Disconnected from hardware")
```

## Complete Example

Here's the complete script:

```python
from src.JubileeManager import JubileeManager

def main():
    # Create manager
    manager = JubileeManager(
        num_piston_dispensers=2,
        num_pistons_per_dispenser=10
    )
    
    # Connect
    if not manager.connect(
        machine_address="192.168.1.100",
        scale_port="/dev/ttyUSB0"
    ):
        print("Failed to connect!")
        return
    
    try:
        # Read weight
        initial_weight = manager.get_weight_stable()
        print(f"Initial weight: {initial_weight}g")
        
        # Dispense operation
        success = manager.dispense_to_well(
            well_id="7",
            target_weight=0.5 # in grams
        )
        
        if success:
            print("Operation completed!")
        else:
            print("Operation failed!")
            
    finally:
        # Always disconnect
        manager.disconnect()

if __name__ == "__main__":
    main()
```

## Understanding What Happened

When you run this script:

1. **Connection Phase**:
   - Connects to Jubilee controller via network
   - Connects to scale via USB serial
   - Loads configuration from JSON files
   - Homes all machine axes (X, Y, Z, U, V)
   - Loads tools and keeps them parked until requested by operations

2. **Operation Phase**:
   - Moves to the specified mold location
   - Picks up the mold from the well
   - Moves to the scale
   - Places mold on scale
   - Fills powder to target weight
   - Picks up mold from scale
   - (Optional) Tamps powder to compress it (V-axis is re-homed after tamping)
   - Gets a piston from dispenser
   - Returns mold to well
   
   **Note**: The V-axis can be homed while holding a mold without a top piston. During homing, the tamper moves from v=2 (inserted into mold) to v=-7 (touching mold bottom), using the mold itself as a positioning reference.

3. **Cleanup Phase**:
   - Disconnects from all hardware
   - Releases resources

## Common Issues

### Connection Fails

If `manager.connect()` returns `False`:

- **Check Jubilee IP**: Verify the IP address is correct
- **Check Network**: Ensure your computer can reach the Jubilee (try `ping 192.168.1.100`)
- **Check Scale Port**: Verify the scale is connected (`ls /dev/ttyUSB*` on Linux)
- **Check Permissions**: Ensure you have permission to access the serial port

### Homing Fails

If homing fails during connection:

- **Check Endstops**: Ensure all endstops are functioning
- **Check Tool State**: Verify tool is not already picked up
- **Check Deck**: Ensure the deck is clear of obstructions

### Dispense Operation Fails

If `dispense_to_well()` returns `False`:

- **Check Well ID**: Verify the well ID exists in your deck configuration
- **Check Dispenser**: Ensure the dispenser has available pistons
- **Check Scale**: Verify the scale is responding to commands

## Advanced Features

### Using Tamping

For more control over powder compression, you can enable tamping before piston insertion:

```python
# Enable tamping in dispense operation
success = manager.dispense_to_well(
    well_id="0",
    target_weight=50.0,
    use_tamping=True  # Compresses powder before inserting piston
)
```

See the [Manipulator API](../api/manipulator.md#tamping-operations) for more details on tamping.

## Next Steps

Now that you have a working script:

- Learn about [system architecture](../concepts/architecture.md)
- Explore [how-to guides](../how-to/run-new-data.md) for specific tasks
- Review the [JubileeManager API](../api/jubilee-manager.md) reference
- Understand the [state machine](../api/motion-platform.md) for advanced control

## Tips

!!! tip "Use Try-Finally"
    Always use `try-finally` blocks to ensure `disconnect()` is called even if an error occurs.

!!! tip "Check Return Values"
    Most JubileeManager methods return `True/False` to indicate success. Always check these values.

!!! tip "Start Simple"
    Begin with simple operations like reading the scale before attempting complex multi-step operations.

!!! warning "Hardware Safety"
    Always monitor the first run of any new script. Be ready to press the emergency stop if needed. Use a lower feedrate so collisions can be stopped before they damage the system.

