# Jubilee Powder Documentation

Welcome to Jubilee Powder documentation. This system provides automated powder dispensing and hardness testing workflows on the Jubilee Motion Platform for precision laboratory tasks.

## What is Jubilee Powder?

Jubilee Powder is a Python-based system that enables programmatic control of the [Jubilee Motion Platform](https://github.com/machineagency/jubilee) for automated powder dispensing and hardness testing operations. It provides high-level APIs, a browser UI, and validated motion workflows for safe lab operation.

## Quick Navigation

=== "Operators"

    If you are looking to **use** the Jubilee system for laboratory work:

    - **Start here:** [Quick Start Guide](getting-started/quickstart.md)
    - **Safety and best practices:** [Best Practices](concepts/best-practices.md)
    - **Learn concepts:** [Architecture Overview](concepts/architecture.md)
    - **Follow recipes:** [How-To Guides](how-to/run-new-data.md)
    - **Use the Automation UI:** [Automation UI Guide](how-to/using-gui.md)
    - **Use the Web UI:** [Web Interface Guide](how-to/web-ui.md)
    - **Read LCD displays:** [LCD Display Reading Guide](how-to/reading-lcd-displays.md)

=== "Developers"

    If you are looking to **extend** or **modify** the system:

    - **Core API:** [JubileeManager Reference](api/jubilee-manager.md)
    - **State Machine:** [MotionPlatformStateMachine Reference](api/motion-platform.md)
    - **Frontend Store:** [Jubilee Store Reference](api/gui/jubilee-view-model.md)
    - **LCD Reader:** [HardnessTester Reference](api/hardness-tester.md)
    - **All APIs:** [Complete API Reference](api/jubilee-manager.md)

## What's Important?

### Automation UI (Recommended for Most Users)

The [Automation UI](how-to/using-gui.md) provides a touchscreen-friendly browser interface:

- Visual well selection and configuration
- Real-time progress monitoring
- Hardware configuration without code
- Built-in safety checklist
- Live weight display

!!! tip "Best choice for interactive operation"
    Use the Automation UI for day-to-day dispensing and hardness jobs, monitoring, and hardware setup without writing scripts.

### Python API: JubileeManager

The [`JubileeManager`](api/jubilee-manager.md) class is your main programming entry point:

- Safe, validated movements through an internal state machine
- High-level operations (dispense, weigh, move)
- Connection management for all hardware components
- Error handling and safety checks

!!! tip "Use for scripted automation"
    Choose JubileeManager when you need custom workflows, batch scripts, or integration with external tools.

### Frontend Store: Jubilee Store

The [`Jubilee Store`](api/gui/jubilee-view-model.md) coordinates browser state with the backend:

- MVVM-inspired architecture using Zustand
- Callback system for real-time updates
- Job execution management
- Thread-safe operations

!!! note "Frontend extension point"
    Use the Jubilee Store when customizing or extending the web frontend.

### Advanced Control: MotionPlatformStateMachine

The [`MotionPlatformStateMachine`](api/motion-platform.md) provides granular control when needed:

!!! warning "Advanced use only"
    Direct state machine access is for complex sequences, lower-level movement primitives, and custom validation logic. Only use this if JubileeManager does not provide what you need.

### LCD Display Reading: HardnessTester

The [`HardnessTester`](api/hardness-tester.md) reads 7-segment LCD displays using segment detection:

- Segment-based recognition (no OCR required)
- Grayscale, sharpening, CLAHE, and threshold preprocessing pipeline
- Works with low-contrast displays
- Calibration system for accurate reading
- Fast and lightweight (no ML dependencies)

## Simple Examples

### Powder Dispensing

Here's a minimal example of using JubileeManager to perform a powder dispense operation:

```python
from src.JubileeManager import JubileeManager

# Create and connect to the powder dispensing system
manager = JubileeManager(
    num_piston_dispensers=2,
    num_pistons_per_dispenser=10
)

# Connect to hardware
if manager.connect(
    machine_address="192.168.1.100",
    scale_port="/dev/ttyUSB0"
):
    print("Connected successfully!")
    
    # Perform a dispense operation
    success = manager.dispense_to_well(
        well_id="0",
        target_weight=50.0  # grams
    )
    
    if success:
        print("Dispense complete!")
    
    # Clean up
    manager.disconnect()
```

### LCD Display Reading

Here's a minimal example of reading a 7-segment LCD display:

```python
from src.HardnessTester import HardnessTester
from src.ConfigLoader import config

# Build from system_config.json (lcd_calibration_path per tester mode)
reader = HardnessTester.from_system_config(
    tester_mode="shore_a",
    cfg=config.system.hardness_testers.shore_a,
)

if reader.load_assigned_calibration():
    result = reader.read_display()
    if result and "?" not in result:
        print(f"LCD shows: {result}")
    else:
        print("Reading failed or unclear")
```

## Key Features

- **Web Automation UI**: Modern interface for interactive powder dispensing and hardness testing
- **Python API**: Full programmatic control for automation
- **Hardware Integration**: Control Jubilee motion platform, scales, and dispensers
- **LCD Display Reading**: Segment-based recognition for 7-segment displays
- **Safety Validation**: All movements validated through state machine
- **Flexible Configuration**: JSON-based configuration system
- **Job Logging**: Per-job JSON records with optional Google Drive backup (CSV and images)
- **MVVM Architecture**: Clean separation between React views, store, and backend model
- **Type Safety**: Full type hints throughout the codebase

## System Architecture

```mermaid
graph TD
    A[Automation UI / User Scripts] --> B[Jubilee Store]
    A --> C[JubileeManager]
    A --> I[HardnessTester]
    B --> L[FastAPI Server]
    L --> C
    C --> D[MotionPlatformStateMachine]
    D --> E[Jubilee Machine]
    D --> F[Scale]
    D --> G[PistonDispenser]
    C --> H[Manipulator]
    H --> D
    I --> J[Camera]
    I --> K[Hardness Display]
```

The system uses a layered architecture where:

1. **Automation UI / User Scripts** interact with the store, API, and core managers
2. **Jubilee Store + FastAPI** coordinate browser workflows and telemetry
3. **JubileeManager** coordinates high-level powder dispensing operations
4. **HardnessTester** reads segmented displays and controls tester interactions
5. **MotionPlatformStateMachine** validates and executes movements
6. **Hardware Components** (Jubilee, Scale, Dispensers, Camera) perform physical actions

## See Also

- **New to the system?** [Quick Start Guide](getting-started/quickstart.md)
- **Ready to use it?** [How-To Guides](how-to/run-new-data.md)
- **Need API details?** [API Reference](api/jubilee-manager.md)
- **Want to understand the design?** [Architecture Guide](concepts/architecture.md)
- **Terminology questions?** [Glossary](concepts/glossary.md)

## Getting Help

If you encounter issues or have questions:

1. Check the [Glossary](concepts/glossary.md) for terminology
2. Review the [How-To Guides](how-to/run-new-data.md) for common tasks
3. Consult the [API Reference](api/jubilee-manager.md) for detailed function documentation
