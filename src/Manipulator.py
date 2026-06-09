"""Manipulator toolhead for mold pick/place and tamping.

The :class:`Manipulator` is a Jubilee :class:`~science_jubilee.tools.Tool.Tool`
that drives mold handling through :class:`~src.MotionPlatformStateMachine.MotionPlatformStateMachine`.
Operations validate state before execution and update payload context
(``empty``, ``mold_without_top_piston``, ``mold_with_top_piston``).

Example:
    Pick a mold and place it on the scale::

        from src.Manipulator import Manipulator, ToolStateError

        manipulator = Manipulator(
            index=0,
            name="manipulator",
            state_machine=state_machine,
        )
        try:
            manipulator.pick_mold("0")
            manipulator.place_mold_on_scale()
        except ToolStateError as exc:
            print(f"Operation failed: {exc}")

Warning:
    A connected state machine is required. Motion methods raise
    :class:`RuntimeError` when ``state_machine`` is ``None``.

See Also:
    :class:`~src.JubileeManager.JubileeManager` for full dispense workflows.
"""

from science_jubilee.tools.Tool import (
    Tool,
    ToolStateError as _ExternalToolStateError,
)
from src.trickler_labware import Mold
from src.PistonDispenser import PistonDispenser
from src.MotionPlatformStateMachine import MotionPlatformStateMachine
from typing import Any


# Re-export ToolStateError for documentation purposes
class ToolStateError(_ExternalToolStateError):
    """Raised when a manipulator operation is attempted in an invalid state.

    Common causes:

    - Picking a mold when already holding one
    - Placing a mold when the payload is empty
    - Acting at the wrong named position for the requested operation
    - Tamp depth or speed outside bounds from ``system_config.json``

    Example:
        Handle at the call site::

            try:
                manipulator.pick_mold("0")
            except ToolStateError as exc:
                print(f"Pick blocked: {exc}")
    """

    pass


class Manipulator(Tool):
    """Jubilee gripper toolhead for mold handling and tamping.

    Delegates validation and motion to
    :class:`~src.MotionPlatformStateMachine.MotionPlatformStateMachine` and
    mirrors mold state on ``state_machine.context``.

    Attributes:
        state_machine: Motion platform FSM used for every pick/place/tamp call.
        tamper_axis: V-axis letter loaded from ``system_config.json``.
        current_well: :class:`~src.trickler_labware.Mold` carried by the
            manipulator, or ``None`` when empty (property).

    Warning:
        Direct :class:`~science_jubilee.Machine.Machine` moves bypass safety.
        Always move via :meth:`~src.MotionPlatformStateMachine.MotionPlatformStateMachine.validated_move_to_mold_slot`
        (or manager helpers) before pick/place.

    Note:
        Tamping and top-piston placement require a mold **without** a top piston.
    """

    # ============================================================================
    # CONFIGURATION PARAMETERS
    # ============================================================================
    # NOTE: The tamper axis letter is configured via self.tamper_axis (default 'V')
    # in __init__. Changing self.tamper_axis will update all axis references
    # throughout this class, including gcode commands.
    # ============================================================================

    def __init__(
        self,
        index: int,
        name: str,
        state_machine: MotionPlatformStateMachine | None = None,
        config_source: Any | None = None,
    ):
        """Initialize the manipulator tool.

        Args:
            index: Jubilee tool index (see ``tools.manipulator`` in config).
            name: Jubilee tool name registered with the firmware.
            state_machine: Connected
                :class:`~src.MotionPlatformStateMachine.MotionPlatformStateMachine`.
                Required for all motion methods.
            config_source: Unused; retained for call-site compatibility.

        Note:
            ``tamper_axis`` loads from ``system_config.json`` via
            :mod:`src.ConfigLoader` at construction time.
        """
        super().__init__(index, name)
        self.state_machine = state_machine  # Reference to MotionPlatformStateMachine

        # Tamper axis loaded from validated system_config.json
        self.tamper_axis: str = ""

        # TODO: tamper_speed should be derived from state machine feedrate default
        # For now, removed as it was only used in get_status() for reporting

        from src.ConfigLoader import config as _cfg

        self.tamper_axis = _cfg.system.manipulator.tamper_axis

    def _get_config_dict(self) -> dict[str, Any]:
        """Package manipulator settings for state machine validated calls.

        Returns:
            Dict with ``tamper_axis`` only. Z policies use ``context.z_height_id``
            and motion ``z_heights`` from JSON.
        """
        return {
            "tamper_axis": self.tamper_axis,
        }

    @property
    def current_well(self) -> Mold | None:
        """
        Mold object currently carried by the manipulator.

        Returns:
            ``Mold`` instance from the state machine context, or ``None`` when
            the manipulator is empty or no state machine is configured.
        """
        if self.state_machine:
            return self.state_machine.context.current_well
        return None

    def home_tamper(self, machine_connection: Any | None = None):
        """Home the tamper (V) axis through the state machine.

        Safe while holding a mold **without** a top piston. Homing uses the mold
        cavity as a mechanical reference:

        - Start: ``v=2`` (tamper inserted into mold)
        - End: ``v=-7`` (tamper at mold bottom)

        Args:
            machine_connection: Deprecated; ignored.

        Raises:
            RuntimeError: If ``state_machine`` is missing or homing fails.

        Warning:
            Do not home when the mold has a top piston. The travel path can
            damage the tamper or piston.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")

        # Validate and execute through state machine
        result = self.state_machine.validated_home_tamper(tamper_axis=self.tamper_axis)

        if not result.valid:
            raise RuntimeError(f"Tamper homing failed: {result.reason}")

    def tamp(self, tamp_depth: float, tamp_speed: int) -> bool:
        """Compress powder in the held mold (tamping).

        Tamping reduces powder volume so the top piston fits and limits airborne
        powder during piston insertion. Typically run at ``scale_ready`` after
        filling. The V axis is re-homed automatically afterward.

        Args:
            tamp_depth: Target depth in mm.
            tamp_speed: Feed rate in mm/min.

        Returns:
            ``True`` on success.

        Raises:
            RuntimeError: If ``state_machine`` is not configured.
            ToolStateError: If tamping is blocked or parameters are out of bounds.

        Note:
            Bounds and defaults live in ``system_config.json`` under
            ``manipulator``. Use :meth:`src.ConfigLoader.config.get_tamp_defaults`
            rather than hardcoding values.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")

        # Call state machine method which validates and executes
        result = self.state_machine.validated_tamp(
            manipulator_config=self._get_config_dict(),
            tamp_depth=tamp_depth,
            tamp_speed=tamp_speed,
        )

        if not result.valid:
            raise ToolStateError(f"Cannot tamp: {result.reason}")

        return True

    def get_status(self) -> dict[str, Any]:
        """Return manipulator status for telemetry and debugging.

        Returns:
            Dict with ``has_mold``, ``tamper_axis``, and optional ``current_well``
            metadata (name, weights, ``has_top_piston``, ``valid``).
        """
        status = {
            "has_mold": self.current_well is not None,
            "tamper_axis": self.tamper_axis,
        }

        if self.current_well is not None:
            status["current_well"] = {
                "name": getattr(self.current_well, "name", "unnamed"),
                "has_top_piston": self.current_well.has_top_piston,
                "valid": self.current_well.valid,
                "current_weight": self.current_well.current_weight,
                "target_weight": self.current_well.target_weight,
                "max_weight": self.current_well.max_weight,
            }
        else:
            status["current_well"] = None

        return status

    def is_carrying_mold(self) -> bool:
        """Return whether the manipulator is carrying a mold.

        Returns:
            ``True`` when :attr:`current_well` is not ``None``.
        """
        return self.current_well is not None

    def pick_mold(self, well_id: str):
        """Pick up a mold from ``mold_ready_{well_id}``.

        Args:
            well_id: Mold slot identifier (numerical string ``"0"`` through ``"17"``).

        Raises:
            RuntimeError: If ``state_machine`` is not configured.
            ToolStateError: If pickup is not allowed in the current state.

        Note:
            Call :meth:`~src.MotionPlatformStateMachine.MotionPlatformStateMachine.validated_move_to_mold_slot`
            first. Requires empty payload and manipulator tool active.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        result = self.state_machine.validated_pick_mold(
            well_id=well_id, manipulator_config=self._get_config_dict()
        )

        if not result.valid:
            raise ToolStateError(f"Cannot pick mold: {result.reason}")

    def place_mold(self, well_id: str) -> Mold | None:
        """Place the carried mold into ``mold_ready_{well_id}``.

        Args:
            well_id: Mold slot identifier (for example ``"0"``, ``"1"``).

        Returns:
            The :class:`~src.trickler_labware.Mold` that was placed, or ``None``
            if nothing was carried.

        Raises:
            RuntimeError: If ``state_machine`` is not configured.
            ToolStateError: If placement is not allowed in the current state.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")

        mold_to_place = self.current_well
        result = self.state_machine.validated_place_mold(
            well_id=well_id, manipulator_config=self._get_config_dict()
        )

        if not result.valid:
            raise ToolStateError(f"Cannot place mold: {result.reason}")

        return mold_to_place

    def place_top_piston(self, piston_dispenser: PistonDispenser) -> bool:
        """
        Place a top piston on the mold currently held by the manipulator.

        Only allowed when carrying a mold without a top piston and when the
        state machine is at a dispenser ready position.

        Args:
            piston_dispenser: Dispenser supplying the piston.

        Returns:
            True if successful.

        Raises:
            RuntimeError: If the state machine is not configured.
            ToolStateError: If placement is not allowed in the current state.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")

        # Call state machine method which validates and executes
        result = self.state_machine.validated_place_top_piston(
            piston_dispenser=piston_dispenser,
            manipulator_config=self._get_config_dict(),
        )

        if not result.valid:
            raise ToolStateError(f"Cannot place top piston: {result.reason}")

        return True

    def place_mold_on_scale(self) -> bool:
        """
        Place the mold currently held by the manipulator onto the scale.

        Only allowed when carrying a mold without a top piston. Engages the
        tool at ``scale_active`` on success.

        Returns:
            True if successful.

        Raises:
            RuntimeError: If the state machine is not configured.
            ToolStateError: If placement is not allowed in the current state.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")

        # Call state machine method which validates and executes
        result = self.state_machine.validated_place_mold_on_scale(
            manipulator_config=self._get_config_dict()
        )

        if not result.valid:
            raise ToolStateError(f"Cannot place mold on scale: {result.reason}")

        return True

    def pick_mold_from_scale(self) -> bool:
        """
        Pick up the mold resting on the scale.

        Requires the mold to be on the scale (``scale_active`` / tool engaged).
        Disengages the tool and returns to ``scale_ready`` on success.

        Returns:
            True if successful.

        Raises:
            RuntimeError: If the state machine is not configured.
            ToolStateError: If pickup is not allowed in the current state.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")

        # Call state machine method which validates and executes
        result = self.state_machine.validated_pick_mold_from_scale(
            manipulator_config=self._get_config_dict()
        )

        if not result.valid:
            raise ToolStateError(f"Cannot pick mold from scale: {result.reason}")

        return True
