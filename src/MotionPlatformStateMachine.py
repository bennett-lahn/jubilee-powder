"""Motion platform state machine for validated Jubilee movements.

``MotionPlatformStateMachine`` tracks logical position, tool engagement, payload
state, and z-height policy. Public ``validated_*`` methods combine FSM checks with
:class:`~src.MovementExecutor.MovementExecutor`
hardware sequences. Position and action definitions load from
``api_config/motion_platform_positions.json`` via
:class:`PositionRegistry`.

Example:
    Create from configuration and move to the scale::

        from src.MotionPlatformStateMachine import MotionPlatformStateMachine

        sm = MotionPlatformStateMachine.from_config_file(
            "api_config/motion_platform_positions.json",
            machine=machine,
            scale=scale,
        )
        result = sm.validated_move_to_scale()
        if not result.valid:
            print(result.reason)

Warning:
    Prefer :class:`~src.JubileeManager.JubileeManager` for routine automation.
    Use the state machine directly only when you need operations not exposed
    on the manager.

See Also:
    :doc:`motion-platform API reference </api/motion-platform>` for FSM diagrams
    and common operation recipes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from statemachine import State, StateMachine
from science_jubilee.Machine import Machine
from science_jubilee.decks.Deck import Deck
from src.PistonDispenser import PistonDispenser
from src.Scale import Scale
from src.HardnessTester import HardnessTester
from src.motion_config import (
    load_motion_platform_config,
    supported_tool_ids_from_system_config,
)


class PositionType(Enum):
    """Enumerates high-level motion platform positions."""

    GLOBAL_READY = auto()
    MOLD_READY = auto()
    DISPENSER_READY = auto()
    SCALE_READY = auto()
    HARDNESS_SAMPLE_READY = auto()


@dataclass(frozen=True)
class ZHeightPolicy:
    """Defines the z-height constraints that must be satisfied before a move."""

    allowed: frozenset[str] = field(default_factory=frozenset)
    required: str | None = None

    def validate(self, z_height_id: str | None) -> str | None:
        """Check whether ``z_height_id`` satisfies this policy.

        Args:
            z_height_id: Active z-height name from motion context.

        Returns:
            ``None`` when the policy passes, otherwise a human-readable error.
        """
        if not self.required and not self.allowed:
            return "No z-height is permitted for this position."

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

    x: float | str | None = None
    y: float | str | None = None
    z: float | str | None = None  # Can be "USE_Z_HEIGHT_POLICY" or numeric
    v: float | str | None = None


@dataclass(frozen=True)
class PositionDescriptor:
    """Runtime descriptor for one named motion platform position.

    Attributes:
        identifier: Lowercase position id from config.
        type: High-level :class:`PositionType` group.
        allowed_origins: Expanded set of valid source position ids.
        allowed_destinations: Expanded set of valid target position ids.
        coordinates: Stored X/Y/Z/V pose, if defined.
        requirements: Context pre-conditions checked before arrival.
        z_height_policy: Z-height constraints for this position.
        allows_tool_engagement: Whether the tool may engage here.
        engagement_requirements: Requirements checked during engagement only.
        engagement_actions: Action ids permitted while engaged.
        resource_id: Optional linked resource identifier.
        description: Human-readable summary from JSON.
        metadata: Extra key-value data from config.
    """

    identifier: str
    type: PositionType
    allowed_origins: frozenset[str]
    allowed_destinations: frozenset[str]
    coordinates: MachineCoordinates | None = None
    requirements: Mapping[str, object] = field(default_factory=dict)
    z_height_policy: ZHeightPolicy = field(default_factory=ZHeightPolicy)
    allows_tool_engagement: bool = False
    engagement_requirements: Mapping[str, object] = field(default_factory=dict)
    engagement_actions: frozenset[str] = field(default_factory=frozenset)
    resource_id: str | None = None
    description: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionDescriptor:
    """Represents an auxiliary action that can be validated by the FSM."""

    identifier: str
    position_scope: frozenset[str]
    requirements: Mapping[str, object] = field(default_factory=dict)
    excludes: Mapping[str, object] = field(default_factory=dict)
    required_tool_id: str | None = None
    requires_tool_engaged: bool = False
    blocked_when_engaged: bool = False
    description: str = ""


@dataclass
class ToolStatus:
    """Tracks engagement state and the ready point associated with a tool."""

    tool_id: str
    engaged: bool = False
    ready_position_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class MotionContext:
    """Captures the mutable state of the motion platform.

    Attributes:
        position_id: Current named position identifier.
        z_height_id: Active z-height policy id, if any.
        active_tool_id: Name of the picked-up tool, or None.
        payload_state: Manipulator payload (``empty``, ``mold_without_top_piston``,
            ``mold_with_top_piston``).
        tool_states: Per-tool engagement metadata.
        pending_move: In-flight ``MoveRequest`` while the FSM is in ``Moving``.
        engaged_ready_position_id: Ready position held during tool engagement.
        engaged_tool_id: Tool id engaged at the ready point.
        metadata: Arbitrary runtime metadata.
        deck: Loaded ``Deck`` with mold labware, if initialized.
        scale: Connected ``Scale`` instance, if any.
        current_well: ``Mold`` object carried by the manipulator, if any.
        mold_on_scale: Whether the mold is physically on the scale.
        piston_dispensers: Configured ``PistonDispenser`` instances.
    """

    position_id: str
    z_height_id: str | None = None
    active_tool_id: str | None = None
    payload_state: str | None = None
    tool_states: dict[str, ToolStatus] = field(default_factory=dict)
    pending_move: "MoveRequest" | None = None
    engaged_ready_position_id: str | None = None
    engaged_tool_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    # Platform state tracking
    deck: Deck | None = None
    scale: Scale | None = None  # Reference to scale object
    current_well: object | None = (
        None  # Mold object representing the mold being carried
    )
    mold_on_scale: bool = False  # Whether the current mold is on the scale
    piston_dispensers: list[object] = field(
        default_factory=list
    )  # List of PistonDispenser objects


@dataclass
class MoveRequest:
    """Represents a requested transition for the motion platform.

    Attributes:
        target_position_id: Destination position id.
        action: Optional action id when validating an action-only request.
        metadata: Extra fields passed through validation hooks.
    """

    target_position_id: str
    action: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class MoveValidationResult:
    """Outcome of a validated move or action.

    All :meth:`~MotionPlatformStateMachine.validated_*` methods return this
    type. Rule violations set ``valid=False`` with a ``reason`` string rather
    than raising.

    Attributes:
        valid: Whether the operation is permitted and completed successfully.
        reason: Human-readable explanation when ``valid`` is False.

    Example:
        Check before retrying::

            result = state_machine.validated_move_to_scale()
            if not result.valid:
                print(f"Move blocked: {result.reason}")
    """

    valid: bool
    reason: str | None = None


@dataclass
class _ResolvedPositionResult:
    """Internal result for ready-position coordinate resolution."""

    error: MoveValidationResult | None = None
    coords: tuple[float, float, float, float | None] | None = None  # (x, y, z, v)


class PositionRegistry:
    """In-memory index of validated motion platform positions and actions.

    Built from ``motion_platform_positions.json`` via
    :meth:`from_config_file`. The state machine uses this registry for
    transition rules, coordinate checks, and action lookup.

    Note:
        Reload requires constructing a new registry (typically by reconnecting).
        Edits to the JSON file are not picked up from an existing instance.
    """

    def __init__(self, positions: Iterable[PositionDescriptor]) -> None:
        """Register an initial set of position descriptors.

        Args:
            positions: Iterable of :class:`PositionDescriptor` instances to index.
        """
        self._positions: dict[str, PositionDescriptor] = {}
        self._actions: dict[str, ActionDescriptor] = {}
        self._z_heights: dict[str, object] = {}
        self._coordinate_tolerance: dict[str, float] = {}
        self._supported_tool_ids: frozenset[str] = frozenset()

        for position in positions:
            self.add_position(position)

    @classmethod
    def from_config_file(
        cls,
        path: str | Path,
        *,
        system_config_path: str | Path | None = None,
    ) -> "PositionRegistry":
        """Load and validate a motion platform config file.

        Expands type references (for example ``MOLD_READY``) to concrete position
        ids and attaches actions, z-heights, and coordinate tolerance from the
        JSON file. Tool ids are taken from :mod:`src.ConfigLoader`, not
        ``system_config_path``.

        Args:
            path: Path to ``motion_platform_positions.json``.
            system_config_path: Deprecated; ignored. Retained for call-site
                compatibility.

        Returns:
            Populated registry ready for the state machine.

        Raises:
            ConfigError: If JSON validation fails.
            KeyError: If a position ``type`` is unknown.

        Warning:
            ``system_config_path`` is ignored. Tool names always come from the
            :mod:`src.ConfigLoader` singleton loaded at import time.
        """
        del system_config_path  # tool ids come from ConfigLoader.system
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        motion = load_motion_platform_config(payload)

        positions: list[PositionDescriptor] = []
        type_to_ids: dict[str, set[str]] = {}

        for raw in motion.positions:
            try:
                position_type = PositionType[raw.type]
            except KeyError as exc:
                raise KeyError(f"Unknown position type '{raw.type}'") from exc

            position_id = raw.id.lower()
            type_name = raw.type.lower()

            if type_name not in type_to_ids:
                type_to_ids[type_name] = set()
            type_to_ids[type_name].add(position_id)

            z_policy = ZHeightPolicy(
                allowed=frozenset(raw.z_height_policy.allowed),
                required=raw.z_height_policy.required,
            )

            engagement_cfg = raw.engagement
            coordinates = None
            if raw.coordinates is not None:
                coordinates = MachineCoordinates(
                    x=raw.coordinates.x,
                    y=raw.coordinates.y,
                    z=raw.coordinates.z,
                    v=raw.coordinates.v,
                )

            descriptor = PositionDescriptor(
                identifier=position_id,
                type=position_type,
                allowed_origins=frozenset(raw.allowed_origins),
                allowed_destinations=frozenset(raw.allowed_destinations),
                coordinates=coordinates,
                requirements=dict(raw.requirements),
                z_height_policy=z_policy,
                allows_tool_engagement=raw.allows_tool_engagement,
                engagement_requirements=dict(
                    engagement_cfg.requirements if engagement_cfg else {}
                ),
                engagement_actions=frozenset(
                    engagement_cfg.allowed_actions if engagement_cfg else []
                ),
                resource_id=raw.resource_id,
                description=raw.description,
                metadata=dict(raw.metadata),
            )
            positions.append(descriptor)

        # Second pass: expand type references to actual position IDs
        def expand_references(refs: frozenset[str]) -> frozenset[str]:
            """Expand type names (e.g., 'MOLD_READY') to all position IDs of that type."""
            expanded = set()
            for ref in refs:
                ref_key = ref.lower() if isinstance(ref, str) else ref
                if ref_key in type_to_ids:
                    # It's a type reference, expand to all IDs of that type
                    expanded.update(type_to_ids[ref_key])
                else:
                    # It's a specific position ID
                    expanded.add(ref_key)
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
            action_cfg.id: ActionDescriptor(
                identifier=action_cfg.id,
                position_scope=frozenset(action_cfg.position_scope),
                requirements=dict(action_cfg.requirements),
                excludes=dict(action_cfg.excludes),
                required_tool_id=action_cfg.required_tool_id,
                requires_tool_engaged=action_cfg.requires_tool_engaged,
                blocked_when_engaged=action_cfg.blocked_when_engaged,
                description=action_cfg.description,
            )
            for action_cfg in motion.actions
        }
        registry._supported_tool_ids = supported_tool_ids_from_system_config()
        registry._z_heights = {
            z_id: entry.model_dump() for z_id, entry in motion.z_heights.items()
        }

        tolerance_cfg = motion.coordinate_tolerance
        registry._coordinate_tolerance = {
            axis: value
            for axis, value in tolerance_cfg.items()
            if axis != "description" and isinstance(value, (int, float))
        }

        return registry

    def add_position(self, position: PositionDescriptor) -> None:
        """Register a position descriptor.

        Args:
            position: Descriptor to add.

        Raises:
            ValueError: If ``position.identifier`` is already registered.
        """
        if position.identifier in self._positions:
            raise ValueError(f"Duplicate position identifier '{position.identifier}'")
        self._positions[position.identifier] = position

    def get(self, identifier: str) -> PositionDescriptor:
        """Return the descriptor for a position id.

        Args:
            identifier: Lowercase position id (for example ``global_ready``).

        Raises:
            KeyError: If the id is unknown.
        """
        try:
            return self._positions[identifier]
        except KeyError as exc:
            raise KeyError(f"Unknown position identifier '{identifier}'") from exc

    def has(self, identifier: str) -> bool:
        """Return whether ``identifier`` is a known position id."""
        return identifier in self._positions

    def find_first_of_type(
        self, position_type: PositionType
    ) -> PositionDescriptor | None:
        """Return the first descriptor matching ``position_type``, if any."""
        for descriptor in self._positions.values():
            if descriptor.type == position_type:
                return descriptor
        return None

    def get_action(self, identifier: str) -> ActionDescriptor:
        """Return the descriptor for an action id.

        Args:
            identifier: Action id from the ``actions`` array.

        Raises:
            KeyError: If the action is unknown.
        """
        try:
            return self._actions[identifier]
        except KeyError as exc:
            raise KeyError(f"Unknown action identifier '{identifier}'") from exc

    @property
    def actions(self) -> dict[str, ActionDescriptor]:
        """Shallow copy of registered action descriptors keyed by id."""
        return dict(self._actions)

    @property
    def z_heights(self) -> dict[str, object]:
        """Shallow copy of z-height entries from config."""
        return dict(self._z_heights)

    @property
    def coordinate_tolerance(self) -> dict[str, float]:
        """Per-axis coordinate tolerance in millimeters."""
        return dict(self._coordinate_tolerance)

    @property
    def supported_tool_ids(self) -> frozenset[str]:
        """Tool names allowed by validated ``system_config.json``."""
        return self._supported_tool_ids

    def validate_machine_position(
        self,
        position_id: str,
        machine_x: float,
        machine_y: float,
        machine_z: float,
        machine_v: float,
        current_z_height_id: str | None = None,
    ) -> str | None:
        """Check reported machine coordinates against a position definition.

        Args:
            position_id: Position whose stored coordinates are the expected pose.
            machine_x: Reported X coordinate (mm).
            machine_y: Reported Y coordinate (mm).
            machine_z: Reported Z coordinate (mm).
            machine_v: Reported V coordinate (mm).
            current_z_height_id: Active z-height when expected Z uses
                ``USE_Z_HEIGHT_POLICY``.

        Returns:
            ``None`` when coordinates match within tolerance, otherwise an
            error message string.

        Note:
            When ``coordinates.z`` is ``USE_Z_HEIGHT_POLICY``, expected Z is
            resolved from :attr:`z_heights` using ``current_z_height_id``.
        """
        position = self.get(position_id)
        if not position.coordinates:
            # No coordinates defined for this position, skip validation
            return None

        coords = position.coordinates
        tolerance = self._coordinate_tolerance

        def check_coord(
            axis: str, expected: float | str | None, actual: float
        ) -> str | None:
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
                        if z_expected is not None and isinstance(
                            z_expected, (int, float)
                        ):
                            if abs(actual - z_expected) > tolerance[axis]:
                                return (
                                    f"{axis.upper()} coordinate mismatch: expected {z_expected}, got {actual} "
                                    f"(tolerance: ±{tolerance[axis]})"
                                )
                    return None

            # Numeric comparison
            if isinstance(expected, (int, float)):
                if abs(actual - expected) > tolerance[axis]:
                    return (
                        f"{axis.upper()} coordinate mismatch: expected {expected}, got {actual} "
                        f"(tolerance: ±{tolerance[axis]})"
                    )

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
    """Validates and sequences Jubilee motion platform moves.

    Uses ``python-statemachine`` for the control FSM (``idle``, ``moving``,
    ``tool_engaged``) and :class:`PositionRegistry` for transition rules from
    ``motion_platform_positions.json``. Public callers should use
    :meth:`validated_*` methods, which delegate hardware motion to an internal
    :class:`~src.MovementExecutor.MovementExecutor`.

    Attributes:
        context: Mutable :class:`MotionContext` (position, tools, payload, deck).
        idle: Initial FSM state when no motion is in progress.
        moving: Transient FSM state while a move executes.
        tool_engaged: FSM state while a mold rests on the scale with tool engaged.

    Warning:
        Not thread-safe. Do not call methods from multiple threads without
        external locking.

    Note:
        Validated methods return :class:`MoveValidationResult`; always inspect
        ``result.valid`` and surface ``result.reason`` before retrying.

    See Also:
        :class:`~src.JubileeManager.JubileeManager` for the recommended
        high-level entry point.
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

    def __init__(
        self,
        registry: PositionRegistry,
        machine: Machine,
        *,
        context: MotionContext | None = None,
        scale: Scale | None = None,
    ) -> None:
        """Construct a state machine bound to a position registry and machine.

        Prefer :meth:`from_config_file` for production setup.

        Args:
            registry: Loaded :class:`PositionRegistry` with positions and actions.
            machine: Connected Jubilee :class:`~science_jubilee.Machine.Machine`.
            context: Optional initial :class:`MotionContext`. Defaults to the
                first ``GLOBAL_READY`` position.
            scale: Optional :class:`~src.Scale.Scale` stored on the context.

        Raises:
            ValueError: If no ``GLOBAL_READY`` position exists when ``context``
                is omitted, or if a provided context references an unknown position.
        """
        # Import MovementExecutor locally to avoid circular import
        from src.MovementExecutor import MovementExecutor

        self._registry = registry
        self._actions = registry.actions

        if context is None:
            initial_descriptor = registry.find_first_of_type(PositionType.GLOBAL_READY)
            if not initial_descriptor:
                raise ValueError("Configuration must define a GLOBAL_READY position.")
            context = MotionContext(
                position_id=initial_descriptor.identifier, scale=scale
            )
        else:
            # Ensure the provided context references a known position.
            self._registry.get(context.position_id)
            # Update scale if provided
            if scale is not None:
                context.scale = scale

        self.context = context
        self._executor = MovementExecutor(machine, scale=scale)
        super().__init__()

    @staticmethod
    def _axis_or_config(axis: str | None) -> str:
        if axis is not None:
            return axis
        from src.ConfigLoader import config as _cfg

        return _cfg.system.manipulator.tamper_axis

    @classmethod
    def from_config_file(
        cls,
        path: str | Path,
        machine: Machine,
        *,
        context_overrides: Mapping[str, object] | None = None,
        scale: Scale | None = None,
        system_config_path: str | Path | None = None,
    ) -> "MotionPlatformStateMachine":
        """Create a state machine from ``motion_platform_positions.json``.

        Args:
            path: Path to ``motion_platform_positions.json``.
            machine: Connected Jubilee :class:`~science_jubilee.Machine.Machine`.
            context_overrides: Optional fields merged into the initial
                :class:`MotionContext` (for example ``payload_state``).
            scale: Optional :class:`~src.Scale.Scale` stored on the context.
            system_config_path: Deprecated; passed to
                :meth:`PositionRegistry.from_config_file` for compatibility.

        Returns:
            Configured state machine with ``context.position_id`` at
            ``GLOBAL_READY``.

        Raises:
            ValueError: If the configuration lacks a ``GLOBAL_READY`` position.

        Example:
            Wire up deck and dispensers after construction::

                sm = MotionPlatformStateMachine.from_config_file(
                    "api_config/motion_platform_positions.json",
                    machine=machine,
                    scale=scale,
                )
                sm.initialize_deck()
                sm.initialize_dispensers(num_piston_dispensers=2, num_pistons_per_dispenser=10)

        Note:
            Position ids, transitions, and z-height policies come from JSON
            only. See :doc:`position configuration </api/position-config>`.
        """
        registry = PositionRegistry.from_config_file(
            path, system_config_path=system_config_path
        )
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
            scale=scale,
        )

        if context_overrides:
            context_kwargs.update(context_overrides)

        context = MotionContext(**context_kwargs)
        return cls(registry, machine, context=context, scale=scale)

    # ---------------------------------------------------------------------
    # Platform State Initialization
    # ---------------------------------------------------------------------

    def initialize_deck(
        self, deck_name: str = "weight_well_deck", config_path: str | None = None
    ):
        """Initialize the deck with mold labware in each slot.

        Loads ``Mold`` objects into slots 0-17 and links each well to a
        ``mold_ready_N`` position id from config.

        Args:
            deck_name: Deck configuration name (default ``weight_well_deck``).
            config_path: Optional path to deck labware JSON files.

        Note:
            Pick/place coordinates still come from
            ``motion_platform_positions.json``, not deck labware offsets.
        """
        from src.trickler_labware import Mold
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
                    if "zDimension" not in labware.dimensions:
                        raise ValueError(
                            "mold_labware.json dimensions must include zDimension"
                        )
                    self.context.deck.safe_z = labware.dimensions["zDimension"]

                    for well_name in labware.wells.keys():
                        # Skip empty mold slot names
                        if not well_name or not isinstance(well_name, str):
                            continue

                        # Extract numerical ID from mold slot name (e.g., "A0" -> "0", "A17" -> "17")
                        # The external API uses numerical IDs (0, 1, 2...) for all mold references.
                        # Internally, labware uses A0, A1, A2... format per labware library requirements.
                        if well_name.startswith("A"):
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
                            ready_pos=ready_pos,  # State machine position name
                        )

                        # Replace the regular well with our Mold
                        # Keep the labware well name format (A0-A17) for internal consistency
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

    def initialize_dispensers(
        self, num_piston_dispensers: int = 0, num_pistons_per_dispenser: int = 0
    ):
        """Initialize piston dispenser inventory tracking.

        Args:
            num_piston_dispensers: Number of side-mounted piston dispensers.
            num_pistons_per_dispenser: Initial piston count per dispenser.
        """

        self.context.piston_dispensers = [
            PistonDispenser(i, num_pistons_per_dispenser)
            for i in range(num_piston_dispensers)
        ]

    def set_dispenser_pistons(self, index: int, num_pistons: int) -> bool:
        """
        Set the piston count for a specific dispenser.

        Allows the piston count to be updated (e.g. after reloading a tray)
        without disconnecting from the machine.

        Args:
            index: Zero-based dispenser index.
            num_pistons: New piston count (must be >= 0).

        Returns:
            True on success, False if the index is out of range.
        """
        dispensers = self.context.piston_dispensers
        if index < 0 or index >= len(dispensers):
            return False
        dispensers[index].num_pistons = num_pistons
        return True

    def get_mold_from_deck(self, well_id: str) -> object | None:
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
            if slot.has_labware and hasattr(slot.labware, "wells"):
                # Convert numerical ID to labware well name format (e.g., "0" -> "A0")
                # Labware internally uses A0, A1, A2... format per library requirements
                labware_well_name = f"A{well_id}"

                # Get the well matching the labware well name
                if labware_well_name in slot.labware.wells:
                    from src.trickler_labware import Mold

                    well = slot.labware.wells[labware_well_name]
                    if isinstance(well, Mold):
                        return well
        return None

    def reset_mold_metadata(self) -> None:
        """Reset transient mold state captured during a dispensing job.

        Clears mold-level metadata so a new job starts from a clean baseline.
        """
        from src.trickler_labware import Mold

        deck = self.context.deck
        if deck is None:
            return

        for slot in deck.slots.values():
            if not getattr(slot, "has_labware", False):
                continue
            labware = getattr(slot, "labware", None)
            wells = getattr(labware, "wells", None)
            if not isinstance(wells, dict):
                continue
            for well in wells.values():
                if isinstance(well, Mold):
                    self._reset_mold_runtime_metadata(well)

        if isinstance(self.context.current_well, Mold):
            self._reset_mold_runtime_metadata(self.context.current_well)

    # ---------------------------------------------------------------------
    # Machine Access
    # ---------------------------------------------------------------------
    @property
    def machine(self) -> Machine:
        """Read-only Jubilee machine access for position and status queries.

        Warning:
            Do not issue moves through this property. Use :meth:`validated_*`
            methods so transition rules and coordinate checks stay enforced.
        """
        return self._executor.machine

    @property
    def last_fill_weight(self) -> float | None:
        """The final stable weight reading from the most recent successful powder fill."""
        return self._executor.last_fill_weight

    # ---------------------------------------------------------------------
    # Validated Movement Methods
    # =====================================================================
    # These methods combine validation (state machine) and execution (executor).
    # This is the interface that Manipulator and other classes should use.
    # =====================================================================

    def validated_pick_mold(
        self, well_id: str, manipulator_config: dict[str, object]
    ) -> MoveValidationResult:
        """Validate and execute picking up a mold from a mold slot.

        Args:
            well_id: Mold slot identifier (numerical string ``"0"`` through ``"17"``).
            manipulator_config: Manipulator settings dict (must include
                ``tamper_axis``). Use :meth:`~src.Manipulator.Manipulator._get_config_dict`.

        Returns:
            :class:`MoveValidationResult`. On success, sets ``current_well`` and
            ``payload_state`` to ``mold_without_top_piston``.

        Note:
            Requires the machine to already be at ``mold_ready_{well_id}`` with
            empty payload and manipulator tool active.
        """
        from src.trickler_labware import Mold

        # Domain-specific validation
        if self.context.current_well is not None:
            return MoveValidationResult(
                valid=False, reason="Manipulator already carrying a mold"
            )

        if self.context.deck is None:
            return MoveValidationResult(valid=False, reason="Deck not configured")

        well = self.get_mold_from_deck(well_id)
        if well is None:
            return MoveValidationResult(
                valid=False, reason=f"Mold slot {well_id} not found"
            )

        if not isinstance(well, Mold):
            return MoveValidationResult(valid=False, reason="Invalid mold object")

        if not well.valid:
            return MoveValidationResult(valid=False, reason="Mold is not valid")

        if well.has_top_piston:
            return MoveValidationResult(
                valid=False, reason="Cannot pick up mold that already has a top piston"
            )

        # Get ready position coordinates for this mold slot
        ready_position_id = f"mold_ready_{well_id}"
        pos_result = self._resolve_ready_position_coords(ready_position_id)
        if pos_result.error:
            return pos_result.error
        ready_x, ready_y, ready_z, ready_v = pos_result.coords

        # Execute through generic validation framework
        result = self._validate_and_execute(
            action_id="pick_up_mold",
            execution_func=self._executor.execute_pick_mold,
            well_id=well_id,
            deck=self.context.deck,
            tamper_axis=manipulator_config["tamper_axis"],
            ready_x=ready_x,
            ready_y=ready_y,
            ready_z=ready_z,
            ready_v=ready_v,
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
        self, well_id: str, manipulator_config: dict[str, object] | None = None
    ) -> MoveValidationResult:
        """Validate and execute placing a mold in a mold slot.

        Args:
            well_id: Mold slot identifier (numerical string ``"0"`` through ``"17"``).
            manipulator_config: Optional manipulator settings dict (unused for
                placement; retained for call-site compatibility).

        Returns:
            :class:`MoveValidationResult`. On success, clears ``current_well`` and
            sets ``payload_state`` to ``empty``.

        Note:
            Requires carrying a mold at ``mold_ready_{well_id}``.
        """
        # Domain-specific validation
        if self.context.current_well is None:
            return MoveValidationResult(valid=False, reason="Not carrying a mold")

        if self.context.deck is None:
            return MoveValidationResult(valid=False, reason="Deck not configured")

        # Get ready position coordinates for this mold slot
        ready_position_id = f"mold_ready_{well_id}"
        pos_result = self._resolve_ready_position_coords(ready_position_id)
        if pos_result.error:
            return pos_result.error
        ready_x, ready_y, ready_z, ready_v = pos_result.coords

        # Execute through generic validation framework
        result = self._validate_and_execute(
            action_id="put_down_mold",
            execution_func=self._executor.execute_place_mold,
            well_id=well_id,
            deck=self.context.deck,
            ready_x=ready_x,
            ready_y=ready_y,
            ready_z=ready_z,
            ready_v=ready_v,
        )

        # Update state machine state if successful
        if result.valid:
            self.context.current_well = None
            self.context.mold_on_scale = False
            self.context.payload_state = "empty"

        return result

    def validated_place_mold_on_scale(
        self, manipulator_config: dict[str, object]
    ) -> MoveValidationResult:
        """Validate and execute placing the carried mold on the scale.

        On success, transitions to ``scale_active`` and engages the tool.

        Args:
            manipulator_config: Manipulator settings dict (must include
                ``tamper_axis``).

        Returns:
            :class:`MoveValidationResult`.

        Note:
            Requires ``scale_ready``, mold without top piston, and manipulator
            tool active. Engages the tool at ``scale_active`` after placement.
        """
        # Domain-specific validation
        if self.context.scale is None:
            return MoveValidationResult(valid=False, reason="Scale not configured")

        if self.context.current_well is None:
            return MoveValidationResult(valid=False, reason="Not carrying a mold")

        mold = self.context.current_well

        if mold.has_top_piston:
            return MoveValidationResult(
                valid=False, reason="Cannot place mold with piston on scale"
            )

        if self.context.mold_on_scale:
            return MoveValidationResult(valid=False, reason="Mold is already on scale")

        # Get ready position coordinates from scale_ready position
        pos_result = self._resolve_ready_position_coords("scale_ready")
        if pos_result.error:
            return pos_result.error
        ready_x, ready_y, ready_z, ready_v = pos_result.coords

        # Execute through generic validation framework
        result = self._validate_and_execute(
            action_id="place_mold_on_scale",
            execution_func=self._executor.execute_place_mold_on_scale,
            tamper_axis=manipulator_config["tamper_axis"],
            ready_x=ready_x,
            ready_y=ready_y,
            ready_z=ready_z,
            ready_v=ready_v,
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
        self, manipulator_config: dict[str, object]
    ) -> MoveValidationResult:
        """Validate and execute picking the mold up from the scale.

        On success, disengages the tool and returns to ``scale_ready``.

        Args:
            manipulator_config: Manipulator settings dict (must include
                ``tamper_axis``).

        Returns:
            :class:`MoveValidationResult`.

        Note:
            Requires ``scale_active`` with tool engaged and ``mold_on_scale``
            set on the context.
        """
        # Domain-specific validation
        if self.context.scale is None:
            return MoveValidationResult(valid=False, reason="Scale not configured")

        if self.context.current_well is None:
            return MoveValidationResult(valid=False, reason="Not carrying a mold")

        if not self.context.mold_on_scale:
            return MoveValidationResult(valid=False, reason="Mold is not on scale")

        # Get ready position coordinates from scale_ready position
        pos_result = self._resolve_ready_position_coords("scale_ready")
        if pos_result.error:
            return pos_result.error
        ready_x, ready_y, ready_z, ready_v = pos_result.coords

        # Execute through generic validation framework
        result = self._validate_and_execute(
            action_id="pick_mold_from_scale",
            execution_func=self._executor.execute_pick_mold_from_scale,
            tamper_axis=manipulator_config["tamper_axis"],
            ready_x=ready_x,
            ready_y=ready_y,
            ready_z=ready_z,
            ready_v=ready_v,
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
        self, piston_dispenser: PistonDispenser, manipulator_config: dict[str, object]
    ) -> MoveValidationResult:
        """Validate and execute placing a top piston on the carried mold.

        Args:
            piston_dispenser: :class:`~src.PistonDispenser.PistonDispenser` at
                the current ``dispenser_ready_N`` position.
            manipulator_config: Manipulator settings dict (must include
                ``tamper_axis``).

        Returns:
            :class:`MoveValidationResult`. On success, sets ``has_top_piston``
            on the carried mold.

        Warning:
            The underlying executor currently uses absolute coordinates and is
            validated for a single dispenser layout. Confirm machine config
            before running on multi-dispenser setups.
        """
        # Domain-specific validation
        if self.context.current_well is None:
            return MoveValidationResult(valid=False, reason="Not carrying a mold")

        mold = self.context.current_well

        if mold.has_top_piston:
            return MoveValidationResult(
                valid=False, reason="Mold already has a top piston"
            )

        if piston_dispenser.num_pistons == 0:
            return MoveValidationResult(
                valid=False, reason="No pistons available in dispenser"
            )

        if self.context.mold_on_scale:
            return MoveValidationResult(
                valid=False, reason="Cannot add top piston when mold is on scale"
            )

        # Get ready position coordinates for this dispenser
        dispenser_ready_id = f"dispenser_ready_{piston_dispenser.index}"
        pos_result = self._resolve_ready_position_coords(dispenser_ready_id)
        if pos_result.error:
            return pos_result.error
        ready_x, ready_y, ready_z, ready_v = pos_result.coords

        # Execute through generic validation framework
        result = self._validate_and_execute(
            action_id="retrieve_piston",
            execution_func=self._executor.execute_place_top_piston,
            piston_dispenser=piston_dispenser,
            tamper_axis=manipulator_config["tamper_axis"],
            ready_x=ready_x,
            ready_y=ready_y,
            ready_z=ready_z,
            ready_v=ready_v,
        )

        # Update state machine state if successful
        if result.valid:
            mold.has_top_piston = True

        return result

    def validated_tamp(
        self,
        manipulator_config: dict[str, object],
        tamp_depth: float,
        tamp_speed: int,
    ) -> MoveValidationResult:
        """Validate and execute tamping to compress powder in the held mold.

        Typically performed at ``scale_ready`` after filling and before piston
        insertion. Bounds are enforced from ``system_config.json`` via
        :mod:`src.ConfigLoader`.

        Args:
            manipulator_config: Manipulator settings dict (must include
                ``tamper_axis``).
            tamp_depth: Target tamp depth in mm.
            tamp_speed: Tamper feed rate in mm/min.

        Returns:
            :class:`MoveValidationResult`.

        Note:
            Requires a mold without top piston. The V axis is re-homed after
            tamping for positioning accuracy.

        See Also:
            :meth:`~src.Manipulator.Manipulator.tamp` raises :class:`~src.Manipulator.ToolStateError`
            when validation fails.
        """
        from src.ConfigLoader import config

        # Load tamping parameter bounds from configuration
        MIN_TAMP_DEPTH = config.get_tamp_depth_min()
        MAX_TAMP_DEPTH = config.get_tamp_depth_max()
        MIN_TAMP_SPEED = config.get_tamp_speed_min()
        MAX_TAMP_SPEED = config.get_tamp_speed_max()

        # Validate tamping parameters
        if not (MIN_TAMP_DEPTH <= tamp_depth <= MAX_TAMP_DEPTH):
            return MoveValidationResult(
                valid=False,
                reason=f"Tamp depth {tamp_depth}mm is out of bounds. Must be between {MIN_TAMP_DEPTH} and {MAX_TAMP_DEPTH} mm.",
            )

        if not (MIN_TAMP_SPEED <= tamp_speed <= MAX_TAMP_SPEED):
            return MoveValidationResult(
                valid=False,
                reason=f"Tamp speed {tamp_speed}mm/min is out of bounds. Must be between {MIN_TAMP_SPEED} and {MAX_TAMP_SPEED} mm/min.",
            )

        # Domain-specific validation
        if self.context.current_well is None:
            return MoveValidationResult(valid=False, reason="Not carrying a mold")

        mold = self.context.current_well
        if mold.has_top_piston:
            return MoveValidationResult(
                valid=False, reason="Cannot tamp mold that has a top piston"
            )

        # Verify we're at scale_ready position (typical) or a mold_ready position
        valid_positions = ["scale_ready"] + [f"mold_ready_{i}" for i in range(16)]
        if self.context.position_id not in valid_positions:
            return MoveValidationResult(
                valid=False,
                reason=f"Tamping should be performed at scale_ready or mold_ready position. Current: {self.context.position_id}",
            )

        # Execute through generic validation framework
        return self._validate_and_execute(
            action_id="tamp_mold",
            execution_func=self._executor.execute_tamp,
            tamper_axis=manipulator_config["tamper_axis"],
            tamp_depth=tamp_depth,
            tamp_speed=tamp_speed,
        )

    # ---------------------------------------------------------------------
    # Generic Validation and Execution
    # ---------------------------------------------------------------------

    def _resolve_ready_position_coords(
        self,
        position_id: str,
        *,
        require_v: bool = True,
    ) -> _ResolvedPositionResult:
        """
        Validate that a named position exists, has all required coordinates defined,
        and resolve the Z axis (handling USE_Z_HEIGHT_POLICY via context).

        Args:
            position_id: Identifier of the position to resolve.
            require_v: When True, the V axis must be defined for the position.

        Returns a _ResolvedPositionResult with either:
          - error set to a failed MoveValidationResult, or
          - coords set to (x, y, z, v) ready for use. V can be None when not required.
        """

        def _fail(reason: str) -> _ResolvedPositionResult:
            return _ResolvedPositionResult(
                error=MoveValidationResult(valid=False, reason=reason)
            )

        if not self._registry.has(position_id):
            return _fail(f"Ready position '{position_id}' not defined in configuration")

        pos = self._registry.get(position_id)

        if not pos.coordinates:
            return _fail(
                f"Ready position '{position_id}' does not have coordinates defined"
            )

        c = pos.coordinates
        required_axes = [("X", c.x), ("Y", c.y)]
        if require_v:
            required_axes.append(("V", c.v))

        for axis, value in required_axes:
            if value is None:
                return _fail(
                    f"Ready position '{position_id}' missing {axis} coordinate"
                )

        # Resolve Z
        if c.z == "USE_Z_HEIGHT_POLICY":
            if not self.context.z_height_id:
                return _fail(
                    "Z height policy required but z_height_id not set in context"
                )
            z_heights = self._registry.z_heights
            if self.context.z_height_id not in z_heights:
                return _fail(
                    f"Z height '{self.context.z_height_id}' not found in configuration"
                )
            z_config = z_heights[self.context.z_height_id]
            ready_z = (
                z_config.get("z_coordinate") if isinstance(z_config, dict) else None
            )
            if ready_z is None:
                return _fail(
                    f"Z coordinate not defined for z_height '{self.context.z_height_id}'"
                )
        elif c.z is not None:
            ready_z = c.z
        else:
            return _fail(f"Ready position '{position_id}' missing Z coordinate")

        try:
            resolved_x = float(c.x)
            resolved_y = float(c.y)
            resolved_z = float(ready_z)
        except (TypeError, ValueError) as exc:
            return _fail(
                f"Position '{position_id}' has non-numeric XY/Z coordinates: {exc}"
            )

        return _ResolvedPositionResult(coords=(resolved_x, resolved_y, resolved_z, c.v))

    def _validate_and_execute(
        self,
        target_position_id: str | None = None,
        action_id: str | None = None,
        additional_requirements: dict[str, object] | None = None,
        execution_func: Callable[..., object] | None = None,
        **execution_kwargs: object,
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
                reason="Already executing a move. Wait for current move to complete.",
            )

        # Step 1.5: Verify all axes are homed (exempt homing actions)
        homing_actions = {"home_all", "home_manipulator", "home_trickler"}
        if action_id not in homing_actions:
            axes_homed = self._executor.get_machine_axes_homed()
            axis_names = ["X", "Y", "Z", "U", "V"]
            not_homed = [
                axis_names[i]
                for i in range(len(axes_homed))
                if i < len(axis_names) and not axes_homed[i]
            ]
            if not_homed:
                return MoveValidationResult(
                    valid=False,
                    reason=f"All axes must be homed before performing moves/actions. Unhomed axes: {', '.join(not_homed)}",
                )

        # Route to appropriate validation based on whether it's a movement or action
        if target_position_id is not None:
            return self._validate_and_execute_move(
                target_position_id=target_position_id,
                additional_requirements=additional_requirements,
                execution_func=execution_func,
                **execution_kwargs,
            )
        else:  # action_id is provided
            return self._validate_and_execute_action(
                action_id=action_id,
                additional_requirements=additional_requirements,
                execution_func=execution_func,
                **execution_kwargs,
            )

    def _validate_and_execute_move(
        self,
        target_position_id: str,
        additional_requirements: dict[str, object] | None = None,
        execution_func=None,
        **execution_kwargs,
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
                valid=False, reason=f"Unknown target position '{target_position_id}'."
            )

        try:
            current_descriptor = self._registry.get(self.context.position_id)
        except KeyError:
            return MoveValidationResult(
                valid=False,
                reason=f"Current position '{self.context.position_id}' is not registered.",
            )

        # Check if transition is allowed
        if target_position_id not in current_descriptor.allowed_destinations:
            allowed = self._format_options(current_descriptor.allowed_destinations)
            return MoveValidationResult(
                valid=False,
                reason=(
                    f"Cannot move from '{self.context.position_id}' to "
                    f"'{target_position_id}'. Allowed destinations: {allowed}."
                ),
            )

        if self.context.position_id not in target_descriptor.allowed_origins:
            allowed_origins = self._format_options(target_descriptor.allowed_origins)
            return MoveValidationResult(
                valid=False,
                reason=(
                    f"'{target_position_id}' cannot accept moves from "
                    f"'{self.context.position_id}'. Allowed origins: {allowed_origins}."
                ),
            )

        # Step 3: Validate machine is at expected current position
        try:
            current_pos = self._executor.get_machine_position()
        except RuntimeError as exc:
            return MoveValidationResult(valid=False, reason=str(exc))
        machine_x, machine_y, machine_z, machine_v = (
            self._machine_coords_from_position(current_pos)
        )
        machine_validation = self.validate_machine_state(
            machine_x=machine_x,
            machine_y=machine_y,
            machine_z=machine_z,
            machine_v=machine_v,
        )
        if not machine_validation.valid:
            return machine_validation

        # Step 4: Validate z-height policy
        z_height_issue = target_descriptor.z_height_policy.validate(
            self.context.z_height_id
        )
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
                        valid=False, reason="Execution returned False"
                    )

                # Wait for all buffered moves to complete before returning
                self._executor.wait_for_moves_to_finish()

                return MoveValidationResult(valid=True)

            except Exception as e:
                # Abort the move on exception
                if self.current_state == self.moving:
                    self.abort_motion()
                return MoveValidationResult(
                    valid=False, reason=f"Execution failed: {str(e)}"
                )

        # If no execution function, just return validation result
        return MoveValidationResult(valid=True)

    def _validate_and_execute_action(
        self,
        action_id: str,
        additional_requirements: dict[str, object] | None = None,
        execution_func=None,
        **execution_kwargs,
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
                valid=False, reason=f"Unknown action '{action_id}'."
            )

        # Step 3: Validate tool engagement state
        if descriptor.requires_tool_engaged and self.current_state != self.tool_engaged:
            return MoveValidationResult(
                valid=False,
                reason=f"Action '{action_id}' requires the tool to be engaged.",
            )

        if descriptor.blocked_when_engaged and self.current_state == self.tool_engaged:
            return MoveValidationResult(
                valid=False,
                reason=(
                    f"Action '{action_id}' cannot be performed while tool is engaged. "
                    f"Tool must be disengaged first."
                ),
            )

        # Step 4: Validate required tool ID
        if descriptor.required_tool_id:
            if self.context.active_tool_id != descriptor.required_tool_id:
                return MoveValidationResult(
                    valid=False,
                    reason=(
                        f"Action '{action_id}' requires tool '{descriptor.required_tool_id}'. "
                        f"Current tool: '{self.context.active_tool_id}'."
                    ),
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
                    ),
                )

        # Step 6: Validate machine is at expected current position unless this is a homing action
        if not (action_id and action_id.startswith("home_")):
            try:
                current_pos = self._executor.get_machine_position()
            except RuntimeError as exc:
                return MoveValidationResult(valid=False, reason=str(exc))
            machine_x, machine_y, machine_z, machine_v = (
                self._machine_coords_from_position(current_pos)
            )
            machine_validation = self.validate_machine_state(
                machine_x=machine_x,
                machine_y=machine_y,
                machine_z=machine_z,
                machine_v=machine_v,
            )
        else:
            machine_validation = MoveValidationResult(valid=True)
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
                        valid=False, reason="Execution returned False"
                    )

                # Wait for all buffered moves to complete before returning
                self._executor.wait_for_moves_to_finish()

                return MoveValidationResult(valid=True)

            except Exception as e:
                return MoveValidationResult(
                    valid=False, reason=f"Execution failed: {str(e)}"
                )
        # If no execution function, just return validation result
        return MoveValidationResult(valid=True)

    # ---------------------------------------------------------------------
    # Validated Methods for JubileeManager Operations
    # ---------------------------------------------------------------------

    def validated_move_to_mold_slot(self, well_id: str) -> MoveValidationResult:
        """Validate and execute movement to a specific mold slot.

        Args:
            well_id: Mold slot identifier (numerical string ``"0"`` through ``"17"``).

        Returns:
            :class:`MoveValidationResult` with updated ``context.position_id``
            on success.

        Note:
            Target resolves to ``mold_ready_{well_id}`` from deck labware or
            config. Requires a valid transition from the current position.
        """
        # Use state machine's deck
        deck = self.context.deck
        if deck is None:
            return MoveValidationResult(valid=False, reason="Deck not configured")

        # Get mold from state machine's deck
        well = self.get_mold_from_deck(well_id)

        # Determine target position from mold's ready_pos if available, otherwise construct from mold slot ID
        if well and hasattr(well, "ready_pos") and well.ready_pos:
            target_position = well.ready_pos
        else:
            # Fallback: construct from mold slot ID
            target_position = f"mold_ready_{well_id}"

        # If position not in registry, return error
        if not self._registry.has(target_position):
            return MoveValidationResult(
                valid=False, reason="Could not find mold ready position"
            )

        # Resolve base coordinates from the logical position definition.
        pos_result = self._resolve_ready_position_coords(target_position)
        if pos_result.error:
            return pos_result.error
        if pos_result.coords is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Could not resolve coordinates for '{target_position}'",
            )
        ready_x, ready_y, ready_z, ready_v = pos_result.coords

        # Execute move using resolved base coordinates.
        return self._validate_and_execute_move(
            target_position_id=target_position,
            execution_func=self._executor.execute_move_to_mold_slot,
            x=ready_x,
            y=ready_y,
            z=ready_z,
            v=ready_v,
        )

    def validated_move_to_scale(self) -> MoveValidationResult:
        """Validate and execute movement to ``scale_ready``.

        Returns:
            :class:`MoveValidationResult`.

        Note:
            Requires scale configured on the context, correct active tool, and
            z-height policy satisfied (typically ``mold_transfer_safe``).
        """
        if self.context.scale is None:
            return MoveValidationResult(valid=False, reason="Scale not configured")

        pos_result = self._resolve_ready_position_coords("scale_ready")
        if pos_result.error:
            return pos_result.error
        if pos_result.coords is None:
            return MoveValidationResult(
                valid=False,
                reason="Could not resolve coordinates for scale_ready",
            )
        ready_x, ready_y, ready_z, ready_v = pos_result.coords

        return self._validate_and_execute_move(
            target_position_id="scale_ready",
            execution_func=self._executor.execute_move_to_scale_location,
            ready_x=ready_x,
            ready_y=ready_y,
            ready_z=ready_z,
            ready_v=ready_v,
        )

    def validated_move_to_dispenser(self) -> MoveValidationResult:
        """
        Validate and execute movement to the next available dispenser ready position.

        Selects the first configured dispenser that still has pistons remaining
        and moves to its ready position. All dispenser tracking lives here,
        callers do not choose dispenser.

        Returns:
            MoveValidationResult with outcome
        """
        # Find the first dispenser with pistons remaining
        piston_dispenser = next(
            (d for d in self.context.piston_dispensers if d.num_pistons > 0), None
        )
        if piston_dispenser is None:
            return MoveValidationResult(
                valid=False, reason="No pistons available in any dispenser"
            )

        target_position = piston_dispenser.ready_pos

        if not self._registry.has(target_position):
            return MoveValidationResult(
                valid=False,
                reason=f"Dispenser ready position '{target_position}' not defined in configuration",
            )

        pos_result = self._resolve_ready_position_coords(target_position)
        if pos_result.error:
            return pos_result.error
        if pos_result.coords is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Could not resolve coordinates for '{target_position}'",
            )
        ready_x, ready_y, ready_z, ready_v = pos_result.coords

        return self._validate_and_execute_move(
            target_position_id=target_position,
            execution_func=self._executor.execute_move_to_position,
            x=ready_x,
            y=ready_y,
            z=ready_z,
            v=ready_v,
        )

    def validated_move_to_sample_tray(
        self,
        tray_index: str | int,
    ) -> MoveValidationResult:
        """
        Validate and execute movement to the sample tray ready position.

        Per-sample slot moves use :meth:`validated_move_to_hardness_sample`.

        Args:
            tray_index: Zero-based tray index configured in
                ``motion_platform_positions.json``.

        Returns:
            MoveValidationResult with outcome.
        """
        try:
            tray_index_int = int(str(tray_index))
        except (TypeError, ValueError):
            return MoveValidationResult(
                valid=False,
                reason=f"Tray index '{tray_index}' must be a non-negative integer",
            )

        if tray_index_int < 0:
            return MoveValidationResult(
                valid=False, reason="Tray index must be non-negative"
            )

        tray_ready = next(
            (
                position
                for position in self._registry._positions.values()
                if position.type == PositionType.HARDNESS_SAMPLE_READY
                and position.metadata.get("tray_index") == tray_index_int
            ),
            None,
        )
        if tray_ready is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Sample tray with tray_index={tray_index_int} is not configured",
            )

        pos_result = self._resolve_ready_position_coords(
            tray_ready.identifier, require_v=False
        )
        if pos_result.error:
            return pos_result.error
        if pos_result.coords is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Sample tray '{tray_ready.identifier}' coordinates could not be resolved",
            )

        ready_x, ready_y, ready_z, _ = pos_result.coords
        return self._validate_and_execute_move(
            target_position_id=tray_ready.identifier,
            execution_func=self._executor.execute_move_to_sample_tray,
            x=ready_x,
            y=ready_y,
            z=ready_z,
        )

    def validated_move_to_hardness_sample(
        self,
        tray_index: str | int,
        sample_id: str | int,
    ) -> MoveValidationResult:
        """
        Validate and execute movement to a specific hardness sample slot.

        Resolves the per-slot position from the registry using the
        ``sample_tray_{tray_index}_slot_{sample_id}`` identifier. The
        state machine owns all coordinate validation; the executor
        receives only the resolved (x, y, z) floats.

        Args:
            tray_index: Zero-based tray index.
            sample_id: Sample index within the tray.

        Returns:
            MoveValidationResult with outcome.
        """
        try:
            tray_index_int = int(str(tray_index))
        except (TypeError, ValueError):
            return MoveValidationResult(
                valid=False,
                reason=f"Tray index '{tray_index}' must be a non-negative integer",
            )
        if tray_index_int < 0:
            return MoveValidationResult(
                valid=False, reason="Tray index must be non-negative"
            )

        try:
            sample_index = int(str(sample_id))
        except (TypeError, ValueError):
            return MoveValidationResult(
                valid=False,
                reason=f"Sample id '{sample_id}' must be a non-negative integer",
            )
        if sample_index < 0:
            return MoveValidationResult(
                valid=False, reason="Sample id must be non-negative"
            )

        slot_id = f"sample_tray_{tray_index_int}_slot_{sample_index}"
        if not self._registry.has(slot_id):
            return MoveValidationResult(
                valid=False,
                reason=f"Sample slot '{slot_id}' is not registered in the position configuration",
            )

        pos_result = self._resolve_ready_position_coords(slot_id, require_v=False)
        if pos_result.error:
            return pos_result.error
        if pos_result.coords is None:
            return MoveValidationResult(
                valid=False,
                reason=f"Sample slot '{slot_id}' coordinates could not be resolved",
            )
        ready_x, ready_y, ready_z, _ = pos_result.coords

        return self._validate_and_execute_move(
            target_position_id=slot_id,
            execution_func=self._executor.execute_move_to_hardness_sample,
            x=ready_x,
            y=ready_y,
            z=ready_z,
        )

    def validated_test_sample(
        self,
        tray_index: str | int,
        sample_id: str | int,
        mode: str | None = None,
        hardness_tester: HardnessTester | None = None,
        image_save_path: str | Path | None = None,
    ) -> MoveValidationResult:
        """
        Validate and execute the hardness measurement at the current sample slot.

        The machine must already be positioned at the target slot (via
        ``validated_move_to_hardness_sample``) before this action is called.

        Args:
            tray_index: Zero-based tray index.
            sample_id: Sample index within the tray.
            mode: Optional Shore mode (``"shore_a"`` or ``"shore_d"``).
            hardness_tester: ``HardnessTester`` used for LCD capture.
            image_save_path: Optional path for a debug camera frame.

        Returns:
            MoveValidationResult with outcome. OCR results are stored on the
            executor as ``last_hardness_result`` and ``last_hardness_error``.
        """
        try:
            tray_index_int = int(str(tray_index))
        except (TypeError, ValueError):
            return MoveValidationResult(
                valid=False,
                reason=f"Tray index '{tray_index}' must be a non-negative integer",
            )

        return self._validate_and_execute(
            action_id="test_sample",
            execution_func=self._executor.execute_test_sample,
            tray_index=tray_index_int,
            sample_id=str(sample_id),
            mode=mode,
            hardness_tester=hardness_tester,
            image_save_path=image_save_path,
        )

    @staticmethod
    def _extract_servo_angles(
        hardness_tester: object | None, button: str
    ) -> tuple[str | None, int | None, int | None, str | None]:
        """Extract and validate servo channel and angles from a HardnessTester.

        Args:
            hardness_tester: HardnessTester instance (duck-typed).
            button: "power" or "zero".

        Returns:
            (servo_channel, press_angle, release_angle, error_message).
            error_message is None on success; a descriptive string on failure.
            Both angles are validated to be in [0, 180].
        """
        if hardness_tester is None:
            return None, None, None, "hardness_tester is required for servo actuation"

        servo_id = getattr(hardness_tester, "servo", None)
        tester_mode = getattr(hardness_tester, "tester_mode", "unknown")

        if button == "power":
            press_angle = getattr(hardness_tester, "power_press_angle", None)
            release_angle = getattr(hardness_tester, "power_release_angle", None)
        elif button == "zero":
            press_angle = getattr(hardness_tester, "zero_press_angle", None)
            release_angle = getattr(hardness_tester, "zero_release_angle", None)
        else:
            return (
                None,
                None,
                None,
                f"Unknown button '{button}'; expected 'power' or 'zero'",
            )

        if not servo_id:
            return None, None, None, (f"No servo configured on {tester_mode} tester")

        if press_angle is None or release_angle is None:
            return (
                None,
                None,
                None,
                (
                    f"Servo angles for '{button}' button are not configured on {tester_mode} tester"
                ),
            )

        for label, angle in (("press", press_angle), ("release", release_angle)):
            if not (0 <= int(angle) <= 180):
                return (
                    None,
                    None,
                    None,
                    (
                        f"Servo {label}_angle {angle} is out of range [0, 180] "
                        f"for '{button}' button on {tester_mode} tester"
                    ),
                )

        s = str(servo_id).strip()
        try:
            channel = int(s[1:]) if s.upper().startswith("S") else int(s)
        except ValueError:
            return None, None, None, f"Cannot parse servo identifier '{servo_id}'"

        return channel, int(press_angle), int(release_angle), None

    def validated_hardness_turn_on(
        self, mode: str | None = None, hardness_tester: HardnessTester | None = None
    ) -> MoveValidationResult:
        """
        Validate and execute hardness tester power-on button actuation.

        Extracts the servo channel and press/release angles from hardness_tester,
        validates that both angles are in the range [0, 180], then delegates to
        the executor. This action is intentionally allowed at any position.

        Args:
            mode: Optional Shore mode string (for logging).
            hardness_tester: ``HardnessTester`` with servo configuration.

        Returns:
            MoveValidationResult with outcome.
        """
        channel, press, release, err = self._extract_servo_angles(
            hardness_tester, "power"
        )
        if err:
            return MoveValidationResult(valid=False, reason=err)
        return self._validate_and_execute(
            action_id="hardness_turn_on",
            execution_func=self._executor.execute_hardness_turn_on,
            mode=mode,
            servo_channel=channel,
            press_angle=press,
            release_angle=release,
        )

    def validated_hardness_turn_off(
        self, mode: str | None = None, hardness_tester: HardnessTester | None = None
    ) -> MoveValidationResult:
        """
        Validate and execute hardness tester power-off button actuation.

        Extracts the servo channel and press/release angles from hardness_tester,
        validates that both angles are in the range [0, 180], then delegates to
        the executor. This action is intentionally allowed at any position.

        Args:
            mode: Optional Shore mode string (for logging).
            hardness_tester: ``HardnessTester`` with servo configuration.

        Returns:
            MoveValidationResult with outcome.
        """
        channel, press, release, err = self._extract_servo_angles(
            hardness_tester, "power"
        )
        if err:
            return MoveValidationResult(valid=False, reason=err)
        return self._validate_and_execute(
            action_id="hardness_turn_off",
            execution_func=self._executor.execute_hardness_turn_off,
            mode=mode,
            servo_channel=channel,
            press_angle=press,
            release_angle=release,
        )

    def validated_hardness_zero(
        self, mode: str | None = None, hardness_tester: HardnessTester | None = None
    ) -> MoveValidationResult:
        """
        Validate and execute hardness tester zero button actuation.

        Extracts the servo channel and press/release angles from hardness_tester,
        validates that both angles are in the range [0, 180], then delegates to
        the executor. This action is intentionally allowed at any position.

        Args:
            mode: Optional Shore mode string (for logging).
            hardness_tester: ``HardnessTester`` with servo configuration.

        Returns:
            MoveValidationResult with outcome.
        """
        channel, press, release, err = self._extract_servo_angles(
            hardness_tester, "zero"
        )
        if err:
            return MoveValidationResult(valid=False, reason=err)
        return self._validate_and_execute(
            action_id="hardness_zero",
            execution_func=self._executor.execute_hardness_zero,
            mode=mode,
            servo_channel=channel,
            press_angle=press,
            release_angle=release,
        )

    def validated_fill_powder(self, target_weight: float) -> MoveValidationResult:
        """Validate and execute trickler fill at ``scale_active``.

        Args:
            target_weight: Target powder mass in grams.

        Returns:
            :class:`MoveValidationResult`. Final stable weight is available on
            :attr:`last_fill_weight` after success.

        Note:
            Requires tool engaged with mold on scale. Jam handling may pause the
            fill loop until an operator clears the blockage.
        """
        # Domain-specific validation
        if self.context.position_id != "scale_active":
            return MoveValidationResult(
                valid=False,
                reason=f"Must be at scale_active position to fill powder. Current: {self.context.position_id}",
            )

        if not self.context.mold_on_scale:
            return MoveValidationResult(
                valid=False, reason="Mold must be on scale before filling with powder"
            )

        # Execute through generic validation framework
        return self._validate_and_execute(
            action_id="fill_mold",
            execution_func=self._executor.execute_fill_powder,
            target_weight=target_weight,
        )

    def validated_open_powder_dispenser_cover(self) -> MoveValidationResult:
        """
        Validate and execute opening the powder dispenser cover.

        Requires the manipulator tool to be active, a mold to be placed on the
        scale, and the tool to be engaged at the scale_active position.

        Returns:
            MoveValidationResult with outcome
        """
        return self._validate_and_execute(
            action_id="open_powder_dispenser_cover",
            execution_func=self._executor.execute_open_powder_dispenser_cover,
        )

    def validated_close_powder_dispenser_cover(self) -> MoveValidationResult:
        """
        Validate and execute closing the powder dispenser cover.

        Requires the manipulator tool to be active, a mold to be placed on the
        scale, and the tool to be engaged at the scale_active position.

        Returns:
            MoveValidationResult with outcome
        """
        return self._validate_and_execute(
            action_id="close_powder_dispenser_cover",
            execution_func=self._executor.execute_close_powder_dispenser_cover,
        )

    def validated_move_to_global_ready(self) -> MoveValidationResult:
        """
        Validate and execute movement to the global ready position.

        Resolves base coordinates from config and moves to global_ready.

        Returns:
            MoveValidationResult with outcome.
        """
        global_ready_pos = self._registry.find_first_of_type(PositionType.GLOBAL_READY)
        if global_ready_pos is None:
            return MoveValidationResult(
                valid=False, reason="global_ready position not defined in configuration"
            )

        pos_result = self._resolve_ready_position_coords(global_ready_pos.identifier)
        if pos_result.error:
            return pos_result.error
        if pos_result.coords is None:
            return MoveValidationResult(
                valid=False,
                reason="Could not resolve coordinates for global_ready",
            )
        ready_x, ready_y, ready_z, ready_v = pos_result.coords

        return self._validate_and_execute_move(
            target_position_id=global_ready_pos.identifier,
            execution_func=self._executor.execute_move_to_scale_location,
            ready_x=ready_x,
            ready_y=ready_y,
            ready_z=ready_z,
            ready_v=ready_v,
        )

    def validated_home_tamper(
        self,
        tamper_axis: str | None = None,
    ) -> MoveValidationResult:
        """Validate and execute tamper (V-axis) homing.

        Uses the mold cavity as a mechanical reference when carrying a mold
        **without** a top piston:

        - Start: ``v=2`` (tamper inserted into mold)
        - End: ``v=-7`` (tamper at mold bottom)

        Args:
            tamper_axis: Axis letter; defaults to
                ``manipulator.tamper_axis`` from ``system_config.json``.

        Returns:
            :class:`MoveValidationResult`.

        Warning:
            Do not home while the mold has a top piston inserted. The travel
            path can damage the tamper or piston.
        """
        return self._validate_and_execute(
            action_id="home_manipulator",
            execution_func=self._executor.execute_home_tamper,
            tamper_axis=self._axis_or_config(tamper_axis),
        )

    def validated_home_all(self) -> MoveValidationResult:
        """Validate and execute homing for all axes (X, Y, Z, U).

        Returns the machine to ``global_ready`` and sets ``z_height_id`` to
        ``mold_transfer_safe`` on success.

        Returns:
            :class:`MoveValidationResult`.

        Warning:
            Requires empty payload and no manipulator tool picked up. Homing
            with a mold or active tool can collide with labware.
        """
        result = self._validate_and_execute(
            action_id="home_all",
            execution_func=self._executor.execute_home_all,
            registry=self._registry,
        )

        # If successful, update context to reflect position change to global_ready
        if result.valid:
            global_ready_pos = self._registry.find_first_of_type(
                PositionType.GLOBAL_READY
            )
            if global_ready_pos:
                self.context.position_id = global_ready_pos.identifier
                # Set z_height to mold_transfer_safe (default after homing)
                self.context.z_height_id = "mold_transfer_safe"

        return result

    def validated_home_manipulator(
        self,
        manipulator_axis: str | None = None,
    ) -> MoveValidationResult:
        """Validate and execute homing for the manipulator axis (V).

        Args:
            manipulator_axis: Axis letter; defaults to
                ``manipulator.tamper_axis`` from ``system_config.json``.

        Returns:
            :class:`MoveValidationResult`.

        Warning:
            Requires ``payload_state`` of ``empty``. For homing while holding a
            mold without top piston, use :meth:`validated_home_tamper` instead.
        """
        return self._validate_and_execute(
            action_id="home_manipulator",
            execution_func=self._executor.execute_home_manipulator,
            manipulator_axis=self._axis_or_config(manipulator_axis),
        )

    def validated_home_trickler(self, trickler_axis: str = "W") -> MoveValidationResult:
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
            trickler_axis=trickler_axis,
        )

    def validated_pickup_tool(self, tool: object) -> MoveValidationResult:
        """
        Validate and execute picking up a tool.

        Valid only from global_ready position. Requires no tool already
        picked up and mold_transfer_safe z_height. Returns to global_ready
        position. After the pickup completes, the active tool offset is
        switched to the tool's configured default offset (e.g. picking up
        a hardness tester loads the durometer offset). The offset is applied
        only AFTER the machine has settled at global_ready, so the offset
        transition cannot put the new tool tip in an unsafe position.

        Note: The machine's pickup_tool() method is decorated with @requires_safe_z,
        which automatically raises the bed height to deck.safe_z + 20 if it is not
        already at that height.

        Args:
            tool: The Tool object to pick up

        Returns:
            MoveValidationResult with outcome
        """
        if not hasattr(tool, "name") or not tool.name:
            return MoveValidationResult(
                valid=False,
                reason=f"Tool must expose a non-empty name. Attempted to pick up: {type(tool).__name__}",
            )

        tool_id = str(tool.name)
        supported_tool_ids = self._registry.supported_tool_ids
        if tool_id not in supported_tool_ids:
            return MoveValidationResult(
                valid=False,
                reason=f"Unsupported tool '{tool_id}'. Supported tools: {self._format_options(supported_tool_ids)}",
            )

        # Pickup is only valid from global_ready (enforced by the action's
        # position_scope). Resolve the recentering coordinates here so the
        # executor only has to drive the machine after the tpost macro completes.
        global_ready_pos = self._registry.find_first_of_type(PositionType.GLOBAL_READY)
        if global_ready_pos is None:
            return MoveValidationResult(
                valid=False,
                reason="GLOBAL_READY position is not defined in configuration",
            )
        gr_resolved = self._resolve_ready_position_coords(
            global_ready_pos.identifier,
        )
        if gr_resolved.error:
            return gr_resolved.error
        gr_x, gr_y, gr_z, gr_v = gr_resolved.coords

        result = self._validate_and_execute(
            action_id="pickup_tool",
            execution_func=self._executor.execute_pickup_tool,
            tool=tool,
            global_ready_x=gr_x,
            global_ready_y=gr_y,
            global_ready_z=gr_z,
            global_ready_v=gr_v,
        )

        # If successful, update context to reflect tool pickup and position change
        if result.valid:
            # Update active tool
            self.context.active_tool_id = tool_id
            self.register_tool(ToolStatus(tool_id=tool_id))
            # Update position to global_ready
            global_ready_pos = self._registry.find_first_of_type(
                PositionType.GLOBAL_READY
            )
            if global_ready_pos:
                self.context.position_id = global_ready_pos.identifier
                # Set z_height to mold_transfer_safe
                self.context.z_height_id = "mold_transfer_safe"

        return result

    def validated_park_tool(self) -> MoveValidationResult:
        """
        Validate and execute parking the current tool.

        Valid from global_ready position. Requires a supported tool to be active.
        Returns to global_ready position.

        Note: The machine's park_tool() method is decorated with @requires_safe_z,
        which automatically raises the bed height to deck.safe_z + 20 if it is not
        already at that height.

        Returns:
            MoveValidationResult with outcome
        """
        global_ready_pos = self._registry.find_first_of_type(PositionType.GLOBAL_READY)
        if global_ready_pos is None:
            return MoveValidationResult(
                valid=False,
                reason="GLOBAL_READY position is not defined in configuration",
            )
        gr_resolved = self._resolve_ready_position_coords(
            global_ready_pos.identifier,
        )
        if gr_resolved.error:
            return gr_resolved.error
        gr_x, gr_y, gr_z, gr_v = gr_resolved.coords

        result = self._validate_and_execute(
            action_id="park_tool",
            execution_func=self._executor.execute_park_tool,
            global_ready_x=gr_x,
            global_ready_y=gr_y,
            global_ready_z=gr_z,
            global_ready_v=gr_v,
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
        self, manipulator_config: dict[str, object]
    ) -> MoveValidationResult:
        """Validate and execute piston retrieval at the current dispenser.

        Derives the dispenser index from ``context.position_id`` (for example
        ``dispenser_ready_0`` maps to dispenser 0). Call
        :meth:`validated_move_to_dispenser` first. On success, decrements the
        dispenser count and sets ``has_top_piston`` on the carried mold.

        Args:
            manipulator_config: Manipulator settings dict (must include
                ``tamper_axis``).

        Returns:
            :class:`MoveValidationResult`.

        Note:
            Requires manipulator tool active, ``mold_without_top_piston``
            payload, and a ``dispenser_ready_N`` position with pistons remaining.
        """
        # Derive which dispenser we're at from the current position id
        pos_id = self.context.position_id
        prefix = "dispenser_ready_"
        if not pos_id.startswith(prefix):
            return MoveValidationResult(
                valid=False,
                reason=f"Must be at a dispenser_ready position to retrieve a piston. Current: {pos_id}",
            )
        try:
            dispenser_index = int(pos_id[len(prefix) :])
        except ValueError:
            return MoveValidationResult(
                valid=False,
                reason=f"Cannot determine dispenser index from position '{pos_id}'",
            )

        dispensers = self.context.piston_dispensers
        if dispenser_index < 0 or dispenser_index >= len(dispensers):
            return MoveValidationResult(
                valid=False,
                reason=f"Dispenser index {dispenser_index} derived from position '{pos_id}' is out of range",
            )
        piston_dispenser = dispensers[dispenser_index]

        if self.context.current_well is None:
            return MoveValidationResult(valid=False, reason="Not carrying a mold")

        mold = self.context.current_well

        if mold.has_top_piston:
            return MoveValidationResult(
                valid=False, reason="Mold already has a top piston"
            )

        if piston_dispenser.num_pistons == 0:
            return MoveValidationResult(
                valid=False, reason="No pistons available in dispenser"
            )

        if self.context.mold_on_scale:
            return MoveValidationResult(
                valid=False, reason="Cannot add top piston when mold is on scale"
            )

        # Resolve the dispenser ready position coordinates
        dispenser_ready_id = f"dispenser_ready_{piston_dispenser.index}"
        pos_result = self._resolve_ready_position_coords(dispenser_ready_id)
        if pos_result.error:
            return pos_result.error
        ready_x, ready_y, ready_z, ready_v = pos_result.coords

        # Validate and execute the action through the state machine
        result = self._validate_and_execute(
            action_id="retrieve_piston",
            execution_func=self._executor.execute_place_top_piston,
            piston_dispenser=piston_dispenser,
            tamper_axis=manipulator_config["tamper_axis"],
            ready_x=ready_x,
            ready_y=ready_y,
            ready_z=ready_z,
            ready_v=ready_v,
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

        Args:
            request: Target position and optional action metadata.

        Returns:
            MoveValidationResult indicating whether the request was accepted.
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
        """
        Validate whether an auxiliary action is permitted at the current state.

        Args:
            action_id: Action identifier from ``motion_platform_positions.json``.

        Returns:
            MoveValidationResult with ``valid=True`` when all action constraints
            (tool, engagement, position scope, requirements) are satisfied.
        """
        descriptor = self._actions.get(action_id)
        if descriptor is None:
            return MoveValidationResult(
                valid=False, reason=f"Unknown action '{action_id}'."
            )

        # Check if action requires tool engagement (e.g., fill_mold)
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

        Args:
            request: Move request with ``target_position_id``.

        Returns:
            MoveValidationResult with outcome (does not execute motion).
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
            if (
                request.target_position_id
                not in current_descriptor.allowed_destinations
            ):
                allowed = self._format_options(current_descriptor.allowed_destinations)
                return MoveValidationResult(
                    valid=False,
                    reason=(
                        f"Cannot move from '{self.context.position_id}' to "
                        f"'{request.target_position_id}'. Allowed destinations: {allowed}."
                    ),
                )

            if self.context.position_id not in target_descriptor.allowed_origins:
                allowed_origins = self._format_options(
                    target_descriptor.allowed_origins
                )
                return MoveValidationResult(
                    valid=False,
                    reason=(
                        f"'{request.target_position_id}' cannot accept moves from "
                        f"'{self.context.position_id}'. Allowed origins: {allowed_origins}."
                    ),
                )

        if self.current_state != self.tool_engaged:
            z_height_issue = target_descriptor.z_height_policy.validate(
                self.context.z_height_id
            )
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

        target_position = self._registry.get(
            self.context.pending_move.target_position_id
        )
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
        """Transition from idle to tool engaged at the current position.

        Returns:
            :class:`MoveValidationResult`. Succeeds only when the position
            ``allows_tool_engagement`` and engagement requirements pass.
        """
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
        """Disengage the tool and return the FSM to idle.

        Returns:
            :class:`MoveValidationResult`. Requires the FSM to be in
            ``tool_engaged`` with a known ``engaged_ready_position_id``.
        """
        if self.current_state != self.tool_engaged:
            return MoveValidationResult(
                valid=False, reason="No tool is currently engaged."
            )

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
        active_tool_id: str | None = None,
        payload_state: str | None = None,
        z_height_id: str | None = None,
    ) -> None:
        """Mutate commonly updated :class:`MotionContext` fields.

        Args:
            active_tool_id: Tool name to record as active, or ``None``.
            payload_state: Manipulator payload (``empty``,
                ``mold_without_top_piston``, ``mold_with_top_piston``).
            z_height_id: Active z-height policy id.

        Warning:
            Bypasses validation. Use only when the physical machine state is
            known to match the values being set.
        """
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
        """Check physical coordinates against the FSM's expected position.

        Called automatically before validated moves and actions.

        Args:
            machine_x: Reported X coordinate (mm).
            machine_y: Reported Y coordinate (mm).
            machine_z: Reported Z coordinate (mm).
            machine_v: Reported V coordinate (mm).

        Returns:
            :class:`MoveValidationResult` with coordinate mismatch details in
            ``reason`` when validation fails.
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

    def _validate_requirements(self, requirements: Mapping[str, object]) -> str | None:
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

    def _validate_excludes(self, excludes: Mapping[str, object]) -> str | None:
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
    def _machine_coords_from_position(current_pos: Mapping[str, object]) -> tuple[float, float, float, float]:
        """Convert machine position payload into validated numeric coordinates."""
        return (
            float(current_pos.get("X", 0)),
            float(current_pos.get("Y", 0)),
            float(current_pos.get("Z", 0)),
            float(current_pos.get("V", 0)),
        )

    @staticmethod
    def _format_options(options: Sequence[str] | Iterable[str]) -> str:
        """Render a collection of options as a comma-separated string."""
        return ", ".join(sorted({str(option) for option in options}))
