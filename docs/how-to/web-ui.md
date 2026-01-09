# Using the Jubilee Web UI

This guide explains how to use the Jubilee's web interface and the custom GUI application for controlling and monitoring the system.

## Overview

There are two web interfaces available:

1. **Duet Web Control** (DWC): The built-in Jubilee controller interface
2. **Jubilee GUI**: Custom Python GUI application for high-level operations

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
    Manual movements in DWC bypass the state machine validation. Be careful not to cause collisions.

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
- ✅ Manual troubleshooting
- ✅ Testing individual movements
- ✅ Verifying positions
- ✅ Emergency control
- ✅ Low-level debugging

**Do not use for**:
- ❌ Automated operations (use Python API instead)
- ❌ Complex multi-step procedures (use JubileeManager)
- ❌ Production workflows (use scripted automation)

## Jubilee GUI Application

### Starting the GUI

Option 1: Using the launch script
```bash
cd src/
./start_gui.sh
```

Option 2: Running directly
```bash
cd src/
python jubilee_gui.py
```

Option 3: From GUI directory
```bash
cd gui/
python jubilee_gui.py
```

### GUI Interface Overview

The custom GUI provides high-level control through the JubileeManager API.

#### Main Components

1. **Connection Panel**
   - IP address input
   - Scale port selection
   - Connect/Disconnect button
   - Connection status indicator

2. **Control Panel**
   - Quick action buttons
   - Dispense operation controls
   - Weight display

3. **Status Display**
   - Current position
   - Active tool
   - Payload state
   - Scale reading

4. **Log/Console**
   - Operation feedback
   - Error messages
   - Status updates

### Common GUI Tasks

#### Connecting to Hardware

1. Enter Jubilee IP address (e.g., `192.168.1.100`)
2. Select scale port from dropdown (e.g., `/dev/ttyUSB0`)
3. Click **Connect** button
4. Wait for initialization (homing, tool pickup, etc.)
5. Status indicator turns green when ready

#### Reading Scale Weight

1. Ensure connection is established
2. The weight display updates automatically
3. For stable reading, wait for indicator to show stable
4. Click **Tare** button to zero the scale

#### Dispensing to a Well

1. Select target well from dropdown (e.g., "A1")
2. Enter target weight in grams
3. Click **Dispense** button
4. Monitor progress in status display
5. Check results when operation completes

#### Manual Positioning

1. Select target position from dropdown
2. Click **Move To** button
3. System validates and executes movement
4. Status updates when movement completes

#### Emergency Stop

1. Click the **E-STOP** button in the GUI, or
2. Press the physical emergency stop on the Jubilee
3. System halts all movement immediately
4. Reconnect and rehome before continuing

### GUI Configuration

The GUI reads settings from the same configuration files as the Python API:

- `jubilee_api_config/system_config.json`
- `jubilee_api_config/motion_platform_positions.json`
- `jubilee_api_config/mold_labware.json`

To customize the GUI:

1. Edit configuration files as needed
2. Restart the GUI application
3. Changes take effect on next connection

## Web UI Best Practices

### Safety

!!! danger "Always Monitor First Run"
    Watch the Jubilee physically during the first run of any operation. Keep your hand near the emergency stop.

### DWC Best Practices

1. **Use relative movements** when testing: `G91` then `G1 X10` to move 10mm in X
2. **Start with small movements**: Test with 1mm increments before larger moves
3. **Check current position** before moving: `M114` shows current coordinates
4. **Home after errors**: If something goes wrong, home all axes before continuing

### GUI Best Practices

1. **Test connectivity** before starting operations
2. **Verify well positions** using manual positioning first
3. **Start with small batches**: Test 1-2 wells before running large batches
4. **Monitor logs**: Watch the log panel for errors or warnings
5. **Save configurations**: Export successful configurations for backup

## Troubleshooting

### Cannot Access DWC

**Symptoms**:
- Browser shows "Cannot connect" or timeout
- Address not reachable

**Solutions**:
1. Verify Jubilee is powered on
2. Check network connection
3. Ping the IP address: `ping 192.168.1.100`
4. Try accessing from different computer
5. Check firewall settings
6. Verify IP address is correct (check `system_config.json`)

### GUI Won't Start

**Symptoms**:
- Error when running `jubilee_gui.py`
- Import errors or missing modules

**Solutions**:
1. Ensure virtual environment is activated
2. Install dependencies: `pip install -r requirements.txt`
3. For GUI-specific deps: `pip install -r gui/requirements.txt`
4. Check Python version (3.8+ required)

### Connection Fails in GUI

**Symptoms**:
- "Failed to connect" message
- Connection button stays red

**Solutions**:
1. Verify IP address is correct
2. Check scale is connected (try `ls /dev/ttyUSB*`)
3. Ensure no other program is using the scale port
4. Check that Jubilee is responsive in DWC
5. Review error messages in log panel

### Movement Commands Don't Work

**Symptoms**:
- Buttons don't respond
- "Movement failed" errors

**Solutions**:
1. Ensure system is connected
2. Check that homing completed successfully
3. Verify tool is picked up if required
4. Check logs for validation errors
5. Ensure target positions are defined in config

### Scale Not Updating

**Symptoms**:
- Weight display shows zero or stale value
- "Scale not connected" warning

**Solutions**:
1. Check USB connection to scale
2. Verify correct port selected
3. Try different USB port
4. Check scale has power
5. Test scale connection manually: `python -c "from src.Scale import Scale; s = Scale(); s.connect(); print(s.get_weight())"`

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

The GUI and API can be controlled programmatically:

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

