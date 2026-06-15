"""Primary entry point for Jubilee powder dispensing automation.

Coordinates the Duet controller, scale, dispensers, and manipulator through an
internal :class:`~src.MotionPlatformStateMachine.MotionPlatformStateMachine`
so movements cannot bypass validation.

Example:
    Connect and dispense::

        from src.JubileeManager import JubileeManager

        manager = JubileeManager(
            num_piston_dispensers=2,
            num_pistons_per_dispenser=10,
        )
        if manager.connect():
            manager.dispense_to_well("0", target_weight=50.0)
            manager.disconnect()
"""

from __future__ import annotations

import logging
import time
import traceback
from typing import Callable, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from src.JobLog import JobLog

# Import Jubilee components
from science_jubilee.Machine import Machine
from science_jubilee.decks.Deck import Deck
from src.Scale import Scale
from src.PistonDispenser import PistonDispenser
from src.Manipulator import Manipulator, ToolStateError
from src.HardnessTester import HardnessTester
from src.MotionPlatformStateMachine import MotionPlatformStateMachine
from src.ConfigLoader import config

logger = logging.getLogger(__name__)


class ScaleResidualObjectError(RuntimeError):
    """Raised when scale weight does not return to baseline after mold pickup.

    Indicates a possible object left on the scale after the manipulator removed
    the mold. The residual exceeds ``safety.weight_tolerance`` from config.
    """


class JubileeManager:
    """High-level manager for Jubilee powder dispensing operations.

    Owns a :class:`~src.MotionPlatformStateMachine.MotionPlatformStateMachine`
    that validates every movement. Application code should call methods on this
    class rather than issuing moves through :attr:`machine_read_only`.

    Attributes:
        scale: Connected :class:`~src.Scale.Scale`, or ``None`` before connect.
        manipulator: :class:`~src.Manipulator.Manipulator` instance, or ``None``.
        state_machine: Internal FSM, or ``None`` before connect.
        connected: Whether hardware initialization completed successfully.

    Example:
        Typical connect / operate / disconnect flow::

            manager = JubileeManager(
                num_piston_dispensers=2,
                num_pistons_per_dispenser=10,
            )
            try:
                if manager.connect():
                    manager.dispense_to_well("0", 50.0)
            finally:
                manager.disconnect()

    Note:
        Always call :meth:`disconnect` when finished. Check :attr:`connected`
        before operations.

    Warning:
        Do not move axes through :attr:`machine_read_only`; that bypasses FSM
        validation and desynchronizes tracked state.
    """

    # TODO: Improve soft fail for scale tare, add functionality for if a communication failure occurs when mold is on scale it is automatically returned
    def __init__(
        self,
        num_piston_dispensers: int = 0,
        num_pistons_per_dispenser: int = 0,
    ) -> None:
        """Initialize the JubileeManager.

        Creates a manager with dispenser capacity metadata. Does not connect to
        hardware; call :meth:`connect` to establish connections.

        Args:
            num_piston_dispensers: Number of piston dispenser units to track.
            num_pistons_per_dispenser: Initial piston count per dispenser.

        Note:
            Feedrate and network addresses come from
            ``api_config/system_config.json`` at connect time.
        """
        self.scale: Scale | None = None
        self.manipulator: Manipulator | None = None
        self.hardness_tester_shore_a: HardnessTester | None = None
        self.hardness_tester_shore_d: HardnessTester | None = None
        self.state_machine: MotionPlatformStateMachine | None = None
        self.connected: bool = False
        self._num_piston_dispensers: int = num_piston_dispensers
        self._num_pistons_per_dispenser: int = num_pistons_per_dispenser
        self.active_job_log: "JobLog" | None = None
        self.last_dispense_weight: float | None = None
        self.last_hardness_result: float | None = None
        self.last_hardness_error: str | None = None
        self.last_hardness_image_path: str | None = None
        self.last_hardness_cv_bypassed: bool = False
        self.last_error: str | None = None
        self._on_jam_callback: Callable | None = None

    @property
    def machine_read_only(self) -> Machine | None:
        """Read-only access to the underlying Jubilee ``Machine``.

        Returns:
            The connected ``Machine`` instance, or ``None`` when disconnected.

        Warning:
            Named ``read_only`` intentionally. Querying position or status is
            fine; issuing moves here bypasses FSM validation and can cause
            collisions or lost state tracking.

        Example:
            Safe read-only query::

                if manager.machine_read_only:
                    pos = manager.machine_read_only.get_position()
        """
        if self.state_machine:
            return self.state_machine.machine
        return None

    @property
    def deck(self) -> Deck | None:
        """Access to the deck configuration and labware layout.

        Returns:
            The ``Deck`` instance when the state machine is initialized,
            otherwise ``None``.

        Example:
            List slots that have labware loaded::

                if manager.deck:
                    loaded = [
                        slot_key
                        for slot_key, slot in manager.deck.slots.items()
                        if slot.has_labware
                    ]
        """
        if self.state_machine:
            return self.state_machine.context.deck
        return None

    @property
    def piston_dispensers(self) -> list[PistonDispenser]:
        """Access to all configured piston dispensers.

        Returns:
            List of :class:`~src.PistonDispenser.PistonDispenser` instances.
            Empty when the state machine is not initialized.

        Example:
            Inspect remaining pistons::

                for dispenser in manager.piston_dispensers:
                    print(dispenser.index, dispenser.num_pistons)
        """
        if self.state_machine:
            return self.state_machine.context.piston_dispensers
        return []

    # ── Jam detection helpers ─────────────────────────────────────────────────

    @property
    def jam_detected(self) -> bool:
        """Whether the dispensing loop is blocked waiting for jam clearance.

        Returns:
            True while a powder jam requires operator intervention.
        """
        if self.state_machine and self.state_machine._executor:
            return self.state_machine._executor.jam_detected
        return False

    def set_jam_callback(self, callback: Callable | None) -> None:
        """Register a callback invoked when a powder jam requires operator clearance.

        The callback runs on the dispensing thread immediately before the loop
        blocks. It is not invoked for the first auto-recovered jam in each fill
        iteration. Keep it lightweight (for example set a flag in job progress).

        Args:
            callback: Callable to invoke on jam, or ``None`` to clear.
        """
        self._on_jam_callback = callback
        if self.state_machine and self.state_machine._executor:
            self.state_machine._executor._on_jam_detected = callback

    def clear_jam(self) -> None:
        """Resume dispensing after the operator has cleared the blockage.

        No-op when no active fill executor is running.
        """
        if self.state_machine and self.state_machine._executor:
            self.state_machine._executor.clear_jam()

    def connect(
        self,
        machine_address: str | None = None,
        scale_port: str | None = None,
        state_machine_config: str | None = None,
    ) -> bool:
        """Connect to hardware and initialize the system.

        Connects the Duet controller and scale, loads
        ``motion_platform_positions.json``, initializes deck and dispensers,
        homes axes, and registers tools. See the API page for the full sequence.

        Args:
            machine_address: Duet IP address. Defaults to
                ``machine.duet_ip`` from config when omitted.
            scale_port: Serial device path for the scale. Defaults to
                ``machine.scale_port`` from config when omitted.
            state_machine_config: Override path to
                ``motion_platform_positions.json``. Relative paths resolve
                against the project root.

        Returns:
            ``True`` when initialization succeeds; ``False`` on any failure.
            Check :attr:`connected` after calling.

        Raises:
            FileNotFoundError: When ``state_machine_config`` does not exist.
            RuntimeError: When homing fails.
            ConnectionError: When machine or scale connection fails.

        Note:
            Homing can take 30-60 seconds. Ensure axes are clear before calling.

        Warning:
            A partial failure may leave hardware in an unknown state. Reset
            before retrying connect.
        """
        try:
            _t0 = time.monotonic()

            # Use config IP if no address provided
            if machine_address is None:
                machine_address = config.get_duet_ip()
            if scale_port is None:
                scale_port = config.get_scale_port()

            # Connect to machine
            real_machine = Machine(address=machine_address)
            real_machine.connect()
            logger.debug("Duet connect: %.2fs", time.monotonic() - _t0)

            # Connect to scale first (needed for state machine initialization)
            _t1 = time.monotonic()
            self.scale = Scale(port=scale_port)
            self.scale.connect()
            logger.debug("Scale connect: %.2fs", time.monotonic() - _t1)

            project_root = config.project_root

            # Initialize the state machine with the real machine and scale
            # The state machine owns the machine and controls all access to it
            if state_machine_config is None:
                config_path = config.get_motion_config_path()
            else:
                config_path = Path(state_machine_config)
                if not config_path.is_absolute():
                    config_path = project_root / config_path
            if not config_path.exists():
                raise FileNotFoundError(
                    f"State machine config not found: {config_path}"
                )

            _t2 = time.monotonic()
            self.state_machine = MotionPlatformStateMachine.from_config_file(
                config_path,
                real_machine,
                scale=self.scale,
            )

            # Initialize deck and dispensers in state machine
            deck_config_path = config.get_api_config_dir()
            if self._num_piston_dispensers < 1:
                raise ValueError(
                    "num_piston_dispensers must be set from system_config before connect"
                )
            if self._num_pistons_per_dispenser < 0:
                raise ValueError(
                    "num_pistons_per_dispenser must be set from system_config before connect"
                )

            self.state_machine.initialize_deck(config_path=str(deck_config_path))
            self.state_machine.initialize_dispensers(
                num_piston_dispensers=self._num_piston_dispensers,
                num_pistons_per_dispenser=self._num_pistons_per_dispenser,
            )

            # Create manipulator with state machine reference
            # Config will default to system_config.json
            tool = config.system.tools.manipulator
            self.manipulator = Manipulator(
                index=tool.index,
                name=tool.name,
                state_machine=self.state_machine,
            )
            active_hardness_profile = config.get_active_hardness_profile()
            enable_monotonic_drop_check = (
                config.get_hardness_monotonic_drop_check_enabled()
            )
            testers = config.system.hardness_testers
            self.hardness_tester_shore_a = HardnessTester.from_system_config(
                tester_mode="shore_a",
                hardware_cfg=testers.shore_a,
                profile_cfg=active_hardness_profile,
                state_machine=self.state_machine,
                enable_monotonic_drop_check=enable_monotonic_drop_check,
            )
            self.hardness_tester_shore_d = HardnessTester.from_system_config(
                tester_mode="shore_d",
                hardware_cfg=testers.shore_d,
                profile_cfg=active_hardness_profile,
                state_machine=self.state_machine,
                enable_monotonic_drop_check=enable_monotonic_drop_check,
            )
            logger.debug("State machine + tools init: %.2fs", time.monotonic() - _t2)

            # Ensure state machine context is set correctly for homing
            # Set z_height_id to mold_transfer_safe which is the default height after homing
            self.state_machine.update_context(
                active_tool_id=None,
                payload_state="empty",
                z_height_id="mold_transfer_safe",
            )

            # Home all axes (X, Y, Z, U, V) through state machine
            # This requires no tool picked up and no mold
            # Returns to global_ready position at mold_transfer_safe z-height
            _t3 = time.monotonic()
            result = self.state_machine.validated_home_all()
            logger.debug(
                "validated_home_all (incl. post-home move + M400): %.2fs",
                time.monotonic() - _t3,
            )
            if not result.valid:
                raise RuntimeError(f"Failed to home all axes: {result.reason}")

            # Load tool definitions (register only; do not pick up yet).
            # The machine must know every tool object before validated pickup.
            #
            # Some firmware setups only expose a z-offset entry for the currently
            # active/default tool. In that case, science_jubilee raises KeyError
            # while loading additional tool indices. Seed missing entries so tool
            # registration can proceed.
            def _load_registered_tool(tool_obj: object) -> None:
                try:
                    self.machine_read_only.load_tool(tool_obj)
                except KeyError as exc:
                    missing_idx = exc.args[0] if exc.args else None
                    tool_idx = getattr(tool_obj, "index", None)
                    if missing_idx != tool_idx:
                        raise

                    tool_offsets = getattr(self.machine_read_only, "tool_z_offsets", None)
                    if not isinstance(tool_offsets, dict):
                        raise RuntimeError(
                            f"Machine missing tool_z_offsets while registering tool index {tool_idx}"
                        ) from exc

                    logger.warning(
                        "Missing machine z-offset entry for tool index %s; "
                        "defaulting to 0.0 for registration",
                        tool_idx,
                    )
                    tool_offsets[tool_idx] = 0.0
                    self.machine_read_only.load_tool(tool_obj)

            _t4 = time.monotonic()
            _load_registered_tool(self.manipulator)
            _load_registered_tool(self.hardness_tester_shore_a)
            _load_registered_tool(self.hardness_tester_shore_d)
            logger.debug("load_tool: %.2fs", time.monotonic() - _t4)
            logger.debug("Total connect: %.2fs", time.monotonic() - _t0)

            self.connected = True
            return True

        except Exception as e:
            self.last_error = str(e)
            print(f"Connection error: {e}")
            traceback.print_exc()
            self.connected = False
            return False

    def disconnect(self) -> None:
        """Disconnect from hardware and release resources.

        Safe to call when not connected or after a partial connect failure.
        Parks the active tool and powers off a mounted hardness tester first.

        Example:
            Always disconnect in ``finally``::

                manager = JubileeManager()
                try:
                    manager.connect()
                    ...
                finally:
                    manager.disconnect()
        """
        self._disconnect_cleanup()
        if self.machine_read_only:
            self.machine_read_only.disconnect()
        if self.scale:
            self.scale.disconnect()
        self.connected = False

    def get_weight_stable(self) -> float | None:
        """Return scale weight after the reading stabilizes.

        Returns:
            Weight in grams, or ``None`` when no scale is connected.

        Note:
            Waits for stability (typically 1-3 seconds). Prefer
            :meth:`get_weight_unstable` only for live monitoring during fill.
        """
        if self.scale and self.scale.is_connected:
            return self.scale.get_weight(stable=True)
        return None

    def get_weight_unstable(self) -> float | None:
        """Return the current scale weight without waiting for stability.

        Returns:
            Instantaneous weight in grams, or ``None`` when no scale is connected.

        Note:
            Suitable for live fill monitoring only. Record measurements with
            :meth:`get_weight_stable`.
        """
        if self.scale and self.scale.is_connected:
            return self.scale.get_weight(stable=False)
        return None

    def _record_scale_baseline_weight(self) -> float:
        """
        Capture a stable gross mold weight after placement, before taring.

        Returns:
            Stable baseline weight in grams.
        """
        baseline_weight = self.get_weight_stable()
        if baseline_weight is None:
            raise RuntimeError("Scale did not return a stable baseline weight")
        print(f"[Safety] Baseline scale weight with mold on pan: {baseline_weight:.4f}g")
        return baseline_weight

    def _validate_scale_clear_after_pickup(self, baseline_weight: float) -> None:
        """
        Ensure scale returns to baseline after mold pickup.

        Raises:
            ScaleResidualObjectError: If residual weight exceeds configured tolerance.
        """
        if self.scale is None or not self.scale.is_connected:
            raise RuntimeError("Scale is not connected or provided.")

        current_weight = self.get_weight_stable()
        if current_weight is None:
            raise RuntimeError("Scale did not return a stable post-pickup weight")

        residual_weight = -current_weight - baseline_weight
        tolerance = config.get_weight_tolerance()
        if abs(residual_weight) > tolerance:
            raise ScaleResidualObjectError(
                "Scale residual safety check failed after mold pickup. "
                f"Expected {baseline_weight:.4f}g (+/-{tolerance:.4f}g), "
                f"measured {current_weight:.4f}g (residual {residual_weight:+.4f}g). "
                "Possible object left on scale."
            )

    def _hardness_tester_for_tool_id(
        self, tool_id: str | None
    ) -> HardnessTester | None:
        """Return the configured hardness tester whose name matches tool_id."""
        if not tool_id:
            return None
        if (
            self.hardness_tester_shore_a
            and tool_id == self.hardness_tester_shore_a.name
        ):
            return self.hardness_tester_shore_a
        if (
            self.hardness_tester_shore_d
            and tool_id == self.hardness_tester_shore_d.name
        ):
            return self.hardness_tester_shore_d
        return None

    def _disconnect_cleanup(self) -> None:
        """Park the mounted tool and power off an active hardness tester before disconnect."""
        if not self.connected or not self.state_machine:
            return

        active_tool_id = self.state_machine.context.active_tool_id
        hardness_tester = self._hardness_tester_for_tool_id(active_tool_id)
        if hardness_tester is not None:
            try:
                hardness_tester.turn_off()
            except Exception as e:
                print(f"Disconnect cleanup: hardness turn-off failed: {e}")

        if active_tool_id is None:
            return

        try:
            self.park_active_tool()
        except Exception as e:
            print(f"Disconnect cleanup: park tool failed: {e}")

    def park_active_tool(self) -> bool:
        """Park the currently mounted tool if one is active.

        Moves to ``global_ready`` first when needed, then delegates to the state
        machine.

        Returns:
            True when no tool was active or parking succeeded.

        Raises:
            RuntimeError: If the state machine is missing or parking fails.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")

        if self.state_machine.context.position_id != "global_ready":
            self.move_to_global_ready()

        if self.state_machine.context.active_tool_id is None:
            return True

        park_result = self.state_machine.validated_park_tool()
        if not park_result.valid:
            raise RuntimeError(f"Failed to park active tool: {park_result.reason}")
        return True

    def pickup_tool(self, tool) -> bool:
        """Pick up the requested tool without assuming current tool state.

        Moves to ``global_ready`` first when needed.

        Args:
            tool: Tool instance to mount (for example :class:`~src.Manipulator.Manipulator`).

        Returns:
            True on success.

        Raises:
            RuntimeError: If the state machine is missing or pickup fails.
            ToolStateError: If ``tool`` is not configured.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        if not tool:
            raise ToolStateError("Requested tool is not configured")

        if self.state_machine.context.position_id != "global_ready":
            self.move_to_global_ready()

        pickup_result = self.state_machine.validated_pickup_tool(tool)
        if not pickup_result.valid:
            raise RuntimeError(
                f"Failed to pick up tool '{tool.name}': {pickup_result.reason}"
            )

        return True

    def ensure_tool_active(self, required_tool) -> bool:
        """Ensure the required tool is mounted.

        Parks any other active tool first, then picks up ``required_tool`` when
        nothing is mounted.

        Args:
            required_tool: Tool that must be active after this call.

        Returns:
            True when ``required_tool`` is already active or was mounted.

        Raises:
            RuntimeError: If the state machine is missing or tool swap fails.
            ToolStateError: If ``required_tool`` is not configured.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        if not required_tool:
            raise ToolStateError("Required tool is not configured")

        active_tool_id = self.state_machine.context.active_tool_id
        if active_tool_id == required_tool.name:
            return True

        if active_tool_id is not None:
            self.park_active_tool()

        self.pickup_tool(required_tool)
        return True

    # TODO: This handles combined shore a+d testing inappropriately
    def _resolve_hardness_tester(self, mode: str | None) -> HardnessTester:
        """Map hardness measurement pass (``shore_a`` / ``shore_d``) to a Shore tester."""
        if not mode:
            raise ValueError(
                "hardness mode is required: pass 'shore_a' or 'shore_d' for the measurement pass"
            )
        normalized_mode = mode.lower()
        if normalized_mode == "shore_d":
            if not self.hardness_tester_shore_d:
                raise ToolStateError("Shore-D hardness tester is not configured.")
            return self.hardness_tester_shore_d

        # shore_a and shore_a_d default to Shore-A tool selection
        if not self.hardness_tester_shore_a:
            raise ToolStateError("Shore-A hardness tester is not configured.")
        return self.hardness_tester_shore_a

    def dispense_to_well(self, well_id: str, target_weight: float) -> bool:
        """Run the full dispense workflow for one mold slot.

        Picks up the mold, fills on the scale, retrieves a piston, tamps, and
        returns the mold to its slot. Each step is validated by the FSM.

        Args:
            well_id: Deck well index as a string (for example ``"0"``).
            target_weight: Target powder mass in grams.

        Returns:
            ``True`` when every step succeeds; ``False`` when not connected or
            a handled error occurs.

        Raises:
            ToolStateError: When manipulator or scale is unavailable.
            RuntimeError: When the state machine is missing.
            ValueError: When ``well_id`` is unknown or ``target_weight`` exceeds
                ``safety.max_weight_per_well``.

        Warning:
            A mid-workflow failure may leave the mold at an intermediate
            position. Manual recovery may be required.
        """
        if not self.connected:
            return False
        self.last_error = None
        try:
            if not self.manipulator:
                raise ToolStateError("Manipulator is not connected or provided.")

            if not self.scale or not self.scale.is_connected:
                raise ToolStateError("Scale is not connected or provided.")

            if not self.state_machine:
                raise RuntimeError("State machine not configured")

            self.ensure_tool_active(self.manipulator)

            max_weight = config.get_max_weight_per_well()
            if target_weight > max_weight:
                raise ValueError(
                    f"target_weight {target_weight}g exceeds safety.max_weight_per_well "
                    f"({max_weight}g) in system_config.json"
                )

            self.move_to_mold_slot(well_id)
            self.manipulator.pick_mold(well_id)
            self.move_to_global_ready()
            self.move_to_scale()
            self.scale.zero()
            self.manipulator.place_mold_on_scale()
            baseline_weight = self._record_scale_baseline_weight()
            self.scale.tare()
            self.fill_powder(target_weight)
            self.manipulator.pick_mold_from_scale()
            self._validate_scale_clear_after_pickup(baseline_weight)
            self.scale.zero()
            tamp_depth, tamp_speed = config.get_tamp_defaults()
            tamp_depth = min(float(tamp_depth), config.get_tamp_depth_max())
            self.manipulator.tamp(tamp_depth=tamp_depth, tamp_speed=tamp_speed)
            self.move_to_global_ready()
            self.move_to_dispenser()
            self.get_piston_from_dispenser()
            self.move_to_global_ready()
            self.move_to_mold_slot(well_id)
            self.manipulator.place_mold(well_id)
            self.move_to_global_ready()
            self.manipulator.home_tamper()
            if self.active_job_log is not None:
                self.active_job_log.update_well(well_id)
            return True
        except ScaleResidualObjectError:
            raise
        except Exception as e:
            self.last_error = str(e)
            print(f"Error filling mold: {e}")
            traceback.print_exc()
            return False

    def test_sample(
        self,
        tray_index: int,
        sample_index: int,
        mode: str,
        image_save_path: str | Path | None = None,
    ) -> bool:
        """Run a hardness measurement on one tray sample.

        Selects the Shore-A or Shore-D tester from ``mode``, ensures it is
        mounted, and delegates to :meth:`~src.HardnessTester.HardnessTester.test_sample`.
        Results are stored on ``last_hardness_result``, ``last_hardness_error``,
        and ``last_hardness_image_path``.

        Args:
            tray_index: Zero-based hardness tray index.
            sample_index: Sample position within the tray.
            mode: Measurement pass: ``shore_a`` or ``shore_d``.
            image_save_path: Optional directory for debug capture images.

        Returns:
            True when the workflow completed without exception, False when not
            connected or an error was caught.
        """
        if not self.connected:
            return False
        self.last_error = None
        try:
            if not self.state_machine:
                raise RuntimeError("State machine not configured")
            self.last_hardness_result = None
            self.last_hardness_error = None
            self.last_hardness_image_path = None
            self.last_hardness_cv_bypassed = False

            selected_tester = self._resolve_hardness_tester(mode)
            self.ensure_tool_active(selected_tester)
            measurement = selected_tester.test_sample(
                tray_index,
                sample_index,
                self.state_machine,
                image_save_path=image_save_path,
            )
            if isinstance(measurement, dict):
                self.last_hardness_result = measurement.get("result")
                self.last_hardness_error = measurement.get("sample_error")
                self.last_hardness_image_path = measurement.get("image_path")
                self.last_hardness_cv_bypassed = bool(measurement.get("cv_bypassed"))
            else:
                self.last_hardness_result = None
                self.last_hardness_error = (
                    "Hardness tester did not return measurement metadata."
                )
                self.last_hardness_cv_bypassed = False

            if self.active_job_log is not None:
                self.active_job_log.update_sample(
                    sample_index,
                    tray_index=tray_index,
                    result=self.last_hardness_result,
                    sample_error=self.last_hardness_error,
                    measurement_mode=selected_tester.tester_mode,
                    image_path=self.last_hardness_image_path,
                )
            return True
        except Exception as e:
            self.last_error = str(e)
            print(f"Error testing hardness sample: {e}")
            traceback.print_exc()
            return False

    def hardness_turn_on(self, mode: str | None = None) -> bool:
        """Power on a Shore hardness tester via its servo button.

        Args:
            mode: ``shore_a`` or ``shore_d``. Required (``None`` raises
                :class:`ValueError`).

        Returns:
            True on success, False when not connected or an error was caught.
        """
        if not self.connected:
            return False
        try:
            if not self.state_machine:
                raise RuntimeError("State machine not configured")
            selected_tester = self._resolve_hardness_tester(mode)
            self.ensure_tool_active(selected_tester)
            selected_tester.turn_on()
            return True
        except Exception as e:
            print(f"Error turning on hardness tester: {e}")
            return False

    def hardness_turn_off(self, mode: str | None = None) -> bool:
        """Power off a Shore hardness tester via its servo button.

        Args:
            mode: ``shore_a`` or ``shore_d``. Required (``None`` raises
                :class:`ValueError`).

        Returns:
            True on success, False when not connected or an error was caught.
        """
        if not self.connected:
            return False
        try:
            if not self.state_machine:
                raise RuntimeError("State machine not configured")
            selected_tester = self._resolve_hardness_tester(mode)
            self.ensure_tool_active(selected_tester)
            selected_tester.turn_off()
            return True
        except Exception as e:
            print(f"Error turning off hardness tester: {e}")
            return False

    def hardness_zero(self, mode: str | None = None) -> bool:
        """Zero a Shore hardness tester via its servo button.

        Args:
            mode: ``shore_a`` or ``shore_d``. Required (``None`` raises
                :class:`ValueError`).

        Returns:
            True on success, False when not connected or an error was caught.
        """
        if not self.connected:
            return False
        try:
            if not self.state_machine:
                raise RuntimeError("State machine not configured")
            selected_tester = self._resolve_hardness_tester(mode)
            self.ensure_tool_active(selected_tester)
            selected_tester.zero()
            return True
        except Exception as e:
            print(f"Error zeroing hardness tester: {e}")
            return False

    def move_to_dispenser(self) -> bool:
        """Move to the next available piston dispenser ready position.

        Returns:
            ``True`` on success; ``False`` when not connected.

        Raises:
            RuntimeError: When the state machine is missing or validation fails.
        """
        if not self.connected:
            return False

        if not self.state_machine:
            raise RuntimeError("State machine not configured")

        try:
            result = self.state_machine.validated_move_to_dispenser()

            if not result.valid:
                raise RuntimeError(
                    f"Failed to move to dispenser position: {result.reason}"
                )

            return True
        except Exception as e:
            print(f"Error moving to dispenser: {e}")
            return False

    def get_piston_from_dispenser(self) -> bool:
        """Retrieve a piston at the current dispenser ready position.

        Returns:
            ``True`` on success; ``False`` when not connected.

        Raises:
            RuntimeError: When the state machine is missing or validation fails.

        Warning:
            Call :meth:`move_to_dispenser` first. The FSM rejects retrieval from
            the wrong position.
        """
        if not self.connected:
            return False

        if not self.state_machine:
            raise RuntimeError("State machine not configured")

        try:
            result = self.state_machine.validated_retrieve_piston(
                manipulator_config=self.manipulator._get_config_dict()
            )

            if not result.valid:
                raise RuntimeError(f"Failed to retrieve piston: {result.reason}")

            return True
        except Exception as e:
            print(f"Getting piston from dispenser error: {e}")
            return False

    def move_to_mold_slot(self, well_id: str) -> bool:
        """Move to a mold slot ready position.

        Args:
            well_id: Deck well index as a string (for example ``"0"``).

        Returns:
            ``True`` when the validated move succeeds.

        Raises:
            RuntimeError: When validation fails.
            KeyError: When ``well_id`` is not in the deck layout.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")

        result = self.state_machine.validated_move_to_mold_slot(well_id=well_id)
        if not result.valid:
            raise RuntimeError(f"Move to mold slot failed: {result.reason}")
        return True

    def move_to_global_ready(self) -> bool:
        """Move to the global ready transit position.

        Returns:
            True when the validated move succeeds.

        Raises:
            RuntimeError: If the state machine is missing or validation fails.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")

        result = self.state_machine.validated_move_to_global_ready()
        if not result.valid:
            raise RuntimeError(f"Move to mold slot failed: {result.reason}")
        return True

    def move_to_scale(self) -> bool:
        """Move to the scale ready position.

        Returns:
            ``True`` on success; ``False`` when no scale is configured.

        Raises:
            RuntimeError: When validation fails.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")

        if not self.scale:
            return False

        result = self.state_machine.validated_move_to_scale()

        if not result.valid:
            raise RuntimeError(f"Move to scale failed: {result.reason}")

        return True

    def set_dispenser_pistons(self, index: int, num_pistons: int) -> bool:
        """Set the piston count for one dispenser while connected.

        Args:
            index: Zero-based dispenser index.
            num_pistons: Replacement count (must be >= 0).

        Returns:
            ``True`` on success; ``False`` when the state machine is missing or
            the index is out of range.
        """
        if not self.state_machine:
            return False
        return self.state_machine.set_dispenser_pistons(index, num_pistons)

    def reset_job_mold_metadata(self) -> None:
        """Clear transient mold metadata after a dispensing job completes."""
        if self.state_machine is None:
            return
        self.state_machine.reset_mold_metadata()

    def abort(self) -> None:
        """Send firmware emergency stop (M112) to the Duet controller.

        Intentionally bypasses the state machine. After M112 the controller
        requires a manual reset before motion resumes, so tracked FSM state is
        no longer reliable.

        Note:
            Best-effort only. Silently ignored when no machine connection exists.
        """
        machine = self.machine_read_only
        if machine is not None:
            try:
                # Bypass MotionPlatformStateMachine intentionally.  See docstring.
                machine.gcode("M112")
            except Exception as e:
                print(f"[abort] M112 command failed: {e}")
                traceback.print_exc()
        self.connected = False

    def fill_powder(self, target_weight: float) -> bool:
        """Fill the mold on the scale to ``target_weight`` via the trickler.

        Args:
            target_weight: Target powder mass in grams.

        Returns:
            ``True`` on success; ``False`` when no scale is configured.

        Raises:
            RuntimeError: When validation fails.

        Warning:
            The mold must already be on the scale. Dispensing without a mold
            deposits powder directly on the load cell.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")

        if not self.scale:
            return False

        # Keep the executor's callback in sync with whatever the hardware
        # manager registered via set_jam_callback().
        if self.state_machine._executor is not None:
            self.state_machine._executor._on_jam_detected = self._on_jam_callback

        result = self.state_machine.validated_fill_powder(target_weight=target_weight)

        if not result.valid:
            raise RuntimeError(f"Fill mold with powder failed: {result.reason}")

        self.last_dispense_weight = self.state_machine.last_fill_weight
        return True
