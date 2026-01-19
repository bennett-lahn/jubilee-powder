# Jubilee Automation GUI

Modern touchscreen interface for the Jubilee powder dispensing automation system.

## Architecture

This GUI follows an **MVVM-inspired architecture** for maintainability and testability:

- **Model**: `JubileeManager` (src/JubileeManager.py) - Hardware operations and state
- **View**: `jubilee_gui.py` - User interface and interaction
- **ViewModel**: `jubilee_view_model.py` - Coordination and business logic

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture documentation.

## Files

### Core Files
- `jubilee_gui.py` - Main GUI application (Kivy-based)
- `jubilee_view_model.py` - ViewModel coordinator between GUI and hardware
- `requirements.txt` - Python dependencies

### Documentation
- `ARCHITECTURE.md` - Detailed architecture documentation
- `example_viewmodel_usage.py` - Example usage of ViewModel without GUI
- `README.md` - This file

## Features

### Hardware Configuration
- Configure number of piston dispensers
- Set pistons per dispenser
- Shows total pistons available
- Configuration can only be changed when disconnected

### Connection Management
- Connect to Jubilee machine and scale
- Automatic homing and initialization
- Real-time connection status display
- Background weight monitoring

### Job Management
- Visual well selection (3x3 grid)
- Set individual target weights per well
- Pre-job safety checklist
- Real-time progress tracking
- Job pause/stop capability

### Progress Monitoring
- Live weight display from scale
- Job progress with completion percentage
- Current well being processed
- Status messages for all operations

### Error Handling
- User-friendly error messages
- Graceful failure handling
- Hardware validation before operations

## Usage

### Prerequisites

Install required packages:
```bash
pip install -r requirements.txt
```

### Running the GUI

From the project root:
```bash
python gui/jubilee_gui.py
```

Or if you have a startup script:
```bash
./src/start_gui.sh  # Linux/Mac
```

### Hardware Configuration

1. Click **Hardware Config** button (only available when disconnected)
2. Enter:
   - Number of Dispensers (e.g., 2)
   - Pistons per Dispenser (e.g., 10)
3. View total pistons available
4. Click **Apply**

### Running a Dispensing Job

1. **Configure Hardware** (if needed)
   - Click "Hardware Config"
   - Set dispenser and piston counts
   - Click "Apply"

2. **Connect to System**
   - Application auto-connects on startup
   - Wait for "Connected" status
   - Scale should show "Connected"

3. **Select Wells**
   - Click wells on the 3x3 grid to select (green = selected)
   - Click again to deselect

4. **Set Target Weights**
   - Click "Set Weights" button
   - Enter target weight (in grams) for each selected well
   - Click "Apply"

5. **Start Job**
   - Click "Start Job" button
   - Complete the pre-job safety checklist
   - Click "Start Job" in checklist dialog
   - Progress dialog will show real-time progress

6. **Monitor Progress**
   - Watch current well being processed
   - See completion percentage
   - Live weight updates during dispensing
   - Option to stop job if needed

### Stopping a Job

- Click "Stop Job" in progress dialog or main screen
- Job will stop after current well completes
- Partially filled wells will remain in their current state

### Disconnecting

- Application automatically disconnects when closed
- Manual disconnect available through app shutdown

## Architecture Benefits

### For Users
- Intuitive, modern interface
- Clear feedback on all operations
- Safe operation with validation
- Easy hardware configuration

### For Developers
- Clear separation of concerns
- Testable ViewModel without GUI
- Easy to add new features
- Hardware code unchanged (stable)

## Extending the GUI

### Adding a New Button/Operation

1. **Add button to KV string** (in `jubilee_gui.py`):
```python
CustomButton:
    text: 'My Operation'
    on_press: root.my_operation()
```

2. **Add method to MainScreen**:
```python
def my_operation(self):
    """Handle my operation"""
    self.view_model.my_operation()
```

3. **Add method to ViewModel** (in `jubilee_view_model.py`):
```python
def my_operation(self) -> bool:
    """Coordinate my operation"""
    if not self._connected:
        self._notify_error("Not connected")
        return False
    
    # Call JubileeManager method
    result = self._jubilee_manager.some_operation()
    self._notify_status("Operation complete")
    return result
```

### Adding a New Dialog

1. **Add KV definition** (in KV string in `jubilee_gui.py`)
2. **Create Popup class** (in `jubilee_gui.py`)
3. **Add method to show dialog** (in MainScreen)

See `HardwareConfigDialog` as an example.

## Testing Without Hardware

The ViewModel can be used independently for testing:

```python
from jubilee_view_model import JubileeViewModel, DispensingJob

# Create ViewModel with mock callbacks
vm = JubileeViewModel(
    on_status_changed=lambda s: print(f"Status: {s}"),
    on_error=lambda e: print(f"Error: {e}")
)

# Configure
vm.set_hardware_config(num_dispensers=2, pistons_per_dispenser=10)

# Would connect to real hardware:
# vm.connect()
```

See `example_viewmodel_usage.py` for more examples.

## Troubleshooting

### GUI won't start
- Check that all requirements are installed: `pip install -r requirements.txt`
- Verify Python version is 3.8 or higher
- Check for import errors in terminal output

### Cannot change hardware config
- Hardware config can only be changed when **disconnected**
- Restart application or disconnect first

### Connection fails
- Verify Jubilee machine IP address in config file
- Check scale is connected to correct serial port
- Ensure hardware is powered on and accessible
- Check network connection to Jubilee

### Job fails to start
- Ensure hardware is connected (green "Connected" status)
- Verify wells are selected (green)
- Verify target weights are set
- Check that enough pistons are available for job

### Progress dialog doesn't update
- Progress updates happen between wells
- Check status message for current operation
- Long operations (filling) show as "Processing {well}"

### Scale weight shows 0.0g
- Check scale connection status
- Verify scale cable is connected
- Check scale port in configuration
- Try reconnecting to system

## Development

### Code Style
- Follow PEP 8 for Python code
- Use type hints for function parameters and returns
- Document public methods with docstrings
- Keep methods focused and small

### Adding Features
1. Consider which layer (View/ViewModel/Model) is appropriate
2. Update ViewModel first (if needed)
3. Update GUI to expose feature
4. Test with and without hardware
5. Update documentation

### Testing
- Test ViewModel independently (see `example_viewmodel_usage.py`)
- Test GUI with mock ViewModel for UI testing
- Test full integration with hardware

## Dependencies

Main dependencies (see `requirements.txt` for full list):
- **Kivy** - GUI framework
- **science-jubilee** - Jubilee machine control
- **threading** - Background operations
- **dataclasses** - Data structures

## License

[Your license here]

## Contact

[Your contact information here]
