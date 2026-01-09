# Overview

## What is Jubilee Powder?

Jubilee Powder is a comprehensive software system for controlling the Jubilee Motion Platform to automate powder dispensing and handling tasks. It provides a Python API for coordinating complex powder dispensing operations involving multiple hardware components.

## Core Components

### Hardware

The system integrates with several hardware components:

- **Jubilee Motion Platform**: A tool-changing CNC motion system
- **Precision Scale**: For weighing materials with high accuracy
- **Piston Dispensers**: For storing and dispensing cylindrical pistons/tools
- **Manipulator Tool**: A custom toolhead with gripper and vertical axis

### Software Layers

The software is organized in layers from high-level to low-level:

1. **JubileeManager** (Top Layer)
   - Highest-level API for common operations
   - Coordinates multiple components
   - Error handling and recovery

2. **MotionPlatformStateMachine** (Middle Layer)
   - Validates all movements for safety
   - Manages system state
   - Enforces movement constraints

3. **Hardware Drivers** (Bottom Layer)
   - Direct hardware communication
   - Low-level control primitives

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
- `mold`: Holding a mold
- `mold_with_piston`: Holding a mold that contains a piston

This enables safe movement validation based on current load.

## Design Philosophy

### Safety First

- All movements are validated before execution
- State machine prevents unsafe operations
- Clear error messages for invalid requests

### Ease of Use

- High-level API for common operations
- Sensible defaults
- Progressive disclosure (simple things simple, complex things possible)

### Flexibility

- JSON-based configuration
- Extensible architecture
- Multiple access levels (high-level to low-level)

## System Requirements

### Hardware Requirements

- Jubilee Motion Platform with Duet3D controller
- USB connection to precision scale
- Network connection to Jubilee controller
- Sufficient workspace for deck layout

### Software Requirements

- Python 3.8 or later
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
   - Edit configuration files in `jubilee_api_config/`
   - Set Jubilee IP address
   - Configure deck layout
   - Set up tool positions

## Next Steps

- Follow the [Quick Start Guide](quickstart.md) for your first program
- Learn about key concepts in the [Architecture Guide](../concepts/architecture.md)
- Explore [How-To Guides](../how-to/run-new-data.md) for common tasks

