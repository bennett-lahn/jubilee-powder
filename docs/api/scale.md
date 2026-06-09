# Scale

The `Scale` class provides a serial interface to A&D precision balances (FX/FZ series) for weight measurements in the Jubilee powder dispensing workflow.

=== "Operator Guide"

    !!! warning "Prefer JubileeManager"
        Most production code should call `JubileeManager.get_weight_stable()` or `get_weight_unstable()` rather than using `Scale` directly. Use this class when integrating standalone scale tests or debugging serial communication.

    ## Overview

    The Scale class:

    - Connects to the balance via USB serial
    - Reads stable and unstable weight measurements
    - Handles taring and low-level A&D protocol commands
    - Serializes concurrent access with an internal command lock

    ## Usage Examples

    ### Basic Connection and Reading

    ```python
    from src.Scale import Scale

    scale = Scale(port="/dev/ttyUSB0")
    scale.connect()

    if scale.is_connected:
        weight = scale.get_weight(stable=True)
        print(f"Weight: {weight}g")
        scale.disconnect()
    ```

    ### Stable vs Unstable Readings

    ```python
    stable_weight = scale.get_weight(stable=True)
    print(f"Stable: {stable_weight}g")

    unstable_weight = scale.get_weight(stable=False)
    print(f"Unstable: {unstable_weight}g")
    ```

    | Mode | When to use |
    |------|-------------|
    | **Stable** (`stable=True`) | Recorded measurements and dispensing decisions |
    | **Unstable** (`stable=False`) | Live monitoring, progress display, telemetry |

    ### Taring the Scale

    ```python
    scale.tare()
    weight = scale.get_weight(stable=True)
    print(f"Object weight: {weight}g")
    ```

    ## Integration with JubileeManager

    ```python
    from src.JubileeManager import JubileeManager

    manager = JubileeManager(
        num_piston_dispensers=2,
        num_pistons_per_dispenser=10,
    )
    manager.connect(scale_port="/dev/ttyUSB0")

    weight = manager.get_weight_stable()
    print(f"Weight: {weight}g")

    weight = manager.get_weight_unstable()
    print(f"Weight: {weight}g")
    ```

    ## Weight Monitoring

    ### Continuous Monitoring

    ```python
    import time

    def monitor_weight(scale, duration=10):
        """Monitor weight for specified duration."""
        start_time = time.time()
        while time.time() - start_time < duration:
            weight = scale.get_weight(stable=False)
            print(f"Weight: {weight:6.2f}g", end="\r")
            time.sleep(0.1)
        print()

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
        tolerance = 0.01

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
    ```

    ## Configuration

    ### Software (`system_config.json`)

    The serial port is configured under `machine`:

    ```json
    {
      "machine": {
        "scale_port": "/dev/ttyUSB0"
      }
    }
    ```

    Baud rate, timeout, and parity are passed to the `Scale` constructor (defaults: `baudrate=9600`, `timeout=10`). They must match the scale's communication settings.

    ### A&D Scale Setup (FX-120i and FX/FZ Series)

    The Jubilee Powder system targets A&D precision balances, particularly the **FX-120i**. Compatible FX/FZ series scales should work with the settings below.

    #### Communication Settings

    | Setting | Value | Notes |
    |---------|-------|-------|
    | **Baud Rate** | 9600 (typical) | Must match `Scale(baudrate=...)` |
    | **Data Bits** | 8 | Standard |
    | **Parity** | None | Default in `Scale.__init__` |
    | **Stop Bits** | 1 | Standard |
    | **Terminator** | CRLF | Required for A&D protocol |

    #### Scale Behavior Settings

    | Setting | Value | Description |
    |---------|-------|-------------|
    | **Stability Bandwidth** | 1 | When weight is considered stable |
    | **Condition** | 1 (Medium Response) | Response speed vs stability |
    | **Time/Date Output** | No Output | Keeps data stream clean |
    | **Zero After Output** | 0 (Not Used) | Disables auto-zero after reading |
    | **AK Error Code** | 1 (Output) | Enables error-correcting communication |

    #### Data Format Settings

    | Setting | Value |
    |---------|-------|
    | **Data Format** | A&D Standard Format |

    ??? note "Menu configuration sequence"
        1. Access the scale configuration menu (see your model manual).
        2. Set communication parameters: baud 9600, 8 data bits, no parity, 1 stop bit, CRLF terminator.
        3. Set response characteristics: stability bandwidth 1, condition 1 (medium response).
        4. Set output: A&D standard format, no time/date, zero-after-output off, AK error code on.
        5. Save, exit, and power-cycle the scale.

    #### Verifying Configuration

    ```python
    from src.Scale import Scale

    scale = Scale(port="/dev/ttyUSB0", baudrate=9600, timeout=10)

    try:
        scale.connect()
        print("Scale connected successfully")
        weight = scale.get_weight(stable=True)
        print(f"Weight reading: {weight}g")
        scale.disconnect()
    except Exception as e:
        print(f"Connection failed - check settings and port: {e}")
    ```

    ### Finding the Serial Port

    === "Linux"
        ```bash
        ls -l /dev/ttyUSB*
        ls -l /dev/ttyACM*
        dmesg | grep tty
        ```

    === "Windows"
        ```powershell
        Get-WmiObject Win32_SerialPort | Select-Object Name, DeviceID
        ```

    === "macOS"
        ```bash
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
    ```

    Common causes: wrong port, port in use, insufficient permissions, hardware disconnected.

    ### Reading Failures

    ```python
    try:
        weight = scale.get_weight(stable=True)
        print(f"Weight: {weight}g")
    except Exception as e:
        print(f"Error reading scale: {e}")
    ```

    ### Handling Disconnection

    ```python
    def safe_read_weight(scale):
        if not scale.is_connected:
            return None
        try:
            return scale.get_weight(stable=True)
        except Exception as e:
            print(f"Error reading weight: {e}")
            return None
    ```

    ## Advanced Usage

    ??? example "Calibration with known weight"
        ```python
        def calibrate_scale(scale, known_weight):
            print("Remove all items from scale, then press Enter")
            input()
            scale.tare()
            print(f"Place {known_weight}g calibration weight on scale, then press Enter")
            input()
            measured = scale.get_weight(stable=True)
            error = measured - known_weight
            print(f"Measured: {measured}g  Expected: {known_weight}g  Error: {error}g")
        ```

    ??? example "CSV data logging"
        ```python
        import csv
        import time
        from datetime import datetime

        def log_weight_data(scale, output_file, duration=60, interval=1.0):
            with open(output_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Weight (g)", "Stable"])
                start_time = time.time()
                while time.time() - start_time < duration:
                    timestamp = datetime.now().isoformat()
                    writer.writerow([timestamp, scale.get_weight(stable=False), "No"])
                    writer.writerow([timestamp, scale.get_weight(stable=True), "Yes"])
                    time.sleep(interval)
        ```

    ## Troubleshooting

    | Symptom | Likely cause | Fix |
    |---------|--------------|-----|
    | Scale not responding | Wrong port or baud | Verify `machine.scale_port` and scale menu settings |
    | Permission denied (Linux) | User not in `dialout` | `sudo usermod -a -G dialout $USER`, re-login |
    | Readings always unstable | Vibration or bandwidth | Increase stability bandwidth; ground the scale |
    | Incorrect values | Wrong data format | Set A&D Standard Format on the scale |
    | Timeout errors | Busy scale or E02 | Wait and retry; check for concurrent access |

    !!! tip "Linux serial permissions"
        Add your user to the `dialout` group or create a udev rule granting access to the scale's USB vendor ID.

    ## Best Practices

    - Tare before each measurement when the container changes.
    - Use `get_weight(stable=True)` for recorded values; `stable=False` only for live display.
    - Check `is_connected` before reading.
    - Always call `disconnect()` in a `finally` block.

=== "API Reference"

    ## Class Reference

    ::: src.Scale.Scale
        options:
          members: true
          show_root_heading: true
          show_source: false
          filters:
            - "!^_[^_]"

    ## ScaleError Codes

    The `ScaleError` enum maps A&D `EC,<code>` responses. See the generated reference above for `ScaleError` members and descriptions.

---

## See Also

- [JubileeManager](jubilee-manager.md) - High-level scale operations
- [Configuration Guide](../how-to/configuration.md) - Setting up scale port
- [Results Interpretation](../how-to/results.md) - Analyzing weight data
