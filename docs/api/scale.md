# Scale API Reference

The `Scale` class provides an interface to precision balance hardware for weight measurements.

## Overview

The Scale class:

- Connects to balance via USB serial
- Reads weight measurements
- Supports stable and unstable readings
- Handles taring and calibration

## Class Reference

::: src.Scale.Scale
    options:
      members: true
      show_root_heading: true
      show_source: false
      filters:
        - "!^_[^_]"  # Hide private methods (except __init__)

## Usage Examples

### Basic Connection and Reading

```python
from src.Scale import Scale

# Create and connect to scale
scale = Scale(port="/dev/ttyUSB0")
scale.connect()

if scale.is_connected:
    # Get stable weight reading
    weight = scale.get_weight(stable=True)
    print(f"Weight: {weight}g")
    
    # Disconnect when done
    scale.disconnect()
```

### Stable vs Unstable Readings

```python
# Stable reading (waits for weight to stabilize)
stable_weight = scale.get_weight(stable=True)
print(f"Stable: {stable_weight}g")

# Unstable reading (immediate, may be changing)
unstable_weight = scale.get_weight(stable=False)
print(f"Unstable: {unstable_weight}g")
```

**When to use each**:

- **Stable**: For measurements you'll record or use for decisions
- **Unstable**: For real-time monitoring or progress display

### Taring the Scale

```python
# Tare (zero) the scale
scale.tare()

# Now readings are relative to current weight
# Place object on scale
weight = scale.get_weight(stable=True)
print(f"Object weight: {weight}g")
```

## Integration with JubileeManager

The scale is typically used through JubileeManager:

```python
from src.JubileeManager import JubileeManager

manager = JubileeManager()
manager.connect(scale_port="/dev/ttyUSB0")

# Get stable weight
weight = manager.get_weight_stable()
print(f"Weight: {weight}g")

# Get unstable weight (faster)
weight = manager.get_weight_unstable()
print(f"Weight: {weight}g")
```

## Weight Monitoring

### Continuous Monitoring

```python
import time

def monitor_weight(scale, duration=10):
    """Monitor weight for specified duration."""
    print("Monitoring weight...")
    start_time = time.time()
    
    while time.time() - start_time < duration:
        weight = scale.get_weight(stable=False)
        print(f"Weight: {weight:6.2f}g", end='\r')
        time.sleep(0.1)
    
    print()  # New line

# Usage
monitor_weight(scale, duration=30)
```

### Waiting for Stability

```python
def wait_for_stable(scale, timeout=30):
    """Wait for weight to stabilize."""
    import time
    
    start_time = time.time()
    previous_weight = None
    stable_count = 0
    required_stable_readings = 5
    tolerance = 0.01  # grams
    
    while time.time() - start_time < timeout:
        weight = scale.get_weight(stable=False)
        
        if previous_weight is not None:
            if abs(weight - previous_weight) < tolerance:
                stable_count += 1
                if stable_count >= required_stable_readings:
                    return weight, True
            else:
                stable_count = 0
        
        previous_weight = weight
        time.sleep(0.2)
    
    return previous_weight, False

# Usage
weight, is_stable = wait_for_stable(scale)
if is_stable:
    print(f"Stable weight: {weight}g")
else:
    print("Timeout waiting for stability")
```

## Configuration

### Serial Port Configuration

The scale port is configured in `system_config.json`:

```json
{
  "system": {
    "scale_port": "/dev/ttyUSB0",
    "scale_baud_rate": 9600,
    "scale_timeout": 2.0
  }
}
```

### Finding the Serial Port

**Linux**:
```bash
# List USB serial devices
ls -l /dev/ttyUSB*
ls -l /dev/ttyACM*

# Check dmesg for recent connections
dmesg | grep tty
```

**Windows**:
```powershell
# List COM ports
Get-WmiObject Win32_SerialPort | Select-Object Name, DeviceID
```

**macOS**:
```bash
# List serial devices
ls -l /dev/tty.*
ls -l /dev/cu.*
```

## Error Handling

### Connection Failures

```python
from src.Scale import Scale

scale = Scale(port="/dev/ttyUSB0")

try:
    scale.connect()
    if not scale.is_connected:
        raise ConnectionError("Scale connection failed")
except Exception as e:
    print(f"Error connecting to scale: {e}")
    # Common causes:
    # - Wrong port
    # - Port already in use
    # - Insufficient permissions
    # - Hardware not connected
```

### Reading Failures

```python
try:
    weight = scale.get_weight(stable=True)
    if weight is None:
        print("Failed to read weight")
except Exception as e:
    print(f"Error reading scale: {e}")
    # Common causes:
    # - Communication timeout
    # - Scale not responding
    # - Invalid data from scale
```

### Handling Disconnection

```python
def safe_read_weight(scale):
    """Safely read weight with error handling."""
    if not scale.is_connected:
        print("Scale not connected")
        return None
    
    try:
        weight = scale.get_weight(stable=True)
        return weight
    except Exception as e:
        print(f"Error reading weight: {e}")
        return None
```

## Advanced Usage

### Calibration

```python
def calibrate_scale(scale, known_weight):
    """
    Calibrate scale using a known reference weight.
    
    Args:
        scale: Connected Scale instance
        known_weight: Weight of calibration standard in grams
    """
    print("Remove all items from scale, then press Enter")
    input()
    
    # Tare the empty scale
    scale.tare()
    print("Scale tared")
    
    print(f"Place {known_weight}g calibration weight on scale, then press Enter")
    input()
    
    # Read calibration weight
    measured = scale.get_weight(stable=True)
    print(f"Measured: {measured}g")
    print(f"Expected: {known_weight}g")
    print(f"Error: {measured - known_weight}g ({((measured - known_weight) / known_weight) * 100:.2f}%)")
    
    if abs(measured - known_weight) > 0.1:
        print("Warning: Calibration error exceeds 0.1g")
```

### Data Logging

```python
import csv
import time
from datetime import datetime

def log_weight_data(scale, output_file, duration=60, interval=1.0):
    """
    Log weight data to CSV file.
    
    Args:
        scale: Connected Scale instance
        output_file: Path to output CSV file
        duration: How long to log in seconds
        interval: Time between readings in seconds
    """
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Timestamp', 'Weight (g)', 'Stable'])
        
        start_time = time.time()
        while time.time() - start_time < duration:
            timestamp = datetime.now().isoformat()
            
            # Get both stable and unstable readings
            unstable = scale.get_weight(stable=False)
            stable = scale.get_weight(stable=True)
            
            writer.writerow([timestamp, unstable, 'No'])
            writer.writerow([timestamp, stable, 'Yes'])
            
            time.sleep(interval)
    
    print(f"Data logged to {output_file}")

# Usage
log_weight_data(scale, "weight_log.csv", duration=300, interval=5.0)
```

### Multi-Scale Setup

For systems with multiple scales:

```python
class ScaleManager:
    """Manage multiple scales."""
    
    def __init__(self, ports):
        """
        Initialize multiple scales.
        
        Args:
            ports: List of serial port paths
        """
        self.scales = []
        for i, port in enumerate(ports):
            scale = Scale(port=port)
            scale.connect()
            if scale.is_connected:
                self.scales.append((i, scale))
                print(f"Scale {i} connected on {port}")
            else:
                print(f"Failed to connect scale {i} on {port}")
    
    def read_all(self, stable=True):
        """Read all scales."""
        readings = {}
        for index, scale in self.scales:
            readings[index] = scale.get_weight(stable=stable)
        return readings
    
    def disconnect_all(self):
        """Disconnect all scales."""
        for index, scale in self.scales:
            scale.disconnect()

# Usage
manager = ScaleManager(["/dev/ttyUSB0", "/dev/ttyUSB1"])
readings = manager.read_all(stable=True)
print(f"Scale readings: {readings}")
manager.disconnect_all()
```

## Troubleshooting

### Scale Not Responding

**Symptoms**:
- `is_connected` is False
- Timeout errors when reading

**Solutions**:
1. Verify physical connection (USB cable plugged in)
2. Check that port is correct (`ls /dev/ttyUSB*`)
3. Verify user has permission to access serial port:
   ```bash
   sudo usermod -a -G dialout $USER
   # Log out and log back in
   ```
4. Try different USB port
5. Check that no other program is using the scale
6. Verify scale is powered on

### Incorrect Readings

**Symptoms**:
- Readings don't match display on scale
- Readings are always zero
- Readings are unstable

**Solutions**:
1. Tare the scale: `scale.tare()`
2. Calibrate using known weight
3. Check for environmental factors:
   - Drafts/air currents
   - Vibrations
   - Temperature changes
4. Verify scale settings (units, precision)
5. Check baud rate matches scale configuration

### Permission Denied

**Linux symptom**: `PermissionError: [Errno 13] Permission denied: '/dev/ttyUSB0'`

**Solutions**:
```bash
# Add user to dialout group
sudo usermod -a -G dialout $USER

# Or use udev rule
sudo nano /etc/udev/rules.d/50-scale.rules
# Add: SUBSYSTEM=="tty", ATTRS{idVendor}=="XXXX", MODE="0666"

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Best Practices

### Always Tare Before Measurements

```python
# GOOD
scale.tare()
# ... place object ...
weight = scale.get_weight(stable=True)

# BAD
weight = scale.get_weight(stable=True)  # May include previous object's weight
```

### Use Stable Readings for Decisions

```python
# GOOD - for recording data
final_weight = scale.get_weight(stable=True)
save_to_database(final_weight)

# BAD - for recording data
weight = scale.get_weight(stable=False)  # Might be changing!
save_to_database(weight)

# OK - for real-time monitoring
while filling:
    current = scale.get_weight(stable=False)
    print(f"Current: {current}g")
```

### Handle Connection State

```python
# GOOD
if scale.is_connected:
    weight = scale.get_weight(stable=True)
else:
    print("Scale not connected")

# BAD
weight = scale.get_weight(stable=True)  # Might fail if not connected
```

### Clean Up Resources

```python
# GOOD
scale = Scale(port="/dev/ttyUSB0")
try:
    scale.connect()
    # ... use scale ...
finally:
    scale.disconnect()

# BETTER - use context manager (if available)
with Scale(port="/dev/ttyUSB0") as scale:
    weight = scale.get_weight(stable=True)
```

## See Also

- [JubileeManager](jubilee-manager.md) - High-level scale operations
- [Configuration Guide](../how-to/configuration.md) - Setting up scale port
- [Results Interpretation](../how-to/results.md) - Analyzing weight data

