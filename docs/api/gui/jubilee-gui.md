# GUI Application API Reference

The Jubilee GUI provides a modern touchscreen interface for powder dispensing operations.

## Overview

The GUI application is built with Kivy and provides:

- Visual well selection (3x3 grid)
- Target weight configuration
- Real-time progress monitoring
- Hardware configuration interface
- Safety checklist before jobs
- Live scale weight display

## Architecture

The GUI follows an MVVM-inspired architecture:

```
MainScreen (View)
    ↓ method calls
JubileeViewModel (Coordinator)
    ↓ method calls
JubileeManager (Model)
    ↓
Hardware
```

## Main Components

### MainScreen

The primary screen containing:

- **Well Grid**: Grid of mold slots (0-17) for selection
- **Scale Display**: Live weight readings from the scale
- **Control Buttons**: Hardware config, set weights, start/stop job
- **Status Bar**: Current operation status

### Dialogs

#### HardwareConfigDialog

Configure hardware before connection:

- Number of dispensers
- Pistons per dispenser
- Real-time total calculation

#### WeightDialog

Set target weights for selected wells:

- Lists all selected wells
- Input fields for target weights (grams)
- Validates numeric input

#### ChecklistDialog

Pre-job safety checklist:

- Scale connected and stable
- Powder container filled
- Work area clear
- All items must be checked to proceed

#### ProgressDialog

Real-time job progress:

- Current well being processed
- Progress bar and percentage
- Completed/total wells count
- Stop button to cancel job

## Running the GUI

### From Command Line

```bash
cd jubilee-automation
python gui/jubilee_gui.py
```

### From Script

```python
from gui.jubilee_gui import JubileeGUIApp

if __name__ == '__main__':
    print("before")
    app = JubileeGUIApp()
    app.run()
    print("after")
```

## User Workflow

### 1. Configure Hardware (Optional)

If not using default configuration:

1. Click "Hardware Config" button
2. Enter number of dispensers and pistons
3. Click "Apply"

**Note**: Hardware config can only be changed when disconnected.

### 2. Connection

The application auto-connects on startup:

- Connects to Jubilee machine
- Connects to scale
- Homes all axes
- Picks up manipulator tool

Connection status shown in status bar and scale panel.

### 3. Select Wells

Click wells in the 3x3 grid to select/deselect:

- Green = Selected
- Gray = Not selected

Multiple wells can be selected.

### 4. Set Target Weights

1. Click "Set Weights" button
2. Enter target weight (grams) for each selected well
3. Click "Apply"

### 5. Start Job

1. Click "Start Job" button
2. Complete safety checklist
3. Click "Start Job" in checklist dialog
4. Monitor progress in real-time

### 6. Monitor Progress

During job execution:

- Progress dialog shows current well
- Progress bar updates after each well
- Status bar shows detailed status
- Live weight updates during filling

### 7. Stop Job (If Needed)

Click "Stop Job" button:

- Job will stop after current well completes
- Partial progress is saved

## GUI Features

### Real-Time Updates

Updates happen via ViewModel callbacks:

- **Weight**: Every 500ms
- **Status**: On every operation
- **Progress**: After each well completed

### Thread Safety

All hardware operations run in background threads to keep GUI responsive. Updates are scheduled on the main thread using Kivy's `Clock.schedule_once()`.

### Error Handling

Errors are displayed in popup dialogs with:

- Clear error message
- OK button to dismiss
- Red styling for visibility

### Visual Feedback

- **Connection Status**: Color-coded (connected/disconnected)
- **Well Selection**: Visual highlighting
- **Progress**: Percentage and bar
- **Status Messages**: Real-time updates

## Customization

### Modifying the GUI

The GUI uses Kivy's KV language for layout. To modify:

1. Edit the `KV` string in `jubilee_gui.py`
2. Modify layout, colors, sizes
3. Add new widgets or dialogs

### Adding New Buttons

To add a new operation button:

1. Add button to KV layout
2. Add method to `MainScreen` class
3. Call ViewModel method from button handler

Example:

```python
# In KV string:
CustomButton:
    text: 'My Operation'
    on_press: root.my_operation()

# In MainScreen class:
def my_operation(self):
    """Handle my operation"""
    self.view_model.my_operation()
```

### Custom Callbacks

The GUI implements six ViewModel callbacks:

```python
def _on_connection_changed(self, connected: bool):
    """Update connection status display"""
    
def _on_weight_changed(self, weight: float):
    """Update weight display"""
    
def _on_status_changed(self, status: str):
    """Update status bar"""
    
def _on_job_progress(self, completed: int, total: int, well: str):
    """Update progress dialog"""
    
def _on_job_completed(self):
    """Show completion dialog"""
    
def _on_error(self, error_msg: str):
    """Show error dialog"""
```

## Configuration

### Display Settings

Edit in KV string:

- Window size: Default fits touchscreen
- Colors: Material Design palette
- Fonts: Size adjustable via `dp()` units

### Hardware Settings

Edit before connection:

- Dispensers: Via Hardware Config dialog
- Machine IP: In `system_config.json`
- Scale Port: In code or config

## Troubleshooting

### GUI Won't Start

- Check Kivy installation: `pip install kivy`
- Verify Python version: 3.8+
- Check terminal for import errors

### Connection Fails

- Verify machine IP address
- Check scale serial port
- Ensure hardware is powered on
- Check network connectivity

### Job Fails to Start

- Verify hardware is connected
- Check enough pistons available
- Ensure wells are selected
- Verify target weights are set

### Progress Not Updating

- Progress updates between wells
- Long operations (filling) show as one step
- Check status message for details

### Cannot Change Hardware Config

- Config can only be changed when disconnected
- Restart application to reconfigure
- Or disconnect first

## Dependencies

Key dependencies:

- **Kivy**: GUI framework
- **JubileeViewModel**: Coordination layer
- **JubileeManager**: Hardware operations

See `gui/requirements.txt` for full list.

## See Also

- [JubileeViewModel](jubilee-view-model.md) - Coordination layer
- [JubileeManager](../jubilee-manager.md) - Hardware operations
- [Using the GUI](../../how-to/using-gui.md) - Detailed user guide
- [Architecture](../../concepts/architecture.md) - System architecture
