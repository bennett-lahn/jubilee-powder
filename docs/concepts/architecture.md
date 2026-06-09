# System Architecture

This document explains the architecture of Jubilee Powder at a conceptual level.

## Overview

Jubilee Powder uses a layered architecture where each layer provides a different level of abstraction and control.

## Architecture Diagram

```mermaid
graph TB
    subgraph "User Interface Layer"
        A[User Scripts]
        subgraph "Web Frontend"
            B[React Screens / Components]
            Z[Zustand Store]
        end
    end

    subgraph "API Layer"
        C[FastAPI Server]
        CM[HardwareManager]
    end
    
    subgraph "Coordination Layer"
        D[JubileeManager]
    end
    
    subgraph "Validation Layer"
        E[MotionPlatformStateMachine]
        F[MovementExecutor]
    end
    
    subgraph "Component Layer"
        G[Manipulator]
        H[PistonDispenser]
        I[Scale]
    end
    
    subgraph "Hardware Layer"
        J[Jubilee Machine]
        K[Scale Hardware]
        L[Deck/Labware]
    end
    
    subgraph "Configuration"
        M[ConfigLoader]
        N[JSON Config Files]
    end
    
    B -- useJubileeStore --> Z
    Z -- REST / WebSocket --> C
    C --> CM
    CM --> D
    A --> D
    D --> E
    D --> G
    D --> I
    E --> F
    F --> J
    G --> E
    H --> E
    I --> K
    E --> L
    M --> N
    D --> M
    E --> M
```

## Layer Details

### 1. User Interface Layer

**Purpose**: Entry point for automation tasks and user interaction

**Components**:

- **User Scripts**: Python scripts written by users to automate specific tasks
- **Web Frontend**: Browser-based React application for interactive control and monitoring

**Responsibilities**:

- Display system state and progress
- Accept user input (well selection, weights, configuration)
- Provide visual feedback
- Submit jobs and monitor progress in real time

**Web Frontend Architecture (MVVM)**:

The browser application follows an MVVM pattern:

| Layer     | Component                    | Responsibility                          |
|-----------|------------------------------|-----------------------------------------|
| View      | React screens + components   | Render state, capture user input        |
| ViewModel | Zustand store                | Derived state, REST/WebSocket actions   |
| Model     | FastAPI server + HardwareManager | Hardware state, physical operations |

See [Web Frontend Reference](../api/gui/jubilee-gui.md) and
[Jubilee Store Reference](../api/gui/jubilee-view-model.md) for details.

### 2. API Layer (Web Frontend Only)

**Purpose**: Bridge the React frontend to the hardware coordination layer

**Components**:

- **FastAPI Server** (`frontend/server.py`): REST endpoints and WebSocket telemetry
- **HardwareManager** (`frontend/src/hardware_manager.py`): Async wrapper around
  `JubileeManager` that offloads all blocking calls to `asyncio.to_thread()`

**Responsibilities**:

- Serve REST endpoints for discrete commands (connect, start/stop/abort job, etc.)
- Push a continuous 4 Hz telemetry frame to all connected browsers via WebSocket
- Translate between the async FastAPI event loop and the synchronous `JubileeManager` API
- Manage job lifecycle (start, progress tracking, `JobLog` persistence)
- Optionally upload completed logs to Google Drive when `google_drive.enabled` is true

**Key Design**:

- A `MockHardwareManager` with an identical public API enables UI development without
  physical hardware
- WebSocket telemetry eliminates polling: every connected browser tab receives live
  state updates at 4 Hz without issuing repeated REST calls
- Job progress is tracked in a shared `JobProgress` object threaded through server
  endpoints and the hardware manager
- Completed jobs are written as JSON by `JobLog` (`metadata` + `state.molds` or
  `state.samples`). When Drive backup is enabled, `JobDriveBackup` exports CSV
  and image artifacts before upload

### 3. Coordination Layer

**Purpose**: Coordinate complex multi-component operations

**Components**:

- **JubileeManager**: Central orchestrator for all operations

**Responsibilities**:

- Connect to and manage all hardware components
- Provide high-level API for common operations
- Coordinate multi-step operations (e.g., dispense_to_well)
- Store all hardware state (dispensers, pistons, positions)
- Handle errors and provide meaningful feedback

**Key Design Decisions**:

- Single point of access for most operations
- Owns the state machine (cannot be bypassed)
- Provides both convenience methods and component access
- All hardware state lives here

### 4. Validation Layer

**Purpose**: Ensure all operations are safe and valid

**Components**:

- **MotionPlatformStateMachine**: Validates and executes movements
- **MovementExecutor**: Executes validated movements on hardware

**Responsibilities**:

- Track current system state (position, tool, payload)
- Validate requested movements against current state
- Enforce movement constraints and safe zones
- Provide detailed error messages for invalid requests
- Execute validated movements

**State Machine States**:

The state machine tracks:

- **Position**: Current named position (e.g., "global_ready", "scale_ready")
- **Active Tool**: Which tool is currently picked up (or None)
- **Payload**: What the manipulator is holding (`empty`, `mold_without_top_piston`, `mold_with_top_piston`)

**Validation Rules**:

- Tool must be picked up to move to certain positions
- Payload state affects which movements are allowed
- Some operations require specific starting positions

### 5. Component Layer

**Purpose**: Represent individual hardware components

**Components**:

- **Manipulator**: Gripper tool with vertical axis
- **PistonDispenser**: Container for pistons with tracking
- **Scale**: Weight measurement device

**Responsibilities**:

- Encapsulate component-specific logic
- Provide component-specific operations
- Maintain component state
- Interact with validation layer for movements

### 6. Hardware Layer

**Purpose**: Physical hardware interface

**Components**:

- **Jubilee Machine**: CNC motion platform (via science-jubilee library)
- **Scale Hardware**: Precision balance (via serial connection)
- **Deck/Labware**: Physical deck layout and labware definitions (`Mold`, `MoldSet` in `trickler_labware`)

**Responsibilities**:

- Execute physical movements
- Report sensor readings
- Handle low-level communication protocols

### 7. Configuration

**Purpose**: Centralize system configuration

**Components**:

- **ConfigLoader**: Loads and provides access to configuration
- **JSON Config Files**: Define positions, deck layouts, system parameters

**Configuration Files**:

- `motion_platform_positions.json`: State machine positions and transitions
- `system_config.json`: System-level settings
- `mold_labware.json`: Deck layout and labware definitions
- `weight_well_deck.json`: Well-specific configurations

## Data Flow

### Example: Web UI Multi-Well Dispensing Job

This example traces how a multi-well dispensing job flows through the web frontend:

```mermaid
sequenceDiagram
    participant U as User (Browser)
    participant S as Zustand Store
    participant API as FastAPI Server
    participant HM as HardwareManager
    participant JM as JubileeManager
    participant H as Hardware

    U->>S: submitJob('dispensing', wells)
    S->>API: POST /api/job/start
    API-->>S: 202 Accepted
    API->>HM: run_dispensing_job(wells, progress)

    loop For each well
        HM->>JM: dispense_to_well(well_id, weight)
        JM->>H: move, pick, fill, piston
        H-->>JM: complete
        JM-->>HM: True
        HM->>HM: progress.completed += 1
        API->>S: WebSocket frame (job.completed, job.current_item)
        S->>U: re-render arc + well grid
    end

    HM-->>API: job loop exits
    API->>S: WebSocket frame (job.running = false)
    S->>U: show completed state
```

### Example: Direct Script Operation

For comparison, a direct script operation (without the web frontend):

```mermaid
sequenceDiagram
    participant U as User Script
    participant JM as JubileeManager
    participant SM as StateMachine
    participant M as Manipulator
    participant S as Scale
    participant H as Hardware

    U->>JM: dispense_to_well("0", 50.0)
    JM->>SM: validated_move_to_mold_slot("0")
    SM->>SM: Check current state
    SM->>SM: Validate movement
    SM->>H: Execute movement
    H-->>SM: Movement complete
    SM-->>JM: Success
    
    JM->>M: pick_mold("0")
    M->>SM: Update payload state
    M->>H: Execute gripper
    
    JM->>SM: validated_move_to_scale()
    SM->>H: Execute movement
    
    JM->>M: place_mold_on_scale()
    M->>H: Execute gripper
    M->>SM: Update payload state
    
    JM->>SM: validated_fill_powder(50.0)
    SM->>S: Read weight
    SM->>H: Control trickler
    SM->>S: Read weight
    Note over SM,S: Repeat until target reached
    
    JM->>M: pick_mold_from_scale()
    JM->>SM: validated_move_to_dispenser()
    JM->>JM: get_piston_from_dispenser()
    JM->>SM: validated_move_to_mold_slot("0")
    JM->>M: place_mold("0")
    
    JM-->>U: True (success)
```

## Key Design Principles

### Safety Through Validation

!!! warning "All movements pass through the state machine"
    Direct G-code or science-jubilee moves that bypass the state machine will desynchronize internal position tracking. Use validated paths for all automated operation.

All movements must pass through the state machine validator. This prevents:

- Moving to unsafe positions
- Collisions between tools and labware
- Invalid state transitions
- Operating on wrong component

### Progressive Disclosure

The architecture supports multiple levels of complexity:

- **Simple**: Use JubileeManager methods (most users)
- **Advanced**: Access state machine directly (power users)
- **Expert**: Access components and machine directly (developers)

### State Tracking

The system maintains comprehensive state:

- Physical position of motion platform
- Active tool and payload
- Component states (dispenser piston counts, etc.)
- Configuration data

### Fail-Safe Defaults

When operations fail:

- Clear error messages explain what went wrong
- System state remains consistent
- No silent failures
- Failed operations return ``False`` or an invalid ``MoveValidationResult``

### Configuration-Driven

!!! note "Config is the source of truth"
    Machine behavior comes from checked-in JSON under `jubilee_api_config/`, loaded via `ConfigLoader` and `PositionRegistry`. See the [Configuration Guide](../how-to/configuration.md).

Physical parameters are in configuration files, not code:

- Easy to adapt to different setups
- No recompilation needed
- Version control for configurations
- Validation of configuration data

## Extending the System

To add new operations, hardware, or positions, follow the same layered pattern:

- New high-level operations belong in `JubileeManager`, implemented as calls to `validated_*` state machine methods.
- New hardware components follow the existing `PistonDispenser` / `Scale` pattern: a class that encapsulates component state and uses the state machine for movements.
- New named positions are added to `motion_platform_positions.json` with transitions, constraints, and tool requirements. See the [Configuration Guide](../how-to/configuration.md) for details.

See [JubileeManager](../api/jubilee-manager.md) and [MotionPlatformStateMachine](../api/motion-platform.md) for implementation specifics.

## See Also

- [Glossary](glossary.md) for terminology
- [JubileeManager API](../api/jubilee-manager.md)
- [State Machine Details](../api/motion-platform.md)
- [Web Frontend Reference](../api/gui/jubilee-gui.md) for the REST API and React application
- [Jubilee Store Reference](../api/gui/jubilee-view-model.md) for the ViewModel layer
- [Best Practices](best-practices.md) for safe operation

