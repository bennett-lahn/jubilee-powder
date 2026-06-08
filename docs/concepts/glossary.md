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

### Trickler
The powder filling mechanism used to add powder to a mold while it is on the scale.

**Terminology policy**:
- Use **fill** or **add powder** when referring to powder transfer into a mold
- Reserve **dispense** for piston-dispenser operations

### Scale
A precision balance for weighing objects. Connected via USB serial connection.

**Capabilities**:
- Stable weight reading (waits for stability)
- Unstable weight reading (immediate)
- High precision measurements

### HardnessTester
A segment-based LCD display reader that recognizes 7-segment digits without traditional OCR. Useful for reading scale displays, meters, and other LCD equipment.

**Key features**:
- Segment detection instead of OCR
- Works with low-contrast displays
- Calibration system for accurate reading
- No machine learning dependencies

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
- `mold_ready_0`: Position to access mold 0

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

### Mold Without Top Piston
The manipulator is holding a mold that does not contain a top piston.

**Canonical payload enum**: `mold_without_top_piston`

### Mold With Top Piston
The manipulator is holding a mold that contains a top piston.

**Canonical payload enum**: `mold_with_top_piston`

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
- **Home Manipulator** (V-axis): Homes the manipulator's V axis
  - Can be performed while holding a mold without a top piston
  - Starts at v=2 (tamper inserted into mold)
  - Ends at v=-7 (tamper touching bottom of mold)
  - Uses the mold itself as a reference for accurate positioning
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

### Tamping
The process of compressing powder in a mold held by the manipulator before inserting the top piston. Tamping serves two purposes:

1. **Volume reduction**: Compresses powder to allow the top piston to fit when powder volume would otherwise prevent insertion
2. **Airborne particulate reduction**: Reduces the amount of powder that becomes airborne when the piston is inserted

After tamping, the V axis is automatically re-homed to ensure axis accuracy. Typically performed at the `scale_ready` position after filling the mold.

### Trickler
A powder dispensing mechanism used to add material to a mold on the scale. Controlled to achieve precise target weights.

### Well ID
A unique identifier for a mold position using numerical indexing (e.g., "0", "1", "2"). Used to reference specific locations in the deck layout.

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
- "Cannot move with mold_with_top_piston payload"

## Naming Conventions and Legacy Aliases

Use these terms consistently across documentation:

- **Top piston** is canonical. Avoid legacy `cap` terminology.
- **Mold** is canonical for payload/object terminology. Legacy `WeightWell` references should be treated as mold equivalents when encountered in older comments.
- **Payload enums** should use `empty`, `mold_without_top_piston`, `mold_with_top_piston`.
- "Must be at global_ready position first"

## LCD Display Reading Terms

### 7-Segment Display
A type of electronic display that uses seven segments arranged in a figure-eight pattern to display decimal numbers. Each segment can be turned on or off independently.

**Segment layout**:
- Top, Top-Left, Top-Right, Middle, Bottom-Left, Bottom-Right, Bottom

### Segment Detection
The process of determining which segments in a 7-segment display are active (lit) by analyzing pixel brightness in predefined regions.

### Calibration
The process of defining the pixel coordinates (ROI boundaries) for each digit in an LCD display. Required once per display setup.

**Types**:
- **Manual Calibration**: User provides exact pixel coordinates
- **Auto-Detection**: System attempts to find digits automatically

### ROI (Region of Interest)
A rectangular area in an image that contains one digit. Defined by (x1, y1, x2, y2) pixel coordinates.

### Segment Pattern
A 7-bit tuple representing which segments are active in a digit. Example: `(1, 1, 1, 0, 1, 1, 1)` represents digit "0".

### Lookup Table
A dictionary mapping segment patterns to digit strings. Used to recognize digits after segment detection.

### Grayscale Conversion
The primary image preprocessing step used in the LCD reading pipeline. The BGR camera frame is converted to grayscale before CLAHE and thresholding are applied.

### CLAHE (Contrast Limited Adaptive Histogram Equalization)
An image enhancement algorithm that improves local contrast by dividing the image into small tiles and applying histogram equalization to each.

### Segment Threshold
The proportion of pixels that must be active in a segment region for it to be considered "ON". Default: 0.5 (50%)

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

