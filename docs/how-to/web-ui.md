# Using the Jubilee Web UI

This guide explains how to use the Jubilee's web interface

## Overview

There are two web interfaces available:

1. **Duet Web Control** (DWC): The built-in Jubilee controller interface
2. **Jubilee GUI**: Custom Python GUI application for high-level operations. See [GUI User Guide](using-gui.md) for more details.

## Duet Web Control (DWC)

### Accessing DWC

1. Open a web browser
2. Navigate to your Jubilee's IP address: `http://192.168.1.100` (use your configured IP)
3. The Duet Web Control interface will load

### DWC Interface Overview

The DWC provides low-level control of the Jubilee:

- **Machine Control**: Manual jog controls for all axes
- **Console**: Send G-code commands directly
- **Status**: View current positions, temperatures, and states
- **Files**: Upload and manage G-code files
- **Macros**: Run predefined macro files

### Common DWC Tasks

#### Manual Movement

1. Click the **Machine Control** tab
2. Select the axis to move (X, Y, Z, U, V)
3. Choose movement distance (0.1mm, 1mm, 10mm, 100mm)
4. Click directional buttons to move

!!! warning "Safety"
    Manual movements in DWC bypass the state machine validation. Be careful not to cause collisions. Misclicks can be catastrophic. 

#### Homing Axes

1. In **Machine Control**, find the "Home" section
2. Click **Home All** to home all axes, or
3. Click individual axis buttons (Home X, Home Y, etc.)

#### Running Macros

1. Click the **Macros** tab (or **Job** tab in some versions)
2. Browse available macros
3. Click a macro name to execute it

**Useful macros**:
- `homeall.g`: Home all axes
- `tool_lock.g`: Lock the current tool
- `tool_unlock.g`: Unlock the current tool

#### Sending G-code Commands

1. Click the **Console** tab
2. Type G-code in the input box at the bottom
3. Press Enter to send

**Common G-code commands**:
```gcode
G28          ; Home all axes
G90          ; Absolute positioning
G91          ; Relative positioning
G1 X100 Y50 F5000  ; Move to X=100, Y=50 at 5000 mm/min
M114         ; Report current position
M999         ; Reset controller after emergency stop
```

#### Monitoring Status

The **Status** section shows:
- Current X, Y, Z, U, V positions
- Active tool (T0, T1, etc.)
- Machine state (idle, processing, paused)
- Temperature readings (if applicable)

### When to Use DWC

Use Duet Web Control for:

- Manual troubleshooting
- Testing individual movements
- Verifying positions
- Emergency control
- Low-level debugging

**Do not use for:**

- Automated operations (use Python API instead)
- Complex multi-step procedures (use JubileeManager)
- Production workflows (use custom scripts)

## Advanced Features

### Creating Custom Macros (DWC)

You can create custom G-code macros for repetitive tasks:

1. In DWC, go to **System** tab
2. Navigate to `/sys/macros/`
3. Create new file (e.g., `my_custom_move.g`)
4. Write G-code:

```gcode
; My Custom Move Macro
G28                      ; Home all
G1 X100 Y100 Z50 F5000  ; Move to position
M400                     ; Wait for moves to complete
M291 P"Movement complete" S1  ; Show message
```

5. Save file
6. Macro appears in Macros list

### Monitoring from Multiple Devices

You can access DWC from multiple browsers simultaneously:

- One person monitors in lab
- Another controls remotely
- All see the same state

!!! warning "Coordination Required"
    If multiple people send commands, they may conflict. Coordinate who is in control.

### Integrating with External Tools

The API can be controlled programmatically:

```python
# External control example
from src.JubileeManager import JubileeManager

# Create manager (could be controlled by another application)
manager = JubileeManager()
if manager.connect():
    # Perform operations
    pass
```

## Next Steps

- [Configure your system](configuration.md) for custom operations
- [Run automated operations](run-new-data.md) using Python scripts
- [Interpret results](results.md) from dispense operations
- Review [JubileeManager API](../api/jubilee-manager.md) for programmatic control

