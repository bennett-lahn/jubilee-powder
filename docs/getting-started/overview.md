# Overview

## What is Jubilee Powder?

Jubilee Powder is a comprehensive software system for controlling the Jubilee Motion Platform to automate powder dispensing and Shore hardness testing. It provides both a browser-based interface and a Python API for coordinating operations across multiple hardware components.

## Core Components

### Hardware

The system integrates several hardware components:

- **Jubilee Motion Platform**: A tool-changing CNC motion system
- **Precision Scale**: For weighing materials with high accuracy (typically A&D FX-120i)
- **Piston Dispensers**: For storing and dispensing cylindrical pistons, placed in molds after dispensing powder
- **Manipulator Tool**: A custom toolhead with grabber and vertical axis

### Software Layers

The software is organized in layers from high-level to low-level:

1. **Automation UI** (User Interface)
   - Browser-based interface for dispensing and hardness jobs
   - Visual mold selection and configuration
   - Real-time progress monitoring
   - Built-in safety checks

2. **Frontend Coordination Layer**
   - Zustand-based `Jubilee Store` for browser state and actions
   - FastAPI server for REST and WebSocket transport

3. **JubileeManager** (Core API)
   - Highest-level programming API
   - Error handling and recovery
   - Hardware state management

4. **MotionPlatformStateMachine** (Validation Layer)
   - Validates all movements for safety
   - Manages system state
   - Enforces movement constraints

5. **Hardware Drivers** (Bottom Layer)
   - Direct hardware communication
   - Low-level control primitives
   - Communicates with Duet3D Controller

## Key Concepts

### State Machine Validation

All movements are validated through a state machine that:

- Tracks the current position and tool state
- Validates requested movements are safe
- Prevents invalid state transitions
- Ensures proper sequencing of operations

### Tool Management

The Jubilee uses a tool-changing system where:

- Tools are picked up and parked at specific positions
- Only one tool can be active at a time
- Tools must be at specific positions for certain operations

### Payload Tracking

The system tracks what the manipulator is holding:

- `empty`: No mold held
- `mold_without_top_piston`: Holding a mold without top piston
- `mold_with_top_piston`: Holding a mold with top piston

This enables safe movement validation based on current load.

## Design Philosophy

### Safety First

- All movements are validated before execution
- State machine prevents unsafe operations
- Clear error messages for invalid requests

### Ease of Use

- High-level API for common operations
- Progressive disclosure (simple things easy, complex things possible)
- GUI for user-modifiable operations
- Python API

### Flexibility

- JSON-based configuration
- Extensible architecture
- Multiple access levels (high-level to low-level)
- MVVM architecture for GUI extensibility

## Usage Options

### Automation UI

For interactive machine operation with visual feedback, use the web interface documented in [Using the Automation UI](../how-to/using-gui.md).

**Features:**
- Visual mold and sample selection
- Real-time weight and job monitoring
- Hardware configuration and connection lifecycle
- Safety checks and emergency controls

### Python API (Automation)

For scripted tasks and custom workflows:

```python
from src.JubileeManager import JubileeManager

manager = JubileeManager(num_piston_dispensers=2, num_pistons_per_dispenser=10)
manager.connect()
manager.dispense_to_well("0", 50.0)
manager.disconnect()
```

See [Quick Start Guide](quickstart.md) for details.

## System Requirements

### Hardware Requirements

- Jubilee Motion Platform with Duet3D controller
- USB connection to precision scale (A&D FX-120i preferred, other A&D scales may work)
- Network connection to Jubilee controller
- Sufficient workspace for deck layout

### Software Requirements

- Python 3.12 or later
- Node.js 20.19+ or 22.12+ (Vite 8 requirement; `deploy/install.sh` installs Node 22 LTS automatically)
- Linux-based operating system (for hardware integration)
- Dependencies listed in `requirements.txt`

## Installation

1. Clone the repository:
```bash
git clone https://github.com/bennett-lahn/jubilee-powder.git
cd jubilee-powder
```

2. Create a virtual environment:
```bash
python -m venv jubilee-env
source jubilee-env/bin/activate  # On Linux/Mac
# or
jubilee-env\Scripts\activate  # On Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure your system:
   - Edit configuration files in `jubilee_api_config/`. You may need to edit all homing files, tool pickup/place, and config files to match your unique setup. 
   - Set Jubilee IP address
   - Configure deck layout
   - Set up tool positions

## Next Steps

- **To launch the web UI:** See [Building and Running](../how-to/running.md) for dev mode, production mode, and Raspberry Pi kiosk setup
- **For GUI users:** Follow the [GUI User Guide](../how-to/using-gui.md)
- **For programmers:** Follow the [Quick Start Guide](quickstart.md)
- **Before your first run:** Read [Best Practices](../concepts/best-practices.md) for hardware safety rules
- Learn about key concepts in the [Architecture Guide](../concepts/architecture.md)
- Explore [How-To Guides](../how-to/run-new-data.md) for common tasks

