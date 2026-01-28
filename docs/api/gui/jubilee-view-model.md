# JubileeViewModel API Reference

The `JubileeViewModel` class coordinates between the GUI and JubileeManager, following an MVVM-inspired architecture pattern.

## Overview

`JubileeViewModel` serves as the coordination layer that:

- Manages hardware configuration before connection
- Drives the JubileeManager to execute operations
- Executes multi-well dispensing jobs systematically
- Provides callbacks to update the GUI on progress
- Handles errors and provides user-friendly feedback

## Architecture Role

```
GUI (View) → ViewModel (Coordinator) → JubileeManager (Model) → Hardware
```

The ViewModel:

- **Receives** requests from the GUI
- **Coordinates** operations through JubileeManager
- **Notifies** GUI of changes via callbacks

## Class Reference

::: gui.jubilee_view_model.JubileeViewModel
    options:
      members:
        - __init__
        - connected
        - job_running
        - num_dispensers
        - pistons_per_dispenser
        - set_hardware_config
        - connect
        - disconnect
        - get_current_weight
        - start_job
        - stop_job
        - get_dispenser_status
        - update_dispenser_pistons
      show_root_heading: true
      show_source: false

## DispensingJob

::: gui.jubilee_view_model.DispensingJob
    options:
      show_root_heading: true
      show_source: false

## Usage Examples

### Basic Setup

```python
from gui.jubilee_view_model import JubileeViewModel, DispensingJob

# Define callbacks for GUI updates
def on_status(status: str):
    print(f"Status: {status}")

def on_progress(completed: int, total: int, current_well: str):
    print(f"Progress: {completed}/{total} - {current_well}")

# Create ViewModel
view_model = JubileeViewModel(
    on_status_changed=on_status,
    on_job_progress=on_progress
)

# Configure hardware before connecting
view_model.set_hardware_config(
    num_dispensers=2,
    pistons_per_dispenser=10
)
```

### Connecting to Hardware

```python
# Connect (this will create JubileeManager with configured settings)
if view_model.connect(machine_address="192.168.1.100"):
    print("Connected successfully!")
    print(f"Dispensers: {view_model.num_dispensers}")
    print(f"Pistons per dispenser: {view_model.pistons_per_dispenser}")
else:
    print("Connection failed")
```

### Running a Dispensing Job

```python
# Define wells to fill
jobs = [
    DispensingJob(well_id="0", target_weight=50.0),
    DispensingJob(well_id="1", target_weight=45.0),
    DispensingJob(well_id="2", target_weight=52.0),
]

# Start job (runs in background thread)
if view_model.start_job(jobs):
    print("Job started")
    
    # Job runs asynchronously
    # Progress updates come via on_job_progress callback
    # Completion notification via on_job_completed callback
```

### Monitoring Progress

```python
# Callbacks provide real-time updates
def on_connection_changed(connected: bool):
    if connected:
        print("Hardware connected")
    else:
        print("Hardware disconnected")

def on_weight_changed(weight: float):
    print(f"Current weight: {weight:.3f}g")

def on_job_progress(completed: int, total: int, current_well: str):
    print(f"Completed {completed}/{total} wells")
    print(f"Currently processing: {current_well}")

def on_job_completed():
    print("Job finished successfully!")

def on_error(error_msg: str):
    print(f"Error: {error_msg}")

# Create ViewModel with all callbacks
view_model = JubileeViewModel(
    on_connection_changed=on_connection_changed,
    on_weight_changed=on_weight_changed,
    on_status_changed=lambda s: print(s),
    on_job_progress=on_job_progress,
    on_job_completed=on_job_completed,
    on_error=on_error
)
```

### Checking Dispenser Status

```python
# Get status of all dispensers
status = view_model.get_dispenser_status()

for dispenser in status:
    print(f"Dispenser {dispenser['index']}: "
          f"{dispenser['pistons_remaining']} pistons")
```

### Updating Piston Counts

```python
# User manually reloaded dispenser 0 with 20 pistons
success = view_model.update_dispenser_pistons(
    dispenser_index=0,
    num_pistons=20
)

if success:
    print("Dispenser piston count updated")
```

### Stopping a Job

```python
# User wants to stop the current job
view_model.stop_job()

# Job will stop after current well completes
# Status update via on_status_changed callback
```

## Callback System

The ViewModel uses callbacks to notify the GUI of changes. This allows the GUI to remain responsive while operations run in background threads.

### Available Callbacks

| Callback | Parameters | When Called |
|----------|-----------|-------------|
| `on_connection_changed` | `connected: bool` | Connection state changes |
| `on_weight_changed` | `weight: float` | Scale weight updates (500ms) |
| `on_status_changed` | `status: str` | Status message changes |
| `on_job_progress` | `completed: int, total: int, current_well: str` | Job progress updates |
| `on_job_completed` | None | Job finishes successfully |
| `on_error` | `error_msg: str` | Error occurs |

### Thread Safety

All callbacks are called from background threads. GUI frameworks typically require updates to happen on the main thread. Use your framework's thread-safe update mechanism:

**Kivy Example:**
```python
from kivy.clock import Clock

def on_status_changed(status: str):
    # Schedule update on main thread
    def update(dt):
        self.status_label.text = status
    Clock.schedule_once(update, 0)
```

## Design Notes

### Hardware Configuration

Hardware configuration (dispensers, pistons) is set in the ViewModel **before** connection. When `connect()` is called, the ViewModel creates a JubileeManager with these settings. The actual hardware state is then stored in the JubileeManager.

### Job Execution

Jobs are executed systematically in a background thread:

1. Validate piston availability
2. For each well in order:
   - Call `JubileeManager.dispense_to_well()`
   - Update progress via callback
   - Check for stop flag
3. Notify completion via callback

### Error Handling

Errors are caught and reported via the `on_error` callback. Jobs stop on first error to prevent cascading failures.

## See Also

- [JubileeManager](../jubilee-manager.md) - Hardware operations layer
- [GUI Application](jubilee-gui.md) - Full GUI application
- [Using the GUI](../../how-to/using-gui.md) - GUI user guide
