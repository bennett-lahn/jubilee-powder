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

!!! note
    The `connect()` method will automatically:
    
    - Connect to the Jubilee machine
    - Connect to the scale
    - Initialize the state machine
    - Home all axes
    - Pick up the manipulator tool
    - Home the manipulator axis

### Step 4: Read Scale Weight

```python
# Get current weight from scale
weight = manager.get_weight_stable()
print(f"Current weight: {weight}g")
```

### Step 5: Perform Operations

```python
# Dispense to a well with target weight
success = manager.dispense_to_well(
    well_id="A1",           # Well identifier from your deck config
    target_weight=50.0      # Target weight in grams
)

if success:
    print("Dispense operation completed successfully!")
else:
    print("Dispense operation failed!")
```

### Step 6: Clean Up

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
            well_id="A1",
            target_weight=50.0
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
   - Homes all machine axes (X, Y, Z, U)
   - Picks up the manipulator tool
   - Homes the manipulator's vertical axis (V)

2. **Operation Phase**:
   - Moves to the specified well location
   - Picks up the mold from the well
   - Moves to the scale
   - Places mold on scale
   - Fills powder to target weight
   - Picks up mold from scale
   - Gets a piston from dispenser
   - Returns mold to well

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
- **Check Tool State**: Verify no tool is already picked up
- **Check Deck Clear**: Ensure the deck is clear of obstructions

### Dispense Operation Fails

If `dispense_to_well()` returns `False`:

- **Check Well ID**: Verify the well ID exists in your deck configuration
- **Check Dispenser**: Ensure the dispenser has available pistons
- **Check Scale**: Verify the scale is responding

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
    Always monitor the first run of any new script. Be ready to press the emergency stop if needed.

