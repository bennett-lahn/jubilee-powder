# Glossary

This glossary defines key terms used throughout the Jubilee Powder system.

## General Terms

### Jubilee
A tool-changing CNC motion platform developed by the Machine Agency. The base hardware for this automation system.

### Motion Platform
The physical CNC (Computer Numerical Control) system that provides X, Y, Z positioning and tool changing capabilities.

### Deck
The working surface of the Jubilee where labware (molds, dispensers, scale, etc.) is positioned. The deck layout is defined in configuration files.

### Labware
Physical items placed on the deck, such as well plates, dispensers, scales, and other equipment.

## Core Components

### JubileeManager
The primary high-level interface for controlling the Jubilee system. Coordinates operations between multiple hardware components and provides simplified APIs for common tasks.

**When to use**: For all standard operations. This should be your first choice for interacting with the system.

### MotionPlatformStateMachine
A state machine that validates and executes all movements. Ensures safety by tracking system state and preventing invalid operations.

**When to use**: For advanced control when JubileeManager doesn't provide the specific operation you need.

### Manipulator
A custom toolhead with a gripper and vertical axis (V-axis). Used for picking up and placing molds and other objects.

**Key features**:
- Gripper for holding objects
- Vertical axis for precise height control
- Integrated with state machine for validated movements

### PistonDispenser
A container that holds and dispenses cylindrical pistons. Tracks the number of available pistons and provides them one at a time.

**Key features**:
- Holds multiple pistons in a stack
- Dispenses from the top of the stack
- Tracks available piston count

### Scale
A precision balance for weighing objects. Connected via USB serial connection.

**Capabilities**:
- Stable weight reading (waits for stability)
- Unstable weight reading (immediate)
- High precision measurements

## State Machine Concepts

### State
The current condition of the system, including:
- Physical position of the motion platform
- Which tool is active (picked up)
- What the manipulator is holding (payload)

### Validation
The process of checking whether a requested operation is safe and valid given the current state.

**Validation checks**:
- Is the current position correct for this operation?
- Is the right tool picked up?
- Is the payload state compatible?
- Are constraints satisfied?

### Named Position
A predefined location on the deck with a specific name (e.g., "global_ready", "scale_ready"). Named positions are defined in the configuration file.

**Examples**:
- `global_ready`: Safe position away from all labware
- `scale_ready`: Position to access the scale
- `mold_slot_A1`: Position to access well A1

### Transition
A validated movement from one named position to another. The state machine defines which transitions are allowed.

### Context
The state machine's internal representation of the current system state. Includes:
- Current position
- Active tool
- Payload state
- Reference to hardware components

## Payload States

### Empty
The manipulator is not holding any object. This is the default state after homing or after placing an object.

### Mold
The manipulator is holding a mold (well plate or container). The mold does not contain a piston.

### Mold with Piston
The manipulator is holding a mold that contains a piston. This affects weight and handling.

## Tool Concepts

### Tool
An interchangeable attachment that the Jubilee can pick up and put down. In this system, the primary tool is the Manipulator.

### Tool Pickup
The process of mechanically engaging with a tool at its parking position and locking it to the carriage.

### Tool Parking
The process of placing a tool back at its designated parking position and releasing it.

### Active Tool
The tool currently picked up and ready for use. Only one tool can be active at a time.

## Movement Concepts

### Homing
The process of moving axes to their reference positions (endstops) to establish a coordinate system. Must be done before any precision operations.

**Types**:
- **Home All**: Homes X, Y, Z, and U axes
- **Home Manipulator**: Homes the manipulator's V axis
- **Rehome**: Re-establishes reference after an error

### Feed Rate
The speed at which the motion platform moves. Can be set to different values for different operations.

**Common values**:
- SLOW: For precise operations
- MEDIUM: For normal operations (default)
- FAST: For rapid positioning

### Safe Zone
An area of the deck where movement is known to be safe. The state machine uses safe zones to prevent collisions.

## Configuration Terms

### Configuration File
A JSON file that defines system parameters, positions, and constraints. Changes to configuration do not require code changes.

**Key configuration files**:
- `motion_platform_positions.json`: Defines positions and transitions
- `system_config.json`: System-level settings
- `mold_labware.json`: Deck layout and labware
- `weight_well_deck.json`: Well-specific parameters

### Deck Layout
The arrangement of labware on the Jubilee deck, defined in configuration files. Includes positions and dimensions of all items.

### System Config
Global system parameters such as:
- Duet controller IP address
- Serial port assignments
- Default feed rates
- Tool configurations

## Operation Terms

### Dispense Operation
A complete workflow that:
1. Picks up a mold from a well
2. Moves to the scale
3. Fills the mold with powder to a target weight
4. Retrieves a piston from a dispenser
5. Returns the mold to the well

### Trickler
A powder dispensing mechanism used to add material to a mold on the scale. Controlled to achieve precise target weights.

### Well ID
A unique identifier for a position in a well plate (e.g., "A1", "B2"). Used to reference specific locations in the deck layout.

### Target Weight
The desired weight of material to dispense into a mold, measured in grams.

## Error and Validation Terms

### Validation Result
The result of a validation check, indicating whether an operation is allowed and providing a reason if not.

**Fields**:
- `valid`: Boolean indicating if operation is allowed
- `reason`: String explaining why operation was rejected (if invalid)

### Tool State Error
An exception raised when an operation is attempted with the wrong tool state (e.g., tool not picked up, wrong tool active).

### Movement Constraint
A rule that limits when or how a movement can be performed. Examples:
- "Must have manipulator tool picked up"
- "Cannot move with mold_with_piston payload"
- "Must be at global_ready position first"

## Hardware Terms

### Duet Controller
The controller board that runs the Jubilee machine. Provides G-code interpretation and motor control.

### G-code
The programming language used to control CNC machines. The Duet controller interprets G-code commands.

### Endstop
A sensor that detects when an axis has reached its reference position. Used during homing.

### Serial Port
A communication interface used to connect to the scale. Typically appears as `/dev/ttyUSB0` on Linux.

### IP Address
The network address of the Jubilee's Duet controller. Used to establish network communication.

## Software Development Terms

### Type Hints
Python annotations that specify the expected types of function parameters and return values. Used throughout the codebase for better code quality.

### Docstring
Documentation embedded in Python code that describes what a function, class, or module does. This project uses Google-style docstrings.

### Google Docstring Style
A specific format for writing docstrings that includes sections for arguments, returns, raises, examples, etc.

## See Also

- [Architecture Overview](architecture.md) - Understand how these components work together
- [Quick Start Guide](../getting-started/quickstart.md) - See these terms in context
- [API Reference](../api/jubilee-manager.md) - Detailed documentation of all components

