from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, TYPE_CHECKING

from statemachine import State, StateMachine
from science_jubilee.Machine import Machine
from science_jubilee.decks.Deck import Deck
from PistonDispenser import PistonDispenser
from Scale import Scale

# Import FeedRate for type checking only (avoiding circular import)
if TYPE_CHECKING:
    from MovementExecutor import FeedRate
else:
    # At runtime, import in __init__ where needed
    FeedRate = 'FeedRate'


class PositionType(Enum):
    """Enumerates high-level motion platform positions."""

    GLOBAL_READY = auto()
    MOLD_READY = auto()
    DISPENSER_READY = auto()
    SCALE_READY = auto()


@dataclass(frozen=True)
class ZHeightPolicy:
    """Defines the z-height constraints that must be satisfied before a move."""

    allowed: frozenset[str] = field(default_factory=frozenset)
    required: Optional[str] = None

    def validate(self, z_height_id: Optional[str]) -> Optional[str]:
        """Return a human readable error message if the policy is not satisfied."""
        if (self.required or self.allowed) and z_height_id is None:
            return "Current z-height is not set."

        if self.required and z_height_id != self.required:
            current = "None" if z_height_id is None else z_height_id
            return f"Move requires z-height '{self.required}', current '{current}'."

        if self.allowed and z_height_id not in self.allowed:
            allowed = ", ".join(sorted(self.allowed))
            current = "None" if z_height_id is None else z_height_id
            return f"Z-height '{current}' not permitted. Allowed: {allowed}."

        return None


@dataclass(frozen=True)
class MachineCoordinates:
    """Physical X, Y, Z, V coordinates for a position."""
    
    x: Optional[float | str] = None
    y: Optional[float | str] = None
    z: Optional[float | str] = None  # Can be "USE_Z_HEIGHT_POLICY" or numeric
    v: Optional[float | str] = None


@dataclass(frozen=True)
class PositionDescriptor:
    """
    Describes a logical position that the motion platform can occupy.

    Positions extend beyond XYZ coordinates and capture the holistic machine
    pose, including manipulator states, payload status, or ancillary actuator
    configurations.
    """

    identifier: str
    type: PositionType
    allowed_origins: frozenset[str]
    allowed_destinations: frozenset[str]
    coordinates: Optional[MachineCoordinates] = None
    requirements: Mapping[str, object] = field(default_factory=dict)
    z_height_policy: ZHeightPolicy = field(default_factory=ZHeightPolicy)
    allows_tool_engagement: bool = False
    engagement_requirements: Mapping[str, object] = field(default_factory=dict)
    engagement_actions: frozenset[str] = field(default_factory=frozenset)
    resource_id: Optional[str] = None
    description: str = ""
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionDescriptor:
    """Represents an auxiliary action that can be validated by the FSM."""

    identifier: str
    position_scope: frozenset[str]
    requirements: Mapping[str, object] = field(default_factory=dict)
    excludes: Mapping[str, object] = field(default_factory=dict)
    required_tool_id: Optional[str] = None
    requires_tool_engaged: bool = False
    blocked_when_engaged: bool = False
    description: str = ""


@dataclass
class ToolStatus:
    """Tracks engagement state and the ready point associated with a tool."""

    tool_id: str
    engaged: bool = False
    ready_position_id: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class MotionContext:
    """Captures the mutable state of the motion platform."""

    position_id: str
    z_height_id: Optional[str] = None
    active_tool_id: Optional[str] = None
    payload_state: Optional[str] = None
    tool_states: Dict[str, ToolStatus] = field(default_factory=dict)
    pending_move: Optional["MoveRequest"] = None
    engaged_ready_position_id: Optional[str] = None
    engaged_tool_id: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)
    # Platform state tracking
    deck: Optional[Deck] = None
    scale: Optional[Scale] = None  # Reference to scale object
    current_well: Optional[object] = None  # Mold object representing the mold being carried
    mold_on_scale: bool = False  # Whether the current mold is on the scale
    piston_dispensers: List[object] = field(default_factory=list)  # List of PistonDispenser objects


@dataclass
class MoveRequest:
    """Represents a requested transition for the motion platform."""

    target_position_id: str
    action: Optional[str] = None
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass
class MoveValidationResult:
    """Encapsulates the outcome of a move validation."""

    valid: bool
    reason: Optional[str] = None


class PositionRegistry:
    """Utility container for known platform positions."""
    # TODO: Update coordinate tolerance to remove hard coded values
    def __init__(self, positions: Iterable[PositionDescriptor]) -> None:
        self._positions: Dict[str, PositionDescriptor] = {}
        self._actions: Dict[str, ActionDescriptor] = {}
        self._z_heights: Dict[str, object] = {}
        self._coordinate_tolerance: Dict[str, float] = {
            "x": 0.2,
            "y": 0.2,
            "z": 0.2,
            "v": 0.2,
        }

        for position in positions:
            self.add_position(position)

    @classmethod
    def from_config_file(cls, path: str | Path) -> "PositionRegistry":
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        # First pass: collect all positions to build type-to-id mapping
        positions: list[PositionDescriptor] = []
        type_to_ids: Dict[str, set[str]] = {}
        
        for raw in payload.get("positions", []):
            try:
                position_type = PositionType[raw["type"]]
            except KeyError as exc:
                raise KeyError(f"Unknown position type '{raw['type']}'") from exc

            position_id = raw["id"]
            type_name = raw["type"]
            
            if type_name not in type_to_ids:
                type_to_ids[type_name] = set()
            type_to_ids[type_name].add(position_id)

            z_policy_config = raw.get("z_height_policy", {})
            z_policy = ZHeightPolicy(
                allowed=frozenset(z_policy_config.get("allowed", [])),
                required=z_policy_config.get("required"),
            )

            engagement_cfg = raw.get("engagement") or {}
            
            # Parse coordinates if present
            coords_cfg = raw.get("coordinates")
            coordinates = None
            if coords_cfg:
                coordinates = MachineCoordinates(
                    x=coords_cfg.get("x"),
                    y=coords_cfg.get("y"),
                    z=coords_cfg.get("z"),
                    v=coords_cfg.get("v"),
                )

            # Store raw origins/destinations for now
            descriptor = PositionDescriptor(
                identifier=position_id,
                type=position_type,
                allowed_origins=frozenset(raw.get("allowed_origins", [])),
                allowed_destinations=frozenset(raw.get("allowed_destinations", [])),
                coordinates=coordinates,
                requirements=dict(raw.get("requirements", {})),
                z_height_policy=z_policy,
                allows_tool_engagement=raw.get("allows_tool_engagement", False),
                engagement_requirements=dict(engagement_cfg.get("requirements", {})),
                engagement_actions=frozenset(engagement_cfg.get("allowed_actions", [])),
                resource_id=raw.get("resource_id"),
                description=raw.get("description", ""),
                metadata=dict(raw.get("metadata", {})),
            )
            positions.append(descriptor)

        # Second pass: expand type references to actual position IDs
        def expand_references(refs: frozenset[str]) -> frozenset[str]:
            """Expand type names (e.g., 'MOLD_READY') to all position IDs of that type."""
            expanded = set()
            for ref in refs:
                if ref in type_to_ids:
                    # It's a type reference, expand to all IDs of that type
                    expanded.update(type_to_ids[ref])
                else:
                    # It's a specific position ID
                    expanded.add(ref)
            return frozenset(expanded)

        # Update all descriptors with expanded references
        expanded_positions = []
        for descriptor in positions:
            expanded_descriptor = PositionDescriptor(
                identifier=descriptor.identifier,
                type=descriptor.type,
                allowed_origins=expand_references(descriptor.allowed_origins),
                allowed_destinations=expand_references(descriptor.allowed_destinations),
                coordinates=descriptor.coordinates,
                requirements=descriptor.requirements,
                z_height_policy=descriptor.z_height_policy,
                allows_tool_engagement=descriptor.allows_tool_engagement,
                engagement_requirements=descriptor.engagement_requirements,
                engagement_actions=descriptor.engagement_actions,
                resource_id=descriptor.resource_id,
                description=descriptor.description,
                metadata=descriptor.metadata,
            )
            expanded_positions.append(expanded_descriptor)

        registry = cls(expanded_positions)
        registry._actions = {
            action_cfg["id"]: ActionDescriptor(
                identifier=action_cfg["id"],
                position_scope=frozenset(action_cfg.get("position_scope", [])),
                requirements=dict(action_cfg.get("requirements", {})),
                excludes=dict(action_cfg.get("excludes", {})),
                required_tool_id=action_cfg.get("required_tool_id"),
                requires_tool_engaged=action_cfg.get("requires_tool_engaged", False),
                blocked_when_engaged=action_cfg.get("blocked_when_engaged", False),
                description=action_cfg.get("description", ""),
            )
            for action_cfg in payload.get("actions", [])
        }
        registry._z_heights = dict(payload.get("z_heights", {}))
        
        # Load coordinate tolerance if present
        if "coordinate_tolerance" in payload:
            tolerance_cfg = payload["coordinate_tolerance"]
            registry._coordinate_tolerance = {
                "x": tolerance_cfg.get("x", 0.2),
                "y": tolerance_cfg.get("y", 0.2),
                "z": tolerance_cfg.get("z", 0.2),
                "v": tolerance_cfg.get("v", 0.2),
            }
        
        return registry

    def add_position(self, position: PositionDescriptor) -> None:
        if position.identifier in self._positions:
            raise ValueError(f"Duplicate position identifier '{position.identifier}'")
        self._positions[position.identifier] = position

    def get(self, identifier: str) -> PositionDescriptor:
        try:
            return self._positions[identifier]
        except KeyError as exc:
            raise KeyError(f"Unknown position identifier '{identifier}'") from exc

    def has(self, identifier: str) -> bool:
        return identifier in self._positions

    def find_first_of_type(self, position_type: PositionType) -> Optional[PositionDescriptor]:
        for descriptor in self._positions.values():
            if descriptor.type == position_type:
                return descriptor
        return None

    def get_action(self, identifier: str) -> ActionDescriptor:
        try:
            return self._actions[identifier]
        except KeyError as exc:
            raise KeyError(f"Unknown action identifier '{identifier}'") from exc

    @property
    def actions(self) -> Dict[str, ActionDescriptor]:
        return dict(self._actions)

    @property
    def z_heights(self) -> Dict[str, object]:
        return dict(self._z_heights)
    
    @property
    def coordinate_tolerance(self) -> Dict[str, float]:
        return dict(self._coordinate_tolerance)
    
    def validate_machine_position(
        self,
        position_id: str,
        machine_x: float,
        machine_y: float,
        machine_z: float,
        machine_v: float,
        current_z_height_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Validate that the machine is actually at the expected coordinates for a position.
        
        Returns None if validation passes, or an error message if coordinates don't match.
        """
        position = self.get(position_id)
        if not position.coordinates:
            # No coordinates defined for this position, skip validation
            return None
        
        coords = position.coordinates
        tolerance = self._coordinate_tolerance
        
        def check_coord(axis: str, expected: Optional[float | str], actual: float) -> Optional[str]:
            """Check if a single coordinate is within tolerance."""
            if expected is None:
                return None
            
            # Handle placeholder strings
            if isinstance(expected, str):
                if expected.startswith("PLACEHOLDER"):
                    # Placeholder not yet filled in, skip validation
                    return None
                if expected == "USE_Z_HEIGHT_POLICY":
                    # Special case: Z coord comes from z_height policy
                    if current_z_height_id is None:
                        return "Z coordinate requires z_height_id but none provided"
                    if current_z_height_id not in self._z_heights:
                        return f"Unknown z_height_id: {current_z_height_id}"
                    z_config = self._z_heights[current_z_height_id]
                    if isinstance(z_config, dict):
                        z_expected = z_config.get("z_coordinate")
                        if z_expected and isinstance(z_expected, (int, float)):
                            if abs(actual - z_expected) > tolerance[axis]:
                                return f"{axis.upper()} coordinate mismatch: expected {z_expected}, got {actual} (tolerance: ±{tolerance[axis]})"
                    return None
            
            # Numeric comparison
            if isinstance(expected, (int, float)):
                if abs(actual - expected) > tolerance[axis]:
                    return f"{axis.upper()} coordinate mismatch: expected {expected}, got {actual} (tolerance: ±{tolerance[axis]})"
            
            return None
        
        # Check each axis
        for axis, expected, actual in [
            ("x", coords.x, machine_x),
            ("y", coords.y, machine_y),
            ("z", coords.z, machine_z),
            ("v", coords.v, machine_v),
        ]:
            error = check_coord(axis, expected, actual)
            if error:
                return f"Position '{position_id}' validation failed: {error}"
        
        return None


class MotionPlatformStateMachine(StateMachine):
    """
    Finite state machine responsible for validating and sequencing platform moves.

    The machine relies on python-statemachine to model the control flow. It
    maintains awareness of both high-level state (idle, moving, tool engaged)
    and the current logical position descriptor.
    """

    idle = State("Idle", initial=True)
    moving = State("Moving")
    tool_engaged = State("Tool Engaged")

    begin_motion = idle.to(moving)
    complete_motion = moving.to(idle)
    complete_motion_with_tool = moving.to(tool_engaged)
    engage_tool = idle.to(tool_engaged)
    disengage_tool = tool_engaged.to(idle)
    abort_motion = moving.to(idle)

    def __init__(self, registry: PositionRegistry, machine: Machine, *, context: Optional[MotionContext] = None, scale: Optional[Scale] = None, feedrate: 'FeedRate' = None) -> None:
        # Import MovementExecutor locally to avoid circular import
        from MovementExecutor import MovementExecutor, FeedRate as FR
        
        # Handle default feedrate
        if feedrate is None:
            feedrate = FR.MEDIUM
        
        self._registry = registry
        self._actions = registry.actions
        
        if context is None:
            initial_descriptor = registry.find_first_of_type(PositionType.GLOBAL_READY)
            if not initial_descriptor:
                raise ValueError("Configuration must define a GLOBAL_READY position.")
            context = MotionContext(position_id=initial_descriptor.identifier, scale=scale)
        else:
            # Ensure the provided context references a known position.
            self._registry.get(context.position_id)
            # Update scale if provided
            if scale is not None:
                context.scale = scale

        self.context = context
        self._executor = MovementExecutor(machine, scale=scale, feedrate=feedrate)
        super().__init__()

    @classmethod
    def from_config_file(
        cls,
        path: str | Path,
        machine: Machine,
        *,
        context_overrides: Optional[Mapping[str, object]] = None,
        scale: Optional[Scale] = None,
        feedrate: 'FeedRate' = None,
    ) -> "MotionPlatformStateMachine":
        registry = PositionRegistry.from_config_file(path)
        initial_descriptor = registry.find_first_of_type(PositionType.GLOBAL_READY)
        if not initial_descriptor:
            raise ValueError("Configuration must include a GLOBAL_READY position.")

        context_kwargs = dict(
            position_id=initial_descriptor.identifier,
            z_height_id=None,
            active_tool_id=None,
            payload_state=None,
            tool_states={},
            pending_move=None,
            engaged_ready_position_id=None,
            engaged_tool_id=None,
            metadata={},
            scale=scale
        )

        if context_overrides:
            context_kwargs.update(context_overrides)

        context = MotionContext(**context_kwargs)
        return cls(registry, machine, context=context, scale=scale, feedrate=feedrate)

    # ---------------------------------------------------------------------
    # Platform State Initialization
    # ---------------------------------------------------------------------
    
    def initialize_deck(self, deck_name: str = "weight_well_deck", config_path: str = "./jubilee_api_config"):
        """
        Initialize the deck with weight wells in each slot.
        
        Args:
            deck_name: Name of the deck configuration
            config_path: Path to the deck configuration files
        """
        from trickler_labware import Mold
        from science_jubilee.labware.Labware import Labware
        
        try:
            # Load the deck configuration
            self.context.deck = Deck(deck_name, path=config_path)
            
            # Load mold labware into each slot (18 slots total: 0-17)
            for i in range(18):
                try:
                    # Manual labware loading to work around bug in Deck.load_labware()
                    # which doesn't pass the path parameter to Labware constructor
                    labware = Labware("mold_labware", order="rows", path=config_path)
                    labware.add_slot(i)
                    offset = self.context.deck.slots[str(i)].offset
                    labware.offset = offset
                    
                    # Register labware with the slot
                    self.context.deck.slots[str(i)].has_labware = True
                    self.context.deck.slots[str(i)].labware = labware
                    self.context.deck.safe_z = labware.dimensions.get("zDimension", 10)
                    
                    for well_name in labware.wells.keys():
                        # Skip empty mold slot names
                        if not well_name or not isinstance(well_name, str):
                            continue
                        
                        # Extract numerical ID from mold slot name (e.g., "A0" -> "0", "A17" -> "17")
                        # This allows external API to use numerical IDs while labware uses letter+number format
                        # since labware internally uses A1, B1, B2... format
                        if well_name.startswith('A'):
                            numerical_id = well_name[1:]  # Strip the 'A' prefix
                        else:
                            numerical_id = well_name
                            
                        # Create state machine position name from numerical ID
                        # External API uses numerical IDs like "0", "1", "2", ... "17"
                        ready_pos = f"mold_ready_{numerical_id}"
                        
                        # Create a Mold with minimal required Well fields (coordinates not used)
                        # Note: Actual coordinates come from motion_platform_positions.json
                        mold = Mold(
                            # Required Well fields (dummy values since not used for movement)
                            name=numerical_id,  # Use numerical ID for external API
                            depth=0.0,
                            totalLiquidVolume=0.0,
                            shape="cylindrical",
                            x=0.0,
                            y=0.0,
                            z=0.0,
                            # Mold custom parameters
                            valid=True,
                            has_top_piston=False,
                            current_weight=0.0,
                            target_weight=0.0,
                            max_weight=None,
                            ready_pos=ready_pos  # State machine position name
                        )
                        
                        # Replace the regular well with our Mold
                        # Keep the labware well name format for internal consistency
                        labware.wells[well_name] = mold
                except Exception as e:
                    print(f"Error loading labware for slot {i}: {e}")
                    import traceback
                    traceback.print_exc()
                    raise
                
        except Exception as e:
            print(f"Error initializing deck: {e}")
            import traceback
            traceback.print_exc()
            self.context.deck = None
    
    def initialize_dispensers(self, num_piston_dispensers: int = 0, num_pistons_per_dispenser: int = 0):
        """
        Initialize piston dispensers.
        
        Args:
            num_piston_dispensers: Number of piston dispensers
            num_pistons_per_dispenser: Number of pistons in each dispenser
        """
        
        self.context.piston_dispensers = [
            PistonDispenser(i, num_pistons_per_dispenser) 
            for i in range(num_piston_dispensers)
        ]

    
    def get_mold_from_deck(self, well_id: str) -> Optional[object]:
        """
        Get a mold object from the deck by mold slot ID.
        
        Args:
            well_id: Mold slot identifier (numerical string "0" through "17")
            
        Returns:
            Mold object if found, None otherwise
        """
        if not self.context.deck:
            return None
        
        # Convert well_id to slot index (well_id is already numerical: "0", "1", ... "17")
        try:
            slot_index = int(well_id)
        except (ValueError, TypeError):
            return None
        
        # Validate slot index is within range (0-17 for 18 slots)
        if slot_index < 0 or slot_index > 17:
            return None
        
        if str(slot_index) in self.context.deck.slots:
            slot = self.context.deck.slots[str(slot_index)]
            if slot.has_labware and hasattr(slot.labware, 'wells'):
                # Convert numerical ID to labware well name format (e.g., "0" -> "A0")
                labware_well_name = f"A{well_id}"
                
                # Get the well matching the labware well name
                if labware_well_name in slot.labware.wells:
                    from trickler_labware import Mold
                    well = slot.labware.wells[labware_well_name]
                    if isinstance(well, Mold):
                        return well
        return None

    # ---------------------------------------------------------------------
    # Machine Access
    # ---------------------------------------------------------------------
    @property
    def machine(self) -> Machine:
        """Read-only access to machine for state queries (position, status, etc)."""
        return self._executor.machine

    # ---------------------------------------------------------------------
    # Validated Movement Methods
    # =====================================================================
    # These methods combine validation (state machine) and execution (executor).
    # This is the interface that Manipulator and other classes should use.
    # =====================================================================
    
    def validated_pick_mold(
        self,
        well_id: str,
        manipulator_config: Dict[str, object]
    ) -> MoveValidationResult:
        """
        Validate and execute picking up a mold from a mold slot.
        
        Args:
            well_id: Mold slot identifier (numerical string "0" through "17")
            manipulator_config: Configuration dict for the manipulator
        """
        from trickler_labware import Mold
        
        # Domain-specific validation
        if self.context.current_well is not None:
            return MoveValidationResult(
                valid=False,
                reason="Manipulator already carrying a mold"
            )
        
        if self.context.deck is None:
            return MoveValidationResult(
                valid=False,
                reason="Deck not configured"
            )
        
        well = self.get_mold_from_deck(well_id)
        if well is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Mold slot {well_id} not found"
            )
        
        if not isinstance(well, Mold):
            return MoveValidationResult(
                valid=False,
                reason="Invalid mold object"
            )
        
        if not well.valid:
            return MoveValidationResult(
                valid=False,
                reason="Mold is not valid"
            )
        
        if well.has_top_piston:
            return MoveValidationResult(
                valid=False,
                reason="Cannot pick up mold that already has a top piston"
            )
        
        # Get ready position coordinates for this mold slot
        ready_position_id = f"mold_ready_{well_id}"
        
        if not self._registry.has(ready_position_id):
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{ready_position_id}' not defined in configuration"
            )
        
        well_ready_pos = self._registry.get(ready_position_id)
        
        if not well_ready_pos.coordinates:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{ready_position_id}' does not have coordinates defined"
            )
        
        ready_coords = well_ready_pos.coordinates
        
        if ready_coords.x is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{ready_position_id}' missing X coordinate"
            )
        if ready_coords.y is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{ready_position_id}' missing Y coordinate"
            )
        if ready_coords.v is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{ready_position_id}' missing V coordinate"
            )
        
        # Resolve z coordinate if needed
        ready_z = None
        if ready_coords.z == "USE_Z_HEIGHT_POLICY":
            if not self.context.z_height_id:
                return MoveValidationResult(
                    valid=False,
                    reason="Z height policy required but z_height_id not set in context"
                )
            z_heights = self._registry.z_heights
            if self.context.z_height_id not in z_heights:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Z height '{self.context.z_height_id}' not found in configuration"
                )
            z_config = z_heights[self.context.z_height_id]
            if isinstance(z_config, dict):
                ready_z = z_config.get("z_coordinate")
            if ready_z is None:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Z coordinate not defined for z_height '{self.context.z_height_id}'"
                )
        elif ready_coords.z is not None:
            ready_z = ready_coords.z
        else:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{ready_position_id}' missing Z coordinate"
            )
        
        # Execute through generic validation framework
        result = self._validate_and_execute(
            action_id="pick_up_mold",
            execution_func=self._executor.execute_pick_mold,
            well_id=well_id,
            deck=self.context.deck,
            tamper_axis=manipulator_config.get('tamper_axis', 'V'),
            ready_x=ready_coords.x,
            ready_y=ready_coords.y,
            ready_z=ready_z,
            ready_v=ready_coords.v
        )
        
        # Update state machine state if successful
        if result.valid:
            self.context.current_well = well
            self.context.mold_on_scale = False
            if not well.has_top_piston:
                self.context.payload_state = "mold_without_top_piston"
            else:
                self.context.payload_state = "mold_with_top_piston"
        
        return result
    
    def validated_place_mold(
        self,
        well_id: str,
        manipulator_config: Optional[Dict[str, object]] = None
    ) -> MoveValidationResult:
        """
        Validate and execute placing a mold in a mold slot.
        
        Args:
            well_id: Well identifier (numerical string "0" through "17")
            manipulator_config: Configuration dict for the manipulator
        """
        # Domain-specific validation
        if self.context.current_well is None:
            return MoveValidationResult(
                valid=False,
                reason="Not carrying a mold"
            )
        
        if self.context.deck is None:
            return MoveValidationResult(
                valid=False,
                reason="Deck not configured"
            )
        
        # Get ready position coordinates for this mold slot
        ready_position_id = f"mold_ready_{well_id}"
        
        if not self._registry.has(ready_position_id):
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{ready_position_id}' not defined in configuration"
            )
        
        well_ready_pos = self._registry.get(ready_position_id)
        
        if not well_ready_pos.coordinates:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{ready_position_id}' does not have coordinates defined"
            )
        
        ready_coords = well_ready_pos.coordinates
        
        if ready_coords.x is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{ready_position_id}' missing X coordinate"
            )
        if ready_coords.y is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{ready_position_id}' missing Y coordinate"
            )
        if ready_coords.v is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{ready_position_id}' missing V coordinate"
            )
        
        # Resolve z coordinate if needed
        ready_z = None
        if ready_coords.z == "USE_Z_HEIGHT_POLICY":
            if not self.context.z_height_id:
                return MoveValidationResult(
                    valid=False,
                    reason="Z height policy required but z_height_id not set in context"
                )
            z_heights = self._registry.z_heights
            if self.context.z_height_id not in z_heights:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Z height '{self.context.z_height_id}' not found in configuration"
                )
            z_config = z_heights[self.context.z_height_id]
            if isinstance(z_config, dict):
                ready_z = z_config.get("z_coordinate")
            if ready_z is None:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Z coordinate not defined for z_height '{self.context.z_height_id}'"
                )
        elif ready_coords.z is not None:
            ready_z = ready_coords.z
        else:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{ready_position_id}' missing Z coordinate"
            )
        
        # Execute through generic validation framework
        result = self._validate_and_execute(
            action_id="put_down_mold",
            execution_func=self._executor.execute_place_mold,
            well_id=well_id,
            deck=self.context.deck,
            ready_x=ready_coords.x,
            ready_y=ready_coords.y,
            ready_z=ready_z,
            ready_v=ready_coords.v
        )
        
        # Update state machine state if successful
        if result.valid:
            self.context.current_well = None
            self.context.mold_on_scale = False
            self.context.payload_state = "empty"
        
        return result
    
    def validated_place_mold_on_scale(
        self,
        manipulator_config: Dict[str, object]
    ) -> MoveValidationResult:
        """Validate and execute placing mold on scale."""
        # Domain-specific validation
        if self.context.scale is None:
            return MoveValidationResult(
                valid=False,
                reason="Scale not configured"
            )
        
        if self.context.current_well is None:
            return MoveValidationResult(
                valid=False,
                reason="Not carrying a mold"
            )
        
        mold = self.context.current_well
        
        if mold.has_top_piston:
            return MoveValidationResult(
                valid=False,
                reason="Cannot place mold with piston on scale"
            )
        
        if self.context.mold_on_scale:
            return MoveValidationResult(
                valid=False,
                reason="Mold is already on scale"
            )
        
        # Get ready position coordinates from SCALE_READY position
        try:
            scale_ready_pos = self._registry.get("scale_ready")
        except KeyError:
            return MoveValidationResult(
                valid=False,
                reason="scale_ready position not defined in configuration"
            )
        
        if not scale_ready_pos.coordinates:
            return MoveValidationResult(
                valid=False,
                reason="scale_ready position does not have coordinates defined"
            )
        
        ready_coords = scale_ready_pos.coordinates
        
        if ready_coords.x is None:
            return MoveValidationResult(
                valid=False,
                reason="scale_ready position missing X coordinate"
            )
        if ready_coords.y is None:
            return MoveValidationResult(
                valid=False,
                reason="scale_ready position missing Y coordinate"
            )
        if ready_coords.v is None:
            return MoveValidationResult(
                valid=False,
                reason="scale_ready position missing V coordinate"
            )
        
        # Resolve z coordinate if needed
        ready_z = None
        if ready_coords.z == "USE_Z_HEIGHT_POLICY":
            if not self.context.z_height_id:
                return MoveValidationResult(
                    valid=False,
                    reason="Z height policy required but z_height_id not set in context"
                )
            z_heights = self._registry.z_heights
            if self.context.z_height_id not in z_heights:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Z height '{self.context.z_height_id}' not found in configuration"
                )
            z_config = z_heights[self.context.z_height_id]
            if isinstance(z_config, dict):
                ready_z = z_config.get("z_coordinate")
            if ready_z is None:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Z coordinate not defined for z_height '{self.context.z_height_id}'"
                )
        elif ready_coords.z is not None:
            ready_z = ready_coords.z
        else:
            return MoveValidationResult(
                valid=False,
                reason="SCALE_READY position missing Z coordinate"
            )
        
        # Execute through generic validation framework
        result = self._validate_and_execute(
            action_id="place_mold_on_scale",
            execution_func=self._executor.execute_place_mold_on_scale,
            tamper_axis=manipulator_config.get('tamper_axis', 'V'),
            ready_x=ready_coords.x,
            ready_y=ready_coords.y,
            ready_z=ready_z,
            ready_v=ready_coords.v
        )
        
        # Update state machine state if successful
        if result.valid:
            self.context.mold_on_scale = True
            # Update position to scale_active to reflect mold is now physically on the scale
            self.context.position_id = "scale_active"
        
        # Typically, state changes happen during _validate_and_execute,
        # but this is the only action that can engage the tool
        engagement_result = self.request_tool_engagement()
        if not engagement_result.valid:
            # Propagate engagement failure (movement already occurred)
            return engagement_result

        return result
    
    def validated_pick_mold_from_scale(
        self,
        manipulator_config: Dict[str, object]
    ) -> MoveValidationResult:
        """Validate and execute picking mold from scale."""
        # Domain-specific validation
        if self.context.scale is None:
            return MoveValidationResult(
                valid=False,
                reason="Scale not configured"
            )
        
        if self.context.current_well is None:
            return MoveValidationResult(
                valid=False,
                reason="Not carrying a mold"
            )
        
        if not self.context.mold_on_scale:
            return MoveValidationResult(
                valid=False,
                reason="Mold is not on scale"
            )
        
        # Get ready position coordinates from SCALE_READY position
        try:
            scale_ready_pos = self._registry.get("scale_ready")
        except KeyError:
            return MoveValidationResult(
                valid=False,
                reason="scale_ready position not defined in configuration"
            )
        
        if not scale_ready_pos.coordinates:
            return MoveValidationResult(
                valid=False,
                reason="SCALE_READY position does not have coordinates defined"
            )
        
        ready_coords = scale_ready_pos.coordinates
        
        if ready_coords.x is None:
            return MoveValidationResult(
                valid=False,
                reason="SCALE_READY position missing X coordinate"
            )
        if ready_coords.y is None:
            return MoveValidationResult(
                valid=False,
                reason="SCALE_READY position missing Y coordinate"
            )
        if ready_coords.v is None:
            return MoveValidationResult(
                valid=False,
                reason="SCALE_READY position missing V coordinate"
            )
        
        # Resolve z coordinate if needed
        ready_z = None
        if ready_coords.z == "USE_Z_HEIGHT_POLICY":
            if not self.context.z_height_id:
                return MoveValidationResult(
                    valid=False,
                    reason="Z height policy required but z_height_id not set in context"
                )
            z_heights = self._registry.z_heights
            if self.context.z_height_id not in z_heights:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Z height '{self.context.z_height_id}' not found in configuration"
                )
            z_config = z_heights[self.context.z_height_id]
            if isinstance(z_config, dict):
                ready_z = z_config.get("z_coordinate")
            if ready_z is None:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Z coordinate not defined for z_height '{self.context.z_height_id}'"
                )
        elif ready_coords.z is not None:
            ready_z = ready_coords.z
        else:
            return MoveValidationResult(
                valid=False,
                reason="SCALE_READY position missing Z coordinate"
            )
        
        # Execute through generic validation framework
        result = self._validate_and_execute(
            action_id="pick_mold_from_scale",
            execution_func=self._executor.execute_pick_mold_from_scale,
            tamper_axis=manipulator_config.get('tamper_axis', 'V'),
            ready_x=ready_coords.x,
            ready_y=ready_coords.y,
            ready_z=ready_z,
            ready_v=ready_coords.v
        )

        # Typically, state changes happen during _validate_and_execute,
        # but this is the only action that can disengage the tool
        disengagement_result = self.request_tool_disengagement()
        if not disengagement_result.valid:
            # Propagate engagement failure (movement already occurred)
            return disengagement_result
        
        # Update state machine state if successful
        if result.valid:
            self.context.mold_on_scale = False
            # Update position back to scale_ready after picking mold from scale
            self.context.position_id = "scale_ready"
            # Placing mold on scale shouldn't change payload_state, so don't update
        
        return result
    
    def validated_place_top_piston(
        self,
        piston_dispenser,
        manipulator_config: Dict[str, object]
    ) -> MoveValidationResult:
        """Validate and execute placing top piston."""
        # Domain-specific validation
        if self.context.current_well is None:
            return MoveValidationResult(
                valid=False,
                reason="Not carrying a mold"
            )
        
        mold = self.context.current_well
        
        if mold.has_top_piston:
            return MoveValidationResult(
                valid=False,
                reason="Mold already has a top piston"
            )
        
        if piston_dispenser.num_pistons == 0:
            return MoveValidationResult(
                valid=False,
                reason="No pistons available in dispenser"
            )
        
        if self.context.mold_on_scale:
            return MoveValidationResult(
                valid=False,
                reason="Cannot add top piston when mold is on scale"
            )
        
        # Get ready position coordinates for this dispenser
        dispenser_ready_id = f"dispenser_ready_{piston_dispenser.index}"
        
        if not self._registry.has(dispenser_ready_id):
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{dispenser_ready_id}' not defined in configuration"
            )
        
        dispenser_ready_pos = self._registry.get(dispenser_ready_id)
        
        if not dispenser_ready_pos.coordinates:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{dispenser_ready_id}' does not have coordinates defined"
            )
        
        ready_coords = dispenser_ready_pos.coordinates
        
        if ready_coords.x is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{dispenser_ready_id}' missing X coordinate"
            )
        if ready_coords.y is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{dispenser_ready_id}' missing Y coordinate"
            )
        if ready_coords.v is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{dispenser_ready_id}' missing V coordinate"
            )
        
        # Resolve z coordinate if needed
        ready_z = None
        if ready_coords.z == "USE_Z_HEIGHT_POLICY":
            if not self.context.z_height_id:
                return MoveValidationResult(
                    valid=False,
                    reason="Z height policy required but z_height_id not set in context"
                )
            z_heights = self._registry.z_heights
            if self.context.z_height_id not in z_heights:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Z height '{self.context.z_height_id}' not found in configuration"
                )
            z_config = z_heights[self.context.z_height_id]
            if isinstance(z_config, dict):
                ready_z = z_config.get("z_coordinate")
            if ready_z is None:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Z coordinate not defined for z_height '{self.context.z_height_id}'"
                )
        elif ready_coords.z is not None:
            ready_z = ready_coords.z
        else:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{dispenser_ready_id}' missing Z coordinate"
            )
        
        # Execute through generic validation framework
        result = self._validate_and_execute(
            action_id="retrieve_piston",
            execution_func=self._executor.execute_place_top_piston,
            piston_dispenser=piston_dispenser,
            tamper_axis=manipulator_config.get('tamper_axis', 'V'),
            dispenser_safe_z=manipulator_config.get('dispenser_safe_z', 254.0),
            ready_x=ready_coords.x,
            ready_y=ready_coords.y,
            ready_z=ready_z,
            ready_v=ready_coords.v
        )
        
        # Update state machine state if successful
        if result.valid:
            mold.has_top_piston = True
        
        return result
    
    def validated_tamp(
        self,
        manipulator_config: Dict[str, object]
    ) -> MoveValidationResult:
        """Validate and execute tamping action."""
        # TODO: This function is incomplete and shouldn't be used, scale.y is defunct.
        # Domain-specific validation
        if self.context.scale is None:
            return MoveValidationResult(
                valid=False,
                reason="Scale not configured"
            )
        
        if self.context.current_well is None:
            return MoveValidationResult(
                valid=False,
                reason="Not carrying a mold"
            )
        
        if not self.context.mold_on_scale:
            return MoveValidationResult(
                valid=False,
                reason="Mold must be on scale to tamp"
            )
        
        mold = self.context.current_well
        if mold.has_top_piston:
            return MoveValidationResult(
                valid=False,
                reason="Cannot tamp mold that has a top piston"
            )
        
        if not hasattr(self.context.scale, 'y') or self.context.scale.y is None:
            return MoveValidationResult(
                valid=False,
                reason="Scale Y coordinate not configured"
            )
        
        # Execute through generic validation framework
        return self._validate_and_execute(
            action_id="tamp_mold",
            execution_func=self._executor.execute_tamp,
            tamper_axis=manipulator_config.get('tamper_axis', 'V'),
            scale_y=self.context.scale.y
        )
    
    # ---------------------------------------------------------------------
    # Generic Validation and Execution
    # ---------------------------------------------------------------------
    
    def _validate_and_execute(
        self,
        target_position_id: Optional[str] = None,
        action_id: Optional[str] = None,
        additional_requirements: Optional[Dict[str, object]] = None,
        execution_func=None,
        **execution_kwargs
    ) -> MoveValidationResult:
        """
        Generic validation and execution for movements and tool actions.
        
        This method performs comprehensive validation for either:
        - Position movements (when target_position_id is provided)
        - Tool actions (when action_id is provided)
        
        Validation steps for MOVEMENTS:
        1. Checks state machine is not already moving
        2. Validates position transition is allowed (current → target)
        3. Validates machine is actually at expected current position
        4. Validates z-height policy for target position
        5. Validates all requirements for target position
        6. If valid, executes the provided function and transitions position
        
        Validation steps for ACTIONS:
        1. Checks state machine is not already moving
        2. Validates action exists in registry
        3. Validates tool engagement state (if required/blocked)
        4. Validates required tool ID matches
        5. Validates position scope (action allowed at current position)
        6. Validates action requirements and excludes
        7. If valid, executes the provided function (no position change)
        
        Args:
            target_position_id: The target position identifier (for movements)
            action_id: The action identifier (for tool actions)
            additional_requirements: Extra requirements beyond position/action requirements
            execution_func: Function to execute if validation passes
            **execution_kwargs: Arguments to pass to execution function
            
        Returns:
            MoveValidationResult with validation outcome
            
        Raises:
            ValueError: If both or neither target_position_id and action_id are provided
        """
        # Validate that exactly one of target_position_id or action_id is provided
        if (target_position_id is None) == (action_id is None):
            raise ValueError(
                "Must provide exactly one of 'target_position_id' (for movements) "
                "or 'action_id' (for actions)"
            )
        
        # Step 1: Check state machine state
        if self.current_state == self.moving:
            return MoveValidationResult(
                valid=False,
                reason="Already executing a move. Wait for current move to complete."
            )
        
        # Step 1.5: Verify all axes are homed (exempt homing actions)
        homing_actions = {'home_all', 'home_manipulator', 'home_trickler'}
        if action_id not in homing_actions:
            axes_homed = self._executor.get_machine_axes_homed()
            axis_names = ['X', 'Y', 'Z', 'U', 'V']
            not_homed = [axis_names[i] for i in range(len(axes_homed)) if i < len(axis_names) and not axes_homed[i]]
            if not_homed:
                return MoveValidationResult(
                    valid=False,
                    reason=f"All axes must be homed before performing moves/actions. Unhomed axes: {', '.join(not_homed)}"
                )
        
        # Route to appropriate validation based on whether it's a movement or action
        if target_position_id is not None:
            return self._validate_and_execute_move(
                target_position_id=target_position_id,
                additional_requirements=additional_requirements,
                execution_func=execution_func,
                **execution_kwargs
            )
        else:  # action_id is provided
            return self._validate_and_execute_action(
                action_id=action_id,
                additional_requirements=additional_requirements,
                execution_func=execution_func,
                **execution_kwargs
            )
    
    def _validate_and_execute_move(
        self,
        target_position_id: str,
        additional_requirements: Optional[Dict[str, object]] = None,
        execution_func=None,
        **execution_kwargs
    ) -> MoveValidationResult:
        """
        Internal method to validate and execute position movements.
        
        See _validate_and_execute() for full documentation.
        """
        # Step 2: Validate position transition
        try:
            target_descriptor = self._registry.get(target_position_id)
        except KeyError:
            return MoveValidationResult(
                valid=False,
                reason=f"Unknown target position '{target_position_id}'."
            )
        
        try:
            current_descriptor = self._registry.get(self.context.position_id)
        except KeyError:
            return MoveValidationResult(
                valid=False,
                reason=f"Current position '{self.context.position_id}' is not registered."
            )
        
        # Check if transition is allowed
        if target_position_id not in current_descriptor.allowed_destinations:
            allowed = self._format_options(current_descriptor.allowed_destinations)
            return MoveValidationResult(
                valid=False,
                reason=(
                    f"Cannot move from '{self.context.position_id}' to "
                    f"'{target_position_id}'. Allowed destinations: {allowed}."
                )
            )
        
        if self.context.position_id not in target_descriptor.allowed_origins:
            allowed_origins = self._format_options(target_descriptor.allowed_origins)
            return MoveValidationResult(
                valid=False,
                reason=(
                    f"'{target_position_id}' cannot accept moves from "
                    f"'{self.context.position_id}'. Allowed origins: {allowed_origins}."
                )
            )
        
        # Step 3: Validate machine is at expected current position
        current_pos = self._executor.get_machine_position()
        machine_validation = self.validate_machine_state(
            machine_x=float(current_pos.get('X', 0)),
            machine_y=float(current_pos.get('Y', 0)),
            machine_z=float(current_pos.get('Z', 0)),
            machine_v=float(current_pos.get('V', 0))
        )
        if not machine_validation.valid:
            return machine_validation
        
        # Step 4: Validate z-height policy
        z_height_issue = target_descriptor.z_height_policy.validate(self.context.z_height_id)
        if z_height_issue:
            return MoveValidationResult(valid=False, reason=z_height_issue)
        
        # Step 5: Validate position requirements
        requirement_issue = self._validate_requirements(target_descriptor.requirements)
        if requirement_issue:
            return MoveValidationResult(valid=False, reason=requirement_issue)
        
        # Step 6: Validate additional requirements (if provided)
        if additional_requirements:
            requirement_issue = self._validate_requirements(additional_requirements)
            if requirement_issue:
                return MoveValidationResult(valid=False, reason=requirement_issue)
        
        # Step 7: Execute if validation passed
        if execution_func:
            try:
                # Create move request and transition to moving state
                request = MoveRequest(target_position_id=target_position_id)
                self.context.pending_move = request
                self.begin_motion()
                
                # Execute the movement
                result = execution_func(**execution_kwargs)
                
                # Complete the move (updates position)
                self.complete_move(tool_still_engaged=False)
                
                # Return result (True/False from executor becomes valid/invalid)
                if result is False:
                    return MoveValidationResult(
                        valid=False,
                        reason="Execution returned False"
                    )
                
                return MoveValidationResult(valid=True)
                
            except Exception as e:
                # Abort the move on exception
                if self.current_state == self.moving:
                    self.abort_motion()
                return MoveValidationResult(
                    valid=False,
                    reason=f"Execution failed: {str(e)}"
                )
        
        # If no execution function, just return validation result
        return MoveValidationResult(valid=True)
    
    def _validate_and_execute_action(
        self,
        action_id: str,
        additional_requirements: Optional[Dict[str, object]] = None,
        execution_func=None,
        **execution_kwargs
    ) -> MoveValidationResult:
        """
        Internal method to validate and execute tool actions.
        
        All actions must be defined in the registry (config JSON).
        
        See _validate_and_execute_move() for full documentation.
        """
        # Step 2: Validate action exists
        descriptor = self._actions.get(action_id)
        if descriptor is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Unknown action '{action_id}'."
            )
        
        # Step 3: Validate tool engagement state
        if descriptor.requires_tool_engaged and self.current_state != self.tool_engaged:
            return MoveValidationResult(
                valid=False,
                reason=f"Action '{action_id}' requires the tool to be engaged."
            )
        
        if descriptor.blocked_when_engaged and self.current_state == self.tool_engaged:
            return MoveValidationResult(
                valid=False,
                reason=(
                    f"Action '{action_id}' cannot be performed while tool is engaged. "
                    f"Tool must be disengaged first."
                )
            )
        
        # Step 4: Validate required tool ID
        if descriptor.required_tool_id:
            if self.context.active_tool_id != descriptor.required_tool_id:
                return MoveValidationResult(
                    valid=False,
                    reason=(
                        f"Action '{action_id}' requires tool '{descriptor.required_tool_id}'. "
                        f"Current tool: '{self.context.active_tool_id}'."
                    )
                )
        
        # Step 5: Validate position scope
        if descriptor.position_scope:
            reference_position = (
                self.context.engaged_ready_position_id
                if self.current_state == self.tool_engaged
                else self.context.position_id
            )
            if reference_position not in descriptor.position_scope:
                allowed = self._format_options(descriptor.position_scope)
                return MoveValidationResult(
                    valid=False,
                    reason=(
                        f"Action '{action_id}' only permitted at: {allowed}. "
                        f"Current position: '{reference_position}'."
                    )
                )
        
        # Step 6: Validate machine is at expected current position
        current_pos = self._executor.get_machine_position()
        machine_validation = self.validate_machine_state(
            machine_x=float(current_pos.get('X', 0)),
            machine_y=float(current_pos.get('Y', 0)),
            machine_z=float(current_pos.get('Z', 0)),
            machine_v=float(current_pos.get('V', 0))
        )
        if not machine_validation.valid:
            return machine_validation
        
        # Step 7: Validate action requirements
        requirement_issue = self._validate_requirements(descriptor.requirements)
        if requirement_issue:
            return MoveValidationResult(valid=False, reason=requirement_issue)
        
        # Step 8: Validate action excludes
        exclude_issue = self._validate_excludes(descriptor.excludes)
        if exclude_issue:
            return MoveValidationResult(valid=False, reason=exclude_issue)
        
        # Step 9: Validate additional requirements (if provided)
        if additional_requirements:
            requirement_issue = self._validate_requirements(additional_requirements)
            if requirement_issue:
                return MoveValidationResult(valid=False, reason=requirement_issue)
        
        # Step 10: Execute if validation passed
        if execution_func:
            try:
                # Actions don't change position, so no state transition needed
                # Execute the action
                result = execution_func(**execution_kwargs)
                
                # Return result
                if result is False or result is None:
                    return MoveValidationResult(
                        valid=False,
                        reason="Execution returned False"
                    )
                
                return MoveValidationResult(valid=True)
                
            except Exception as e:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Execution failed: {str(e)}"
                )
        # If no execution function, just return validation result
        return MoveValidationResult(valid=True)
    
    # ---------------------------------------------------------------------
    # Validated Methods for JubileeManager Operations
    # ---------------------------------------------------------------------
    
    def validated_move_to_mold_slot(
        self,
        well_id: str
    ) -> MoveValidationResult:
        """
        Validate and execute movement to a specific mold slot.
        
        Args:
            well_id: Mold slot identifier (numerical string "0" through "17")
            
        Returns:
            MoveValidationResult with outcome
        """
        # Use state machine's deck
        deck = self.context.deck
        if deck is None:
            return MoveValidationResult(
                valid=False,
                reason="Deck not configured"
            )
        
        # Get mold from state machine's deck
        well = self.get_mold_from_deck(well_id)
        
        # Determine target position from mold's ready_pos if available, otherwise construct from mold slot ID
        if well and hasattr(well, 'ready_pos') and well.ready_pos:
            target_position = well.ready_pos
        else:
            # Fallback: construct from mold slot ID
            target_position = f"mold_ready_{well_id}"
        
        # If position not in registry, return error
        if not self._registry.has(target_position):
            return MoveValidationResult(
                valid=False,
                reason="Could not find mold ready position"
            )
        
        # Get coordinates from registry for this position
        position_descriptor = self._registry.get(target_position)
        if not position_descriptor.coordinates:
            return MoveValidationResult(
                valid=False,
                reason=f"Position '{target_position}' has no coordinates defined"
            )
        
        coords = position_descriptor.coordinates
        
        # Execute move using coordinates from motion_platform_positions.json
        return self._validate_and_execute_move(
            target_position_id=target_position,
            execution_func=self._executor.execute_move_to_mold_slot,
            x=coords.x,
            y=coords.y,
            z=coords.z,
            v=coords.v,
            registry=self._registry
        )
    
    def validated_move_to_scale(
        self
    ) -> MoveValidationResult:
        """
        Validate and execute movement to the scale.
        
        Returns:
            MoveValidationResult with outcome
        """
        if self.context.scale is None:
            return MoveValidationResult(
                valid=False,
                reason="Scale not configured"
            )
        
        # Get ready position coordinates from SCALE_READY position
        try:
            scale_ready_pos = self._registry.get("scale_ready")
        except KeyError:
            return MoveValidationResult(
                valid=False,
                reason="scale_ready position not defined in configuration"
            )
        
        if not scale_ready_pos.coordinates:
            return MoveValidationResult(
                valid=False,
                reason="SCALE_READY position does not have coordinates defined"
            )
        
        ready_coords = scale_ready_pos.coordinates
        
        # Validate required coordinates exist
        if ready_coords.x is None:
            return MoveValidationResult(
                valid=False,
                reason="SCALE_READY position missing X coordinate"
            )
        if ready_coords.y is None:
            return MoveValidationResult(
                valid=False,
                reason="SCALE_READY position missing Y coordinate"
            )
        if ready_coords.v is None:
            return MoveValidationResult(
                valid=False,
                reason="SCALE_READY position missing V coordinate"
            )
        
        # Resolve z coordinate if needed
        ready_z = None
        if ready_coords.z == "USE_Z_HEIGHT_POLICY":
            if not self.context.z_height_id:
                return MoveValidationResult(
                    valid=False,
                    reason="Z height policy required but z_height_id not set in context"
                )
            z_heights = self._registry.z_heights
            if self.context.z_height_id not in z_heights:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Z height '{self.context.z_height_id}' not found in configuration"
                )
            z_config = z_heights[self.context.z_height_id]
            if isinstance(z_config, dict):
                ready_z = z_config.get("z_coordinate")
            if ready_z is None:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Z coordinate not defined for z_height '{self.context.z_height_id}'"
                )
        elif ready_coords.z is not None:
            ready_z = ready_coords.z
        else:
            return MoveValidationResult(
                valid=False,
                reason="SCALE_READY position missing Z coordinate"
            )
        
        return self._validate_and_execute_move(
            target_position_id="scale_ready",
            execution_func=self._executor.execute_move_to_scale_location,
            ready_x=ready_coords.x,
            ready_y=ready_coords.y,
            ready_z=ready_z,
            ready_v=ready_coords.v
        )
    
    def validated_move_to_dispenser(
        self,
        piston_dispenser
    ) -> MoveValidationResult:
        """
        Validate and execute movement to a dispenser ready position.
        
        Args:
            piston_dispenser: PistonDispenser object with ready_pos attribute
            
        Returns:
            MoveValidationResult with outcome
        """
        # Get target position from dispenser's ready_pos
        target_position = piston_dispenser.ready_pos
        
        # Get coordinates from registry
        if not self._registry.has(target_position):
            return MoveValidationResult(
                valid=False,
                reason=f"Dispenser ready position '{target_position}' not defined in configuration"
            )
        
        position_descriptor = self._registry.get(target_position)
        if not position_descriptor.coordinates:
            return MoveValidationResult(
                valid=False,
                reason=f"Position '{target_position}' has no coordinates defined"
            )
        
        coords = position_descriptor.coordinates
        
        # Execute move using coordinates from motion_platform_positions.json
        return self._validate_and_execute_move(
            target_position_id=target_position,
            execution_func=self._executor.execute_move_to_position,
            x=coords.x,
            y=coords.y,
            z=coords.z, # TODO: Update to Z_HEIGHT_POLICY instead of hardcoded position
            v=coords.v
        )
    
    def validated_dispense_powder(
        self,
        target_weight: float
    ) -> MoveValidationResult:
        """
        Validate and execute powder dispensing.
        
        Args:
            target_weight: Target weight to dispense
            
        Returns:
            MoveValidationResult with outcome
        """
        # Domain-specific validation
        if self.context.position_id != "scale_active":
            return MoveValidationResult(
                valid=False,
                reason=f"Must be at scale_active position to dispense. Current: {self.context.position_id}"
            )
        
        if not self.context.mold_on_scale:
            return MoveValidationResult(
                valid=False,
                reason="Mold must be on scale before dispensing powder"
            )

        # Execute through generic validation framework
        return self._validate_and_execute(
            action_id="trickler_dispense",
            execution_func=self._executor.execute_dispense_powder,
            target_weight=target_weight
        )
    
    def validated_home_tamper(
        self,
        tamper_axis: str = 'V'
    ) -> MoveValidationResult:
        """
        Validate and execute tamper homing (uses home_manipulator action).
        
        Args:
            tamper_axis: Axis letter for tamper (default 'V')
            
        Returns:
            MoveValidationResult with outcome
        """
        # No domain-specific validation needed for homing
        # Execute through generic validation framework using home_manipulator action
        return self._validate_and_execute(
            action_id="home_manipulator",
            execution_func=self._executor.execute_home_tamper,
            tamper_axis=tamper_axis
        )
    
    def validated_home_all(
        self
    ) -> MoveValidationResult:
        """
        Validate and execute homing for all axes (X, Y, Z, U).
        
        This action can be conducted from any position, but requires:
        - No tool picked up (active_tool_id should not be "manipulator")
        - No mold (payload_state should be "empty")
        
        Returns machine to global_ready position after homing.
        
        Returns:
            MoveValidationResult with outcome
        """
        result = self._validate_and_execute(
            action_id="home_all",
            execution_func=self._executor.execute_home_all,
            registry=self._registry
        )
        
        # If successful, update context to reflect position change to global_ready
        if result.valid:
            global_ready_pos = self._registry.find_first_of_type(PositionType.GLOBAL_READY)
            if global_ready_pos:
                self.context.position_id = global_ready_pos.identifier
                # Set z_height to mold_transfer_safe (default after homing)
                self.context.z_height_id = "mold_transfer_safe"
        
        return result
    
    def validated_home_manipulator(
        self,
        manipulator_axis: str = 'V'
    ) -> MoveValidationResult:
        """
        Validate and execute homing for the manipulator axis (V).
        
        Requires no mold picked up (payload_state should be "empty").
        
        Args:
            manipulator_axis: Axis letter for manipulator (default 'V')
            
        Returns:
            MoveValidationResult with outcome
        """
        return self._validate_and_execute(
            action_id="home_manipulator",
            execution_func=self._executor.execute_home_manipulator,
            manipulator_axis=manipulator_axis
        )
    
    def validated_home_trickler(
        self,
        trickler_axis: str = 'W'
    ) -> MoveValidationResult:
        """
        Validate and execute homing for the trickler axis (W).
        
        Can be homed at any time with no requirements.
        
        Args:
            trickler_axis: Axis letter for trickler (default 'W')
            
        Returns:
            MoveValidationResult with outcome
        """
        return self._validate_and_execute(
            action_id="home_trickler",
            execution_func=self._executor.execute_home_trickler,
            trickler_axis=trickler_axis
        )
    
    def validated_pickup_tool(
        self,
        tool
    ) -> MoveValidationResult:
        """
        Validate and execute picking up a tool.
        
        Valid from mold_ready or global_ready positions. Requires no tool already
        picked up and mold_transfer_safe z_height. Returns to global_ready position.
        Only manipulator tool is currently supported.
        
        Note: The machine's pickup_tool() method is decorated with @requires_safe_z,
        which automatically raises the bed height to deck.safe_z + 20 if it is not
        already at that height.
        
        Args:
            tool: The Tool object to pick up (must be manipulator)
            
        Returns:
            MoveValidationResult with outcome
        """
        # Validate tool is manipulator
        if not hasattr(tool, 'name') or tool.name != "manipulator":
            return MoveValidationResult(
                valid=False,
                reason=f"Only manipulator tool is supported. Attempted to pick up: {tool.name if hasattr(tool, 'name') else type(tool).__name__}"
            )
        
        # Validate and execute the action
        result = self._validate_and_execute(
            action_id="pickup_tool",
            execution_func=self._executor.execute_pickup_tool,
            tool=tool,
            registry=self._registry
        )
        
        # If successful, update context to reflect tool pickup and position change
        if result.valid:
            # Update active tool
            self.context.active_tool_id = "manipulator"
            # Update position to global_ready
            global_ready_pos = self._registry.find_first_of_type(PositionType.GLOBAL_READY)
            if global_ready_pos:
                self.context.position_id = global_ready_pos.identifier
                # Set z_height to mold_transfer_safe
                self.context.z_height_id = "mold_transfer_safe"
        
        return result
    
    def validated_park_tool(
        self
    ) -> MoveValidationResult:
        """
        Validate and execute parking the current tool.
        
        Valid from global_ready position. Requires manipulator tool to be active.
        Returns to global_ready position.
        
        Note: The machine's park_tool() method is decorated with @requires_safe_z,
        which automatically raises the bed height to deck.safe_z + 20 if it is not
        already at that height.
        
        Returns:
            MoveValidationResult with outcome
        """
        # Validate and execute the action
        result = self._validate_and_execute(
            action_id="park_tool",
            execution_func=self._executor.execute_park_tool,
            registry=self._registry
        )
        
        # If successful, update context to reflect tool parking
        if result.valid:
            # Clear active tool
            self.context.active_tool_id = None
            # Position should already be at global_ready (executor handles this)
            # Ensure z_height is set appropriately
            self.context.z_height_id = "mold_transfer_safe"
        
        return result
    
    def validated_retrieve_piston(
        self,
        piston_dispenser,
        manipulator_config: Dict[str, object]
    ) -> MoveValidationResult:
        """
        Validate and execute retrieving a piston from a dispenser.
        This action retrieves the piston, partially inserts it, and then returns
        to ready position.
        
        Requires:
        - Manipulator tool to be active
        - Mold without top piston (payload_state: mold_without_top_piston)
        - Must start from the corresponding dispenser_ready position for that dispenser
        
        Args:
            piston_dispenser: The PistonDispenser object to retrieve from
            manipulator_config: Configuration dict for the manipulator
            
        Returns:
            MoveValidationResult with outcome
        """
        # Validate that we're at the correct dispenser position
        expected_position = f"dispenser_ready_{piston_dispenser.index}"
        if self.context.position_id != expected_position:
            return MoveValidationResult(
                valid=False,
                reason=f"Must be at {expected_position} to retrieve piston from dispenser {piston_dispenser.index}. Current position: {self.context.position_id}"
            )
        
        if self.context.current_well is None:
            return MoveValidationResult(
                valid=False,
                reason="Not carrying a mold"
            )
        
        mold = self.context.current_well
        
        if mold.has_top_piston:
            return MoveValidationResult(
                valid=False,
                reason="Mold already has a top piston"
            )
        
        if piston_dispenser.num_pistons == 0:
            return MoveValidationResult(
                valid=False,
                reason="No pistons available in dispenser"
            )
        
        if self.context.mold_on_scale:
            return MoveValidationResult(
                valid=False,
                reason="Cannot add top piston when mold is on scale"
            )
        
        # Get ready position coordinates for this dispenser
        dispenser_ready_id = f"dispenser_ready_{piston_dispenser.index}"
        
        # Try to get the specific dispenser's ready position
        if not self._registry.has(dispenser_ready_id):
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{dispenser_ready_id}' not defined in configuration"
            )
        
        dispenser_ready_pos = self._registry.get(dispenser_ready_id)
        
        if not dispenser_ready_pos.coordinates:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{dispenser_ready_id}' does not have coordinates defined"
            )
        
        ready_coords = dispenser_ready_pos.coordinates
        
        # Validate required coordinates exist
        if ready_coords.x is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{dispenser_ready_id}' missing X coordinate"
            )
        if ready_coords.y is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{dispenser_ready_id}' missing Y coordinate"
            )
        if ready_coords.v is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{dispenser_ready_id}' missing V coordinate"
            )
        
        # Resolve z coordinate if needed
        ready_z = None
        if ready_coords.z == "USE_Z_HEIGHT_POLICY":
            if not self.context.z_height_id:
                return MoveValidationResult(
                    valid=False,
                    reason="Z height policy required but z_height_id not set in context"
                )
            z_heights = self._registry.z_heights
            if self.context.z_height_id not in z_heights:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Z height '{self.context.z_height_id}' not found in configuration"
                )
            z_config = z_heights[self.context.z_height_id]
            if isinstance(z_config, dict):
                ready_z = z_config.get("z_coordinate")
            if ready_z is None:
                return MoveValidationResult(
                    valid=False,
                    reason=f"Z coordinate not defined for z_height '{self.context.z_height_id}'"
                )
        elif ready_coords.z is not None:
            ready_z = ready_coords.z
        else:
            return MoveValidationResult(
                valid=False,
                reason=f"Ready position '{dispenser_ready_id}' missing Z coordinate"
            )
        
        # Validate and execute the action through the state machine
        result = self._validate_and_execute(
            action_id="retrieve_piston",
            execution_func=self._executor.execute_place_top_piston,
            piston_dispenser=piston_dispenser,
            tamper_axis=manipulator_config.get('tamper_axis', 'V'),
            dispenser_safe_z=manipulator_config.get('dispenser_safe_z', 254.0),
            ready_x=ready_coords.x,
            ready_y=ready_coords.y,
            ready_z=ready_z,
            ready_v=ready_coords.v
        )
        
        if result.valid:
            mold.has_top_piston = True
            piston_dispenser.remove_piston()
        
        return result

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def request_move(self, request: MoveRequest) -> MoveValidationResult:
        """
        Evaluate and, if permissible, initiate a move or action.

        If the request references an action, the FSM validates the action without
        changing state. Otherwise, the FSM transitions into the moving state and
        records the pending move for completion tracking.
        """
        if request.action:
            return self.perform_action(request.action)

        if self.current_state == self.moving:
            return MoveValidationResult(valid=False, reason="Already executing a move.")

        validation = self.validate_move(request)
        if not validation.valid:
            return validation

        self.context.pending_move = request
        self.begin_motion()
        return validation

    def perform_action(self, action_id: str) -> MoveValidationResult:
        """Validate whether an auxiliary action is permitted."""
        descriptor = self._actions.get(action_id)
        if descriptor is None:
            return MoveValidationResult(valid=False, reason=f"Unknown action '{action_id}'.")

        # Check if action requires tool engagement (e.g., trickler_dispense)
        if descriptor.requires_tool_engaged and self.current_state != self.tool_engaged:
            return MoveValidationResult(
                valid=False,
                reason=f"Action '{action_id}' requires the tool to be engaged.",
            )

        # Check if action is blocked when tool is engaged (most actions)
        if descriptor.blocked_when_engaged and self.current_state == self.tool_engaged:
            return MoveValidationResult(
                valid=False,
                reason=(
                    f"Action '{action_id}' cannot be performed while tool is engaged. "
                    f"Tool must be disengaged first."
                ),
            )

        if descriptor.required_tool_id:
            if self.context.active_tool_id != descriptor.required_tool_id:
                return MoveValidationResult(
                    valid=False,
                    reason=(
                        f"Action '{action_id}' requires tool '{descriptor.required_tool_id}'. "
                        f"Current tool: '{self.context.active_tool_id}'."
                    ),
                )

        if descriptor.position_scope:
            reference_position = (
                self.context.engaged_ready_position_id
                if self.current_state == self.tool_engaged
                else self.context.position_id
            )
            if reference_position not in descriptor.position_scope:
                allowed = self._format_options(descriptor.position_scope)
                return MoveValidationResult(
                    valid=False,
                    reason=(
                        f"Action '{action_id}' only permitted at: {allowed}. "
                        f"Current position: '{reference_position}'."
                    ),
                )
        else:
            raise RuntimeError("Descriptor corrupt. Position scope not found.")

        requirement_issue = self._validate_requirements(descriptor.requirements)
        if requirement_issue:
            return MoveValidationResult(valid=False, reason=requirement_issue)

        exclude_issue = self._validate_excludes(descriptor.excludes)
        if exclude_issue:
            return MoveValidationResult(valid=False, reason=exclude_issue)

        return MoveValidationResult(valid=True)

    def validate_move(self, request: MoveRequest) -> MoveValidationResult:
        """
        Core validation hook for requested moves.

        This implementation verifies:
          * The target position exists in the registry.
          * The transition between current and target positions is permitted.
          * Z-height and contextual requirements are satisfied.
          * Engaged tools remain constrained to their ready points.
        """
        try:
            target_descriptor = self._registry.get(request.target_position_id)
        except KeyError:
            return MoveValidationResult(
                valid=False,
                reason=f"Unknown target position '{request.target_position_id}'.",
            )

        try:
            current_descriptor = self._registry.get(self.context.position_id)
        except KeyError:
            return MoveValidationResult(
                valid=False,
                reason=f"Current position '{self.context.position_id}' is not registered.",
            )

        if self.current_state == self.tool_engaged:
            if request.target_position_id != self.context.position_id:
                return MoveValidationResult(
                    valid=False,
                    reason="Cannot leave the ready point while the tool is engaged.",
                )
        else:
            if request.target_position_id not in current_descriptor.allowed_destinations:
                allowed = self._format_options(current_descriptor.allowed_destinations)
                return MoveValidationResult(
                    valid=False,
                    reason=(
                        f"Cannot move from '{self.context.position_id}' to "
                        f"'{request.target_position_id}'. Allowed destinations: {allowed}."
                    ),
                )

            if self.context.position_id not in target_descriptor.allowed_origins:
                allowed_origins = self._format_options(target_descriptor.allowed_origins)
                return MoveValidationResult(
                    valid=False,
                    reason=(
                        f"'{request.target_position_id}' cannot accept moves from "
                        f"'{self.context.position_id}'. Allowed origins: {allowed_origins}."
                    ),
                )

        if self.current_state != self.tool_engaged:
            z_height_issue = target_descriptor.z_height_policy.validate(self.context.z_height_id)
            if z_height_issue:
                return MoveValidationResult(valid=False, reason=z_height_issue)

        requirement_issue = self._validate_requirements(target_descriptor.requirements)
        if requirement_issue:
            return MoveValidationResult(valid=False, reason=requirement_issue)

        return MoveValidationResult(valid=True)

    def complete_move(self, *, tool_still_engaged: bool) -> None:
        """
        Finalize a move previously initiated via `request_move`.

        Args:
            tool_still_engaged: Indicates whether the tool engagement status
                should keep the FSM in the tool_engaged state after the move.
        """
        if not self.context.pending_move:
            raise RuntimeError("Cannot complete move when no pending move is recorded.")

        target_position = self._registry.get(self.context.pending_move.target_position_id)
        self.context.position_id = target_position.identifier

        if tool_still_engaged:
            self.context.engaged_ready_position_id = target_position.identifier
            if not self.context.engaged_tool_id:
                self.context.engaged_tool_id = self.context.active_tool_id
            self.complete_motion_with_tool()
        else:
            self._assert_engagement_exit_ready()
            self.complete_motion()
            self.context.engaged_ready_position_id = None
            self.context.engaged_tool_id = None

        self.context.pending_move = None

    def request_tool_engagement(self) -> MoveValidationResult:
        """Attempt to transition from idle to tool engaged state at the current position."""
        if self.current_state != self.idle:
            return MoveValidationResult(
                valid=False,
                reason="Tool engagement is only permitted while idle at a ready point.",
            )

        descriptor = self._registry.get(self.context.position_id)
        if not descriptor.allows_tool_engagement:
            return MoveValidationResult(
                valid=False,
                reason=f"Tool engagement is not permitted at '{descriptor.identifier}'.",
            )

        requirements = descriptor.engagement_requirements or descriptor.requirements
        requirement_issue = self._validate_requirements(requirements)
        if requirement_issue:
            return MoveValidationResult(valid=False, reason=requirement_issue)

        self.engage_tool()
        self.context.engaged_ready_position_id = descriptor.identifier
        self.context.engaged_tool_id = self.context.active_tool_id
        return MoveValidationResult(valid=True)

    def request_tool_disengagement(self) -> MoveValidationResult:
        """Attempt to disengage the tool and return to idle."""
        if self.current_state != self.tool_engaged:
            return MoveValidationResult(valid=False, reason="No tool is currently engaged.")

        if not self.context.engaged_ready_position_id:
            return MoveValidationResult(
                valid=False,
                reason="Engaged ready position is unknown; cannot disengage safely.",
            )

        descriptor = self._registry.get(self.context.engaged_ready_position_id)
        requirements = descriptor.engagement_requirements or descriptor.requirements
        requirement_issue = self._validate_requirements(requirements)
        if requirement_issue:
            return MoveValidationResult(valid=False, reason=requirement_issue)

        self.disengage_tool()
        self.context.engaged_ready_position_id = None
        self.context.engaged_tool_id = None
        return MoveValidationResult(valid=True)

    def register_tool(self, tool_status: ToolStatus) -> None:
        """Introduce or update a tool within the motion context."""
        self.context.tool_states[tool_status.tool_id] = tool_status

    def update_tool_engagement(self, tool_id: str, engaged: bool) -> None:
        """Update the engagement flag for a specific tool."""
        if tool_id not in self.context.tool_states:
            raise KeyError(f"Tool '{tool_id}' is not registered.")
        self.context.tool_states[tool_id].engaged = engaged

    def update_context(
        self,
        *,
        active_tool_id: Optional[str] = None,
        payload_state: Optional[str] = None,
        z_height_id: Optional[str] = None
    ) -> None:
        """Convenience helper to mutate commonly updated context properties."""
        if active_tool_id is not None:
            self.context.active_tool_id = active_tool_id
        if payload_state is not None:
            self.context.payload_state = payload_state
        if z_height_id is not None:
            self.context.z_height_id = z_height_id
    
    def validate_machine_state(
        self,
        machine_x: float,
        machine_y: float,
        machine_z: float,
        machine_v: float,
    ) -> MoveValidationResult:
        """
        Validate that the machine's physical coordinates match the FSM's expected position.
        
        This is a safety check to ensure the machine is actually where the FSM thinks it is.
        Should be called before attempting moves or actions.
        
        Args:
            machine_x: Current X coordinate from machine
            machine_y: Current Y coordinate from machine
            machine_z: Current Z coordinate from machine
            machine_v: Current V (manipulator) coordinate from machine
            
        Returns:
            MoveValidationResult indicating if machine state matches expected position
        """
        error = self._registry.validate_machine_position(
            position_id=self.context.position_id,
            machine_x=machine_x,
            machine_y=machine_y,
            machine_z=machine_z,
            machine_v=machine_v,
            current_z_height_id=self.context.z_height_id,
        )
        
        if error:
            return MoveValidationResult(
                valid=False,
                reason=(
                    f"Machine state validation failed: {error}. "
                    f"Machine may not be at expected position '{self.context.position_id}'."
                ),
            )
        
        return MoveValidationResult(valid=True)

    # ---------------------------------------------------------------------
    # FSM Lifecycle Hooks
    # ---------------------------------------------------------------------
    def on_enter_moving(self) -> None:
        """
        Hook invoked when entering the moving state.

        Future implementations can trigger hardware-level commands or logging
        from this hook. The current framework simply asserts that a pending move
        exists when transitions occur.
        """
        if not self.context.pending_move:
            raise RuntimeError("Entered moving state without a pending move.")

    def on_enter_idle(self) -> None:
        """Reset pending move tracking when returning to idle."""
        self.context.pending_move = None

    # ---------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------
    def _assert_engagement_exit_ready(self) -> None:
        """Ensure the machine satisfies engagement requirements before exiting."""
        if not self.context.engaged_ready_position_id:
            return

        descriptor = self._registry.get(self.context.engaged_ready_position_id)
        requirements = descriptor.engagement_requirements or descriptor.requirements
        issue = self._validate_requirements(requirements)
        if issue:
            raise RuntimeError(f"Cannot exit tool-engaged state: {issue}")

    def _validate_requirements(self, requirements: Mapping[str, object]) -> Optional[str]:
        """Validate context attributes against a requirements mapping."""
        for key, expected in requirements.items():
            actual = getattr(self.context, key, None)
            if not self._value_matches(actual, expected):
                expected_display = (
                    self._format_options(expected)
                    if isinstance(expected, (list, tuple, set, frozenset))
                    else repr(expected)
                )
                return (
                    f"Requirement '{key}={expected_display}' not satisfied "
                    f"(current: {repr(actual)})."
                )
        return None

    def _validate_excludes(self, excludes: Mapping[str, object]) -> Optional[str]:
        """Validate that context attributes do not match excluded values."""
        for key, excluded in excludes.items():
            actual = getattr(self.context, key, None)
            if self._value_matches(actual, excluded):
                excluded_display = (
                    self._format_options(excluded)
                    if isinstance(excluded, (list, tuple, set, frozenset))
                    else repr(excluded)
                )
                return (
                    f"Exclusion violated: '{key}' must not be {excluded_display} "
                    f"(current: {repr(actual)})."
                )
        return None

    @staticmethod
    def _value_matches(actual: object, expected: object) -> bool:
        """Determine whether a context value satisfies an expected requirement."""
        if isinstance(expected, (list, tuple, set, frozenset)):
            return actual in expected
        return actual == expected

    @staticmethod
    def _format_options(options: Sequence[str] | Iterable[str]) -> str:
        """Render a collection of options as a comma-separated string."""
        return ", ".join(sorted({str(option) for option in options}))
