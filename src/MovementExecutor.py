"""Low-level movement execution for validated state machine moves.

:class:`MovementExecutor` contains the physical G-code and hardware sequences for
the Jubilee motion platform. All ``execute_*`` methods assume validation has
already occurred in
:class:`~src.MotionPlatformStateMachine.MotionPlatformStateMachine`.

Warning:
    Do not instantiate or call this class from application code. Use
    ``validated_*`` methods on
    :class:`~src.MotionPlatformStateMachine.MotionPlatformStateMachine` so
    transition rules and coordinate checks stay enforced.

See Also:
    :doc:`motion-platform API reference </api/motion-platform>` for the public
    validated interface.
"""

import logging
import threading
import time

from typing import Callable
from science_jubilee.Machine import Machine
from src.Scale import Scale
from src.HardnessTester import HardnessTester
from src.PistonDispenser import PistonDispenser
from src.MotionPlatformStateMachine import PositionType
from src.ConfigLoader import config as _system_config

logger = logging.getLogger(__name__)
SHORE_D_SAMPLE_X_OFFSET_MM = 0.5


class MovementExecutor:
    """Executes physical machine moves after state machine validation.

    Owned internally by :class:`~src.MotionPlatformStateMachine.MotionPlatformStateMachine`.
    Each ``execute_*`` method maps to one validated action or position transition.

    Warning:
        Calling executor methods directly bypasses FSM checks and can move the
        machine from an unsafe pose.

    Attributes:
        last_fill_weight: Final stable grams from the most recent successful fill.
        last_hardness_result: Parsed durometer reading from the last test, if any.
        last_hardness_error: OCR or hardware error string from the last test.
        last_hardness_image_path: Debug image path from the last test, if saved.
    """

    def __init__(
        self,
        machine: Machine,
        scale: Scale | None = None,
        on_jam_detected: Callable | None = None,
    ):
        """
        Initialize the movement executor with a machine reference.

        Args:
            machine: The Jubilee Machine instance to control
            scale: Optional Scale instance (reference to JubileeManager's scale)
            on_jam_detected: Optional callback invoked when a powder jam requires
                operator clearance (not called for the first auto-recovered jam
                in each fill iteration).
        """
        self._machine = machine
        self._scale = scale
        self._feedrate = int(_system_config.get_default_feedrate())
        self.last_fill_weight: float | None = None
        self.last_hardness_result: float | None = None
        self.last_hardness_error: str | None = None
        self.last_hardness_image_path: str | None = None
        self.last_hardness_cv_bypassed: bool = False

        # Jam handling: the dispensing loop blocks on this event when a jam is
        # detected; clear_jam() sets it to allow the loop to resume.
        self._jam_resume_event: threading.Event = threading.Event()
        self._jam_resume_event.set()  # not jammed initially
        self._on_jam_detected: Callable | None = on_jam_detected

    @property
    def machine(self) -> Machine:
        """Read-only Jubilee machine access for position and status queries.

        Warning:
            Do not issue moves through this property. Use state machine
            ``validated_*`` methods on the state machine instead.
        """
        return self._machine

    def _well_label_for_slot(self, well_id: str, deck) -> str:
        """Resolve a human-friendly well label for logs."""
        try:
            slot_index = int(well_id)
            if 0 <= slot_index <= 17 and str(slot_index) in deck.slots:
                slot = deck.slots[str(slot_index)]
                if slot.has_labware and hasattr(slot.labware, "wells"):
                    well = slot.labware.wells.get(well_id)
                    if well and hasattr(well, "name"):
                        return well.name
        except Exception:
            pass
        return well_id

    def _home_axis(self, axis: str, label: str) -> bool:
        """Home one axis using the standard home macro convention."""
        try:
            self._machine.gcode(f'M98 P"home{axis.lower()}.g"')
            logger.info("%s (%s) homing complete. Position reset to 0.0mm", label, axis)
            return True
        except Exception as e:
            logger.error("Error homing %s: %s", label.lower(), e)
            return False

    # ===== MANIPULATOR MOVEMENTS =====

    def execute_pick_mold(
        self,
        well_id: str,
        deck,
        tamper_axis: str,
        tamper_travel_pos: float = 30.0,
        safe_z: float = 195.0,
        ready_x: float = None,
        ready_y: float = None,
        ready_z: float = None,
        ready_v: float = None,
    ) -> bool:
        """
        Execute the physical movements to pick up a mold from a mold slot.

        Assumes the toolhead is above the chosen mold slot at safe_z height
        with tamper axis in travel position.

        Args:
            well_id: Mold slot identifier (numerical string "0" through "17")
            deck: The Deck object with mold configuration
            tamper_axis: Axis letter for tamper (default 'V')
            tamper_travel_pos: Travel position for tamper axis (default 30.0 mm)
            safe_z: Safe Z height (default 195.0 mm)
            ready_x: X coordinate of mold slot ready position (required)
            ready_y: Y coordinate of mold slot ready position (required)
            ready_z: Z coordinate of mold slot ready position (required)
            ready_v: V coordinate of mold slot ready position (required)

        Returns:
            True if successful, False otherwise.
        """
        try:
            logger.info("Picking up mold: %s", self._well_label_for_slot(well_id, deck))

            feedrate = self._feedrate
            self._machine.move_to(v=66, s=feedrate)
            self._machine.move_to(z=40, s=feedrate)
            self._machine.move(dy=23, s=feedrate)
            self._machine.move_to(v=30, s=feedrate)
            self._machine.move(dy=-23, s=feedrate)
            self._machine.move_to(z=95, s=feedrate)

            # Move back to ready position, if not already there
            self._machine.move_to(
                x=ready_x, y=ready_y, z=ready_z, v=ready_v, s=feedrate
            )
            return True
        except Exception as e:
            logger.error("Error picking up mold from mold slot %s: %s", well_id, e)
            return False

    def execute_place_mold(
        self,
        well_id: str,
        deck,
        ready_x: float,
        ready_y: float,
        ready_z: float,
        ready_v: float,
    ) -> bool:
        """
        Execute the physical movements to place a mold in a mold slot.

        Args:
            well_id: Mold slot identifier (numerical string "0" through "17")
            deck: The Deck object with mold configuration
            ready_x: X coordinate of mold slot ready position (required)
            ready_y: Y coordinate of mold slot ready position (required)
            ready_z: Z coordinate of mold slot ready position (required)
            ready_v: V coordinate of mold slot ready position (required)

        Returns:
            True if successful, False otherwise.
        """
        try:
            logger.info("Placing mold: %s", self._well_label_for_slot(well_id, deck))

            feedrate = self._feedrate
            self._machine.move_to(v=66, s=feedrate)
            self._machine.move(dy=23, s=feedrate)
            self._machine.move_to(z=40, s=feedrate)
            self._machine.move(dy=-23, s=feedrate)
            self._machine.move_to(v=30, s=feedrate)
            self._machine.move_to(z=95, s=feedrate)

            # Move back to ready position, if not already there
            self._machine.move_to(
                x=ready_x, y=ready_y, z=ready_z, v=ready_v, s=feedrate
            )
            return True
        except Exception as e:
            logger.error("Error placing mold in mold slot %s: %s", well_id, e)
            return False

    def execute_place_mold_on_scale(
        self,
        tamper_axis: str,
        ready_x: float = None,
        ready_y: float = None,
        ready_z: float = None,
        ready_v: float = None,
    ) -> bool:
        """
        Execute movements to place mold on scale.

        Assumes the gantry has been moved to the scale ready spot location in front of and
        above the scale.

        Args:
            tamper_axis: Axis letter for tamper (default 'V')
            ready_x: X coordinate of scale ready position (required)
            ready_y: Y coordinate of scale ready position (required)
            ready_z: Z coordinate of scale ready position (required)
            ready_v: V coordinate of scale ready position (required)

        Returns:
            True if successful, False otherwise.
        """
        # TODO: replace z=90 references with mold transfer height constant
        if self._scale is None:
            raise RuntimeError("Scale not configured in MovementExecutor")
        if self._machine is None:
            raise RuntimeError("Jubilee not configured in MovementExecutor")

        try:
            logger.info("Placing mold on scale...")
            feedrate = self._feedrate
            self._machine.move(
                dy=38, s=feedrate
            )  # Move from ready position towards scale
            self._machine.move_to(v=67, s=feedrate)  # Move mold to fit under trickler
            self._machine.gcode(
                "M208 Z32.5:155"
            )  # Move bed up so well fits under trickler, relax z-limit to do so
            self._machine.move_to(z=34.5, s=feedrate)
            self._machine.move(dy=7, s=feedrate)
            # TODO: open chute
            self._machine.move_to(z=32.5, s=feedrate)
            self._machine.move(dy=19, s=feedrate)
            self._machine.gcode(
                "M208 Z27:155"
            )  # Move bed up so well is resting on scale, relax z-limit to do so
            self._machine.move_to(z=27, s=feedrate)  # Place mold on scale

            # Post-place retreat: move away from scale and mold.
            self._machine.move(
                dy=-19, s=feedrate
            )  # Back off mold so tool isn't touching
            # This sequence is intentionally undone in execute_pick_mold_from_scale.
            self._machine.move_to(z=34.5, s=feedrate)
            self._machine.move(dy=-7, s=feedrate)
            return True
        except Exception as e:
            logger.error("Error placing mold on scale: %s", e)
            return False

    def execute_pick_mold_from_scale(
        self,
        tamper_axis: str,
        ready_x: float = None,
        ready_y: float = None,
        ready_z: float = None,
        ready_v: float = None,
    ) -> bool:
        """
        Execute movements to pick mold from scale.

        Only call if a mold has been placed under the trickler.

        Args:
            tamper_axis: Axis letter for tamper (default 'V')
            ready_x: X coordinate of scale ready position (required)
            ready_y: Y coordinate of scale ready position (required)
            ready_z: Z coordinate of scale ready position (required)
            ready_v: V coordinate of scale ready position (required)

        Returns:
            True if successful, False otherwise.
        """
        if self._scale is None:
            raise RuntimeError("Scale not configured in MovementExecutor")
        if self._machine is None:
            raise RuntimeError("Jubilee not configured in MovementExecutor")

        try:
            logger.info("Picking mold from scale...")
            feedrate = self._feedrate
            # Phase 1: undo the post-place retreat exactly in reverse order.
            self._machine.move(dy=7, s=feedrate)
            self._machine.move_to(z=27, s=feedrate)
            self._machine.move(dy=19, s=feedrate)

            # Phase 2: execute the existing pickup and retreat sequence.
            self._machine.move(dy=1, s=feedrate)  # Return to model position
            self._machine.move_to(z=32.5, s=feedrate)  # Pick up mold off scale
            self._machine.gcode("M208 Z34.5:155")  # Revert z-limit to protect tool
            self._machine.move(dy=-19, s=feedrate)  # Move mold from under trickler
            self._machine.move_to(z=34.5, s=feedrate)  # Move within z-limits
            self._machine.move(
                dy=-7, s=feedrate
            )  # Move all the way back from under trickler
            self._machine.move_to(z=ready_z, s=feedrate)  # Move mold out from trickler
            self._machine.move_to(v=30, s=feedrate)  # Move tool to travel position
            self._machine.move(
                dy=-39, s=feedrate
            )  # Restore y position to position before mold was placed
            return True
        except Exception as e:
            logger.error("Error picking mold from scale: %s", e)
            return False

    def execute_place_top_piston(
        self,
        piston_dispenser: PistonDispenser,
        tamper_axis: str,
        ready_x: float = None,
        ready_y: float = None,
        ready_z: float = None,
        ready_v: float = None,
    ) -> bool:
        """Execute movements to place a top piston on the carried mold.

        Args:
            piston_dispenser: :class:`~src.PistonDispenser.PistonDispenser` index
                and inventory metadata.
            tamper_axis: Tamper axis letter (for example ``"V"``).
            ready_x: Resolved dispenser ready X coordinate (mm).
            ready_y: Resolved dispenser ready Y coordinate (mm).
            ready_z: Resolved dispenser ready Z coordinate (mm).
            ready_v: Resolved dispenser ready V coordinate (mm).

        Returns:
            ``True`` if successful, ``False`` on hardware error.

        Warning:
            Currently uses absolute Y coordinates and is validated for a single
            dispenser layout. Confirm machine config before multi-dispenser use.
        """
        try:
            logger.info("Placing top piston from dispenser %s", piston_dispenser.index)

            feedrate = self._feedrate
            self._machine.move_to(
                y=175.7, s=feedrate
            )  # Move into dispenser to dispense piston
            self._machine.gcode("M400")  # Wait for previous command to finish
            self._machine.gcode("G4 S2")  # Wait for 2 seconds
            self._machine.move_to(v=21, s=feedrate)  # Move tool up to pickup piston
            self._machine.move_to(y=140, s=feedrate)  # Move away from dispenser
            self._machine.move_to(
                v=8, s=feedrate
            )  # Push piston into mold
            self._machine.move_to(
                x=ready_x, y=ready_y, z=ready_z, v=ready_v, s=feedrate
            )

            return True
        except Exception as e:
            logger.error(
                "Error placing top piston from dispenser %s: %s",
                piston_dispenser.index,
                e,
            )
            return False

    def execute_tamp(
        self, tamper_axis: str, tamp_depth: float, tamp_speed: int
    ) -> bool:
        """
        Execute tamping movements at the scale_ready position.

        Tamping compresses powder in a mold held by the manipulator to:
        1. Reduce powder volume so the top piston can fit
        2. Minimize airborne powder when inserting the top piston

        After tamping, the V axis is homed to ensure axis accuracy.

        Args:
            tamper_axis: Axis letter for tamper (default 'V')
            tamp_depth: How deep to tamp within mold (mm)
            tamp_speed: Speed for tamper movement in mm/min

        Returns:
            True if successful, False otherwise.

        Note:
            Parameter bounds are validated by the state machine before this method is called.
            Valid ranges are configured in system_config.json (manipulator.tamp_depth_min/max,
            manipulator.tamp_speed_min/max).
        """
        try:
            logger.info("Executing tamp at scale_ready position...")

            feedrate = tamp_speed

            # Save current v value to return to after tamping
            current_position = self._machine.get_position()
            saved_v = float(current_position.get("V"))

            # Move tamper until it is just outside mold
            self._machine.move_to(v=2, s=feedrate)

            # Move by requested tamp depth
            self._machine.move(dv=tamp_depth, s=feedrate)
            self._machine.gcode("M400")

            # Return tamper to safe position
            self._machine.move_to(
                v=_system_config.get_tamper_travel_position(),
                s=feedrate,
            )

            # Home V axis after tamping to ensure axis accuracy
            logger.info("Homing V axis after tamp to ensure accuracy...")
            self.execute_home_tamper(tamper_axis)
            self._machine.move_to(v=saved_v, s=feedrate)

            logger.info("Tamping complete")
            return True
        except Exception as e:
            logger.error("Error during tamp: %s", e)
            return False

    # ===== BASIC MOVEMENTS =====

    def execute_move_to_position(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        v: float | None = None,
        speed: int | None = None,
    ) -> bool:
        """
        Execute a basic move to specified coordinates.

        Args:
            x: X coordinate (None to skip)
            y: Y coordinate (None to skip)
            z: Z coordinate (None to skip)
            v: V/manipulator coordinate (None to skip)
            speed: Movement speed in mm/min (None to use configured feedrate)

        Returns:
            True if successful, False otherwise.
        """
        try:
            if speed is None:
                speed = self._feedrate
            self._machine.move_to(x=x, y=y, z=z, v=v, s=speed)
            return True
        except Exception as e:
            logger.error("Error executing basic move: %s", e)
            return False

    def execute_move_to_sample_tray(self, x: float, y: float, z: float) -> bool:
        """
        Move the hardness tester to a sample tray ready coordinate.

        The state machine resolves tray coordinates and validates tool/position
        requirements before this executor is called.

        Args:
            x: Resolved X machine coordinate.
            y: Resolved Y machine coordinate.
            z: Resolved Z machine coordinate.

        Returns:
            True if successful, False otherwise.
        """
        try:
            feedrate = self._feedrate
            logger.info("Moving hardness tester to sample tray: x=%s, y=%s, z=%s", x, y, z)
            self._machine.move_to(x=x, y=y, z=z, s=feedrate)
            return True
        except Exception as e:
            logger.error("Error moving to hardness sample tray: %s", e)
            return False

    def execute_move_to_hardness_sample(
        self,
        x: float,
        y: float,
        z: float,
        mode: str | None = None,
    ) -> bool:
        """
        Move the hardness tester to a specific sample slot position.

        The state machine resolves the per-slot coordinates and validates
        the slot before this executor is called.

        Args:
            x: Resolved X machine coordinate.
            y: Resolved Y machine coordinate.
            z: Resolved Z machine coordinate.
            mode: Optional Shore mode string (``"shore_a"`` or ``"shore_d"``).

        Returns:
            True if successful, False otherwise.
        """
        try:
            feedrate = self._feedrate
            resolved_x = x
            normalized_mode = (mode or "").strip().lower()
            if normalized_mode == "shore_d":
                resolved_x = x + SHORE_D_SAMPLE_X_OFFSET_MM
            self._machine.move_to(x=resolved_x, y=y, z=z, s=feedrate)
            return True
        except Exception as e:
            logger.error("Error moving to hardness sample: %s", e)
            return False

    def execute_test_sample(
        self,
        tray_index: int,
        sample_id: str,
        mode: str | None = None,
        hardness_tester: HardnessTester = None,
        image_save_path=None,
    ) -> bool:
        """
        Execute the hardness measurement at the current sample slot position.

        Pre-conditions (validated by the state machine before this is called):
          - Machine is already positioned at the target sample slot via
            ``execute_move_to_hardness_sample``.

        Sequence:
          1. TODO: Issue the z-probe descent (e.g. G38.2 / vendor probe
             routine) and capture the contact Z. This is a no-op placeholder
             until probing hardware is wired up.
          2. Drive the durometer down for contact pressure and read the LCD
             via the HardnessTester.

        Args:
            tray_index: Zero-based tray index for logging and debug artifacts.
            sample_id: Sample identifier within the tray.
            mode: Optional Shore mode string (``"shore_a"`` or ``"shore_d"``).
            hardness_tester: ``HardnessTester`` instance used for LCD capture.
            image_save_path: Optional path to persist a debug camera frame.

        Returns:
            True when the executor finishes (including OCR stub paths). OCR
            failures are recorded on ``last_hardness_error`` rather than
            returning False.

        Note:
            Results are stored on ``last_hardness_result``,
            ``last_hardness_error``, and ``last_hardness_image_path``.
        """
        self.last_hardness_result = None
        self.last_hardness_error = None
        self.last_hardness_image_path = None
        self.last_hardness_cv_bypassed = False

        # TODO: Issue the actual z-probe descent (e.g. G38.2 / vendor
        # probe routine) and capture the contact Z.
        probed_top_z = None  # Replace with real probe result.

        logger.debug(
            "Hardness sample motion stub (tray=%s, sample=%s, mode=%s, probed_top_z=%s)",
            tray_index,
            sample_id,
            mode,
            probed_top_z,
        )
        if hardness_tester is None:
            self.last_hardness_error = (
                "Hardness tester instance was not provided for OCR."
            )
            return True

        if getattr(hardness_tester, "bypass_cv", False):
            self.last_hardness_cv_bypassed = True
            return True

        if getattr(hardness_tester, "enable_monotonic_drop_check", False):
            numeric_samples = hardness_tester.sample_numeric_readings(
                frame_count=8,
                total_duration_s=0.8,
                debug_prefix=f"hardness_probe_{tray_index}_{sample_id}",
            )
            threshold = getattr(hardness_tester, "monotonic_drop_threshold", 0.0)
            previous_value: float | None = None
            for value in numeric_samples:
                if previous_value is not None:
                    drop_amount = previous_value - value
                    if drop_amount >= float(threshold):
                        self.last_hardness_error = (
                            "Hardness reading dropped sharply during probe descent "
                            f"(drop={drop_amount:.2f}, threshold={float(threshold):.2f}); "
                            "sample may have broken."
                        )
                        return True
                previous_value = value

        reading = hardness_tester.read_display(
            debug=False,
            debug_prefix=f"hardness_{tray_index}_{sample_id}",
            image_save_path=image_save_path,
        )
        measured_value, sample_error = hardness_tester._parse_hardness_reading(reading)
        self.last_hardness_result = measured_value
        self.last_hardness_error = sample_error
        if image_save_path is not None:
            from pathlib import Path as _Path

            p = _Path(image_save_path)
            self.last_hardness_image_path = (
                str(image_save_path) if p.is_file() else None
            )
        return True

    def execute_hardness_turn_on(
        self,
        mode: str | None = None,
        servo_channel: int = None,
        press_angle: int = None,
        release_angle: int = None,
    ) -> bool:
        """
        Press and release the power button on the specified Shore tester.

        Args:
            mode: Tester mode string (for logging only).
            servo_channel: Duet servo channel number.
            press_angle: Servo angle in degrees to press the button.
            release_angle: Servo angle in degrees to release the button.

        Returns:
            True if successful, False otherwise.
        """
        return self._actuate_servo(
            mode, servo_channel, press_angle, release_angle, "turn_on"
        )

    def execute_hardness_turn_off(
        self,
        mode: str | None = None,
        servo_channel: int = None,
        press_angle: int = None,
        release_angle: int = None,
    ) -> bool:
        """
        Press and release the power button on the specified Shore tester to turn off.

        Args:
            mode: Tester mode string (for logging only).
            servo_channel: Duet servo channel number.
            press_angle: Servo angle in degrees to press the button.
            release_angle: Servo angle in degrees to release the button.

        Returns:
            True if successful, False otherwise.
        """
        return self._actuate_servo(
            mode, servo_channel, press_angle, release_angle, "turn_off"
        )

    def execute_hardness_zero(
        self,
        mode: str | None = None,
        servo_channel: int = None,
        press_angle: int = None,
        release_angle: int = None,
    ) -> bool:
        """
        Press and release the zero button on the specified Shore tester.

        Args:
            mode: Tester mode string (for logging only).
            servo_channel: Duet servo channel number.
            press_angle: Servo angle in degrees to press the button.
            release_angle: Servo angle in degrees to release the button.

        Returns:
            True if successful, False otherwise.
        """
        return self._actuate_servo(
            mode, servo_channel, press_angle, release_angle, "zero"
        )

    def _actuate_servo(
        self,
        mode: str | None,
        servo_channel: int | None,
        press_angle: int | None,
        release_angle: int | None,
        action: str,
    ) -> bool:
        """Send M280 press/release gcode for a single servo button actuation.

        Args:
            mode: Tester mode string (for logging only).
            servo_channel: Duet servo channel number (integer).
            press_angle: Servo angle in degrees to press the button (0-180).
            release_angle: Servo angle in degrees to release the button (0-180).
            action: Action label for log messages.
        """
        if servo_channel is None or press_angle is None or release_angle is None:
            logger.warning(
                "_actuate_servo called with missing parameters "
                "(mode=%s, channel=%s, press=%s, release=%s, action=%s)",
                mode,
                servo_channel,
                press_angle,
                release_angle,
                action,
            )
            return False
        try:
            self._machine.gcode(f"M280 P{servo_channel} S{press_angle}")
            self._machine.gcode("G4 P500")
            self._machine.gcode(f"M280 P{servo_channel} S{release_angle}")
            self._machine.gcode("M400")
            return True
        except Exception as e:
            logger.error("Error actuating servo (mode=%s, action=%s): %s", mode, action, e)
            return False

    def _extract_powder_dispenser_cover_servo_config(
        self,
    ) -> tuple[int | None, int | None, int | None, str | None]:
        """Read and validate powder dispenser cover servo settings from config."""
        servo_id = _system_config.get_powder_dispenser_cover_servo()
        open_angle = _system_config.get_powder_dispenser_cover_open_angle()
        closed_angle = _system_config.get_powder_dispenser_cover_closed_angle()

        for label, angle in (("open", open_angle), ("closed", closed_angle)):
            if not (0 <= int(angle) <= 90):
                return (
                    None,
                    None,
                    None,
                    f"powder_dispenser_cover.{label}_angle {angle} is out of range [0, ]",
                )

        s = str(servo_id).strip()
        try:
            channel = int(s[1:]) if s.upper().startswith("S") else int(s)
        except ValueError:
            return (
                None,
                None,
                None,
                f"Cannot parse powder_dispenser_cover.servo identifier '{servo_id}'",
            )

        return channel, int(open_angle), int(closed_angle), None

    def execute_home_all(self, registry) -> bool:
        """Home all axes and return to global_ready position.

        Returns:
            True if successful, False otherwise.
        """
        try:
            self._machine.home_all()
            global_ready_pos = registry.find_first_of_type(PositionType.GLOBAL_READY)
            if global_ready_pos and global_ready_pos.coordinates:
                coords = global_ready_pos.coordinates
                z_height = None
                if coords.z == "USE_Z_HEIGHT_POLICY":
                    z_heights = registry.z_heights
                    if "mold_transfer_safe" in z_heights:
                        z_config = z_heights["mold_transfer_safe"]
                        if isinstance(z_config, dict):
                            z_height = z_config.get("z_coordinate")

                def _to_float(value):
                    if value is None or isinstance(value, str):
                        return None
                    return float(value)

                x = _to_float(coords.x)
                y = _to_float(coords.y)
                z = _to_float(z_height)
                v = (
                    coords.v
                    if (
                        coords.v is not None
                        and (
                            not isinstance(coords.v, str)
                            or not coords.v.startswith("PLACEHOLDER")
                        )
                    )
                    else None
                )

                if x is not None or y is not None or z is not None or v is not None:
                    self._machine.move_to(x=x, y=y, z=z, v=v, s=self._feedrate)
            return True
        except Exception as e:
            logger.error("Error homing all axes: %s", e)
            return False

    def execute_pickup_tool(
        self,
        tool,
        global_ready_x: float,
        global_ready_y: float,
        global_ready_z: float,
        global_ready_v: float | None = None,
    ) -> bool:
        """
        Pick up a tool and re-center on global_ready.

        The state machine enforces that pickup is only valid from global_ready
        with the manipulator (zero) offset active, and resolves the
        offset-adjusted global_ready coordinates before calling this method.
        After the firmware tpost macro completes, this method drives the
        machine back to those coordinates so the pose is well-defined when
        the state machine swaps in the new tool's default offset.

        Note: The machine's pickup_tool() method is decorated with @requires_safe_z,
        which automatically raises the bed height to deck.safe_z + 20 if it is not
        already at that height.

        Args:
            tool: The Tool object to pick up
            global_ready_x: Resolved global_ready X coordinate (manipulator offset)
            global_ready_y: Resolved global_ready Y coordinate (manipulator offset)
            global_ready_z: Resolved global_ready Z coordinate (manipulator offset)
            global_ready_v: Resolved global_ready V coordinate (None to skip)

        Returns:
            True if successful, False otherwise
        """
        try:
            self._machine.pickup_tool(tool)
            self._machine.move_to(
                x=global_ready_x,
                y=global_ready_y,
                z=global_ready_z,
                v=global_ready_v,
                s=self._feedrate,
            )
            return True
        except Exception as e:
            logger.error("Error picking up tool: %s", e)
            return False

    def execute_park_tool(
        self,
        global_ready_x: float,
        global_ready_y: float,
        global_ready_z: float,
        global_ready_v: float | None = None,
    ) -> bool:
        """
        Park the current tool and re-center on global_ready.

        The state machine enforces that park is only valid from global_ready
        and restores the manipulator (zero) offset before calling this
        method, so the supplied coordinates are already in the correct frame.

        Note: The machine's park_tool() method is decorated with @requires_safe_z,
        which automatically raises the bed height to deck.safe_z + 20 if it is not
        already at that height.

        Args:
            global_ready_x: Resolved global_ready X coordinate (manipulator offset)
            global_ready_y: Resolved global_ready Y coordinate (manipulator offset)
            global_ready_z: Resolved global_ready Z coordinate (manipulator offset)
            global_ready_v: Resolved global_ready V coordinate (None to skip)

        Returns:
            True if successful, False otherwise
        """
        try:
            self._machine.park_tool()
            self._machine.move_to(
                x=global_ready_x,
                y=global_ready_y,
                z=global_ready_z,
                v=global_ready_v,
                s=self._feedrate,
            )
            return True
        except Exception as e:
            logger.error("Error parking tool: %s", e)
            return False

    def execute_home_xyz(self) -> bool:
        """Home X, Y, Z axes.

        Returns:
            True if successful, False otherwise.
        """
        try:
            self._machine.home_xyu()
            self._machine.home_z()
            return True
        except Exception as e:
            logger.error("Error homing XYZ axes: %s", e)
            return False

    def execute_move_to_mold_slot(
        self,
        x: float,
        y: float,
        z: float,
        v: float | None = None,
    ) -> bool:
        """
        Move to a specific mold slot position.

        All coordinates must be fully resolved from the state machine's
        position and z-height policy logic before calling this executor.

        Args:
            x: Final X machine coordinate
            y: Final Y machine coordinate
            z: Final Z machine coordinate
            v: V coordinate (None to skip)

        Returns:
            True if successful, False otherwise
        """
        try:
            feedrate = self._feedrate
            self._machine.move_to(x=x, y=y, z=z, v=v, s=feedrate)
            return True
        except Exception as e:
            logger.error("Error moving to well: %s", e)
            logger.error("Coordinate: x=%s, y=%s, z=%s, v=%s", x, y, z, v)
            return False

    def execute_move_to_scale(
        self, ready_x: float, ready_y: float, ready_z: float, ready_v: float
    ) -> bool:
        """
        Execute movement to the scale ready location.

        Args:
            ready_x: X coordinate of scale ready position (required)
            ready_y: Y coordinate of scale ready position (required)
            ready_z: Z coordinate of scale ready position (required)
            ready_v: V coordinate of scale ready position (required)

        Note:
            Z-height safety is enforced by state machine's z_height_policy validation.
            SCALE_READY position requires z_height_policy (typically mold_transfer_safe)

        Returns:
            True if successful, False otherwise.
        """
        try:
            feedrate = self._feedrate
            self._machine.move_to(
                x=ready_x, y=ready_y, z=ready_z, v=ready_v, s=feedrate
            )
            return True
        except Exception as e:
            logger.error("Error moving to scale ready position: %s", e)
            return False

    def get_machine_position(self) -> dict:
        """
        Get current machine position from the Duet controller.

        Returns:
            Position mapping with axis keys (for example ``X``, ``Y``, ``Z``, ``V``).

        Raises:
            RuntimeError: If the Duet does not respond or returns an unusable
                response (science_jubilee returns None on HTTP failure, which
                surfaces as TypeError or AttributeError inside get_position).
        """
        _DUET_COMM_ERRORS = (
            TypeError,
            AttributeError,
            ConnectionError,
            TimeoutError,
            OSError,
        )
        try:
            pos = self._machine.get_position()
        except _DUET_COMM_ERRORS as exc:
            raise RuntimeError(
                f"Failed to read machine position (Duet not responding): {exc!r}"
            ) from exc
        if pos is None:
            raise RuntimeError(
                "Failed to read machine position: get_position() returned None"
            )
        return pos

    def get_machine_axes_homed(self) -> list:
        """
        Get homing status for each machine axis.

        Returns:
            Boolean list indexed by axis (typically X, Y, Z, U, V).
        """
        return getattr(self._machine, "axes_homed", [False, False, False, False])

    def wait_for_moves_to_finish(self) -> None:
        """
        Wait for all buffered moves to complete execution.

        Executes the M400 G-code command, which blocks until all previously
        buffered moves in the machine's internal buffer have been executed.
        This ensures the Python program does not advance past the physical
        state of the Jubilee.
        """
        self._machine.gcode("M400")

    def execute_move_to_scale_location(
        self, ready_x: float, ready_y: float, ready_z: float, ready_v: float
    ) -> bool:
        """Move to the scale ready location.

        Args:
            ready_x: Resolved scale ready X coordinate (mm).
            ready_y: Resolved scale ready Y coordinate (mm).
            ready_z: Resolved scale ready Z coordinate (mm).
            ready_v: Resolved scale ready V coordinate (mm).

        Returns:
            ``True`` if successful, ``False`` on hardware error.

        Note:
            Z-height policy is enforced by the state machine before this runs
            (``scale_ready`` typically requires ``mold_transfer_safe``).
        """
        try:
            feedrate = self._feedrate
            self._machine.move_to(
                x=ready_x, y=ready_y, z=ready_z, v=ready_v, s=feedrate
            )
            return True
        except Exception as e:
            logger.error("Error moving to scale: %s", e)
            return False

    # ===== JAM DETECTION HELPERS =====

    @property
    def jam_detected(self) -> bool:
        """True while the dispensing loop is blocked waiting for jam clearance."""
        return not self._jam_resume_event.is_set()

    def clear_jam(self) -> None:
        """Resume dispensing after a jam has been physically cleared by the operator."""
        self._jam_resume_event.set()

    def _set_trickler_vibration(self, amplitude: float) -> None:
        """Set trickler vibration servo amplitude (M42 P0). Amplitude 0 turns it off."""
        self._machine.gcode(f"M42 P0 S{amplitude:.2f} F20000")

    def _auto_recover_jam(self, vibration_amplitude: float, wait_seconds: float) -> None:
        """First jam in a fill iteration: bump vibration and wait before retrying."""
        logger.warning(
            "[Jam] Powder jam detected - auto-recovery: vibration %.2f for %.0fs",
            vibration_amplitude,
            wait_seconds,
        )
        try:
            self._set_trickler_vibration(vibration_amplitude)
            self._machine.gcode("M400")
        except Exception as e:
            logger.warning("[Jam] Could not set recovery vibration: %s", e)
        time.sleep(wait_seconds)
        self._set_trickler_vibration(0.0)
        logger.info("[Jam] Auto-recovery complete - resuming dispensing.")

    def _handle_jam(self) -> None:
        """Called when a jam requires operator clearance.

        Stops vibration, fires the on_jam_detected callback (which
        signals the UI), then blocks until clear_jam() is called by the
        operator-facing REST endpoint.
        """
        try:
            self._set_trickler_vibration(0.0)
            self._machine.gcode("M400")
        except Exception as e:
            logger.warning("[Jam] Could not stop vibration: %s", e)

        self._jam_resume_event.clear()
        logger.warning("[Jam] Powder jam detected - waiting for operator clearance.")

        if self._on_jam_detected is not None:
            try:
                self._on_jam_detected()
            except Exception as e:
                logger.warning("[Jam] on_jam_detected callback raised: %s", e)

        self._jam_resume_event.wait()
        logger.info("[Jam] Jam cleared by operator - resuming dispensing.")

    def _recover_from_jam_stall(
        self,
        *,
        jam_auto_recovered: bool,
        recovery_vib_amp: float,
        recovery_wait_seconds: float,
    ) -> bool:
        """Handle a detected jam stall. Returns updated jam_auto_recovered flag."""
        if not jam_auto_recovered:
            self._auto_recover_jam(recovery_vib_amp, recovery_wait_seconds)
            return True
        self._handle_jam()
        return True

    # ===== POWDER FILL =====

    def execute_fill_powder(self, target_weight: float) -> bool:
        """Fill the mold on the scale using the trickler.

        Uses stable weight reads in the fine phase and unstable reads in the
        coarse phase. Per-step EMAs (flow and yield, g/mm) drive adaptive step
        sizing and jam detection. The first jam in each fill attempt auto-recovers
        via increased vibration; later jams block until
        :meth:`clear_jam` is called.

        Args:
            target_weight: Target powder mass in grams.

        Returns:
            ``True`` when the finish threshold is reached; ``False`` on error.

        Note:
            Trickler tuning parameters load from ``system_config.json``
            (``trickler`` section). Final weight is stored on
            :attr:`last_fill_weight`.
        """
        trickler = _system_config.get_active_trickler_profile()

        flow_alpha = trickler.flow_ema_alpha
        yield_alpha = trickler.yield_ema_alpha
        jam_threshold = trickler.jam_yield_threshold
        jam_iter_limit = trickler.jam_iter_threshold
        jam_recovery_vib_amp = trickler.jam_auto_recovery_vibration_amplitude
        jam_recovery_wait_seconds = trickler.jam_auto_recovery_wait_seconds
        max_step = trickler.max_step_size_mm
        min_step = trickler.min_step_size_mm
        warmup_steps = trickler.warmup_steps
        warmup_max_step = trickler.warmup_max_step_mm
        coarse_pct = trickler.coarse_threshold_pct
        finish_pct = trickler.finish_threshold_pct
        coarse_tgt_steps = trickler.coarse_target_steps
        coarse_feedrate = trickler.coarse_feedrate
        fine_feedrate = trickler.fine_feedrate
        coarse_vib_amp = trickler.coarse_vibration_amplitude
        fine_vib_amp = trickler.fine_vibration_amplitude
        max_dribble_step = trickler.max_dribble_step_mm

        coarse_feedrate_str = f"F{coarse_feedrate}"
        fine_feedrate_str = f"F{fine_feedrate}"
        coarse_threshold = coarse_pct * target_weight
        finish_threshold = finish_pct * target_weight

        try:
            self._machine.gcode("M400")  # ensure prior moves are complete
            if not self.execute_open_powder_dispenser_cover():
                raise RuntimeError("Failed to open powder dispenser cover servo")

            self._scale.tare()
            initial_weight = self._scale.get_weight(stable=True)
            logger.info("[Fill] Initial weight after tare: %.4fg", initial_weight)
            logger.info(
                "[Fill] Target: %.4fg coarse: %.4fg finish: %.4fg",
                target_weight,
                coarse_threshold,
                finish_threshold,
            )

            self._machine.gcode("G92 W0")  # reset trickler axis
            self._machine.gcode("G91")  # relative positioning

            current_vib_amp = coarse_vib_amp
            self._set_trickler_vibration(current_vib_amp)

            flow_ema = 0.0
            yield_ema = 0.0
            step_count = 0
            stagnant_count = 0
            motor_has_moved = False
            threshold_crossed = False
            jam_auto_recovered = False

            while True:
                if threshold_crossed:
                    time.sleep(0.15)
                    current_weight = self._scale.get_weight(stable=True)
                    logger.debug("[FillTrace] stable sample: weight=%.4f", current_weight)
                else:
                    current_weight = self._scale.get_weight(stable=False)
                    logger.debug("[FillTrace] unstable sample: weight=%.4f", current_weight)

                if current_weight >= coarse_threshold:
                    if not threshold_crossed:
                        threshold_crossed = True
                        current_vib_amp = fine_vib_amp
                        logger.info(
                            "[Fill] Coarse threshold crossed at %.4fg", current_weight
                        )
                        self._set_trickler_vibration(current_vib_amp)
                        time.sleep(0.15)
                        current_weight = self._scale.get_weight(stable=True)
                        logger.debug(
                            "[FillTrace] stable sample after coarse crossing: weight=%.4f",
                            current_weight,
                        )

                    remaining = max(0.0, finish_threshold - current_weight)
                    if yield_ema > 0 and remaining > 0:
                        step_size = remaining / yield_ema
                    else:
                        step_size = min_step
                    step_size = max(min_step, min(max_dribble_step, step_size))

                    weight_before_step = current_weight
                    # High-speed "flick" at fine_feedrate; vibration already running.
                    self._machine.gcode(f"G1 W{step_size:.4f} {fine_feedrate_str}")
                    self._machine.gcode("M400")
                    motor_has_moved = True

                    weight_after_step = self._scale.get_weight(stable=True)
                    logger.debug(
                        "[FillTrace] stable sample after fine step: weight=%.4f",
                        weight_after_step,
                    )
                    weight_gained = max(0.0, weight_after_step - weight_before_step)
                    step_yield = weight_gained / step_size

                    flow_ema = flow_alpha * step_yield + (1 - flow_alpha) * flow_ema
                    yield_ema = yield_alpha * step_yield + (1 - yield_alpha) * yield_ema
                    step_count += 1

                    if flow_ema < jam_threshold:
                        stagnant_count += 1
                    else:
                        stagnant_count = 0
                    if stagnant_count >= jam_iter_limit:
                        jam_auto_recovered = self._recover_from_jam_stall(
                            jam_auto_recovered=jam_auto_recovered,
                            recovery_vib_amp=jam_recovery_vib_amp,
                            recovery_wait_seconds=jam_recovery_wait_seconds,
                        )
                        stagnant_count = 0
                        flow_ema = 0.0
                        yield_ema = 0.0
                        self._set_trickler_vibration(current_vib_amp)
                        continue

                    current_weight = weight_after_step

                    if current_weight >= finish_threshold:
                        self._set_trickler_vibration(0.0)
                        time.sleep(4)
                        final_weight = self._scale.get_weight(stable=True)
                        logger.info("[Fill] Stable confirmation: %.4fg", final_weight)
                        if final_weight >= finish_threshold:
                            logger.info("[Fill] Target reached: %.4fg", final_weight)
                            self.last_fill_weight = final_weight
                            break
                        logger.info(
                            "[Fill] Stable weight %.4fg below threshold, continuing...",
                            final_weight,
                        )
                        self._set_trickler_vibration(current_vib_amp)

                else:
                    if step_count < warmup_steps or yield_ema == 0.0:
                        progress = max(0.0, current_weight / coarse_threshold)
                        step_size = max_step - (max_step - min_step) * progress
                        step_size = min(
                            step_size,
                            warmup_max_step if step_count < warmup_steps else max_step,
                        )
                    else:
                        target_remaining = coarse_threshold - current_weight
                        step_size = target_remaining / (yield_ema * coarse_tgt_steps)
                        step_size = max(min_step, min(max_step, step_size))

                    weight_before_step = current_weight
                    self._machine.gcode(f"G1 W{step_size:.4f} {coarse_feedrate_str}")
                    self._machine.gcode("M400")
                    motor_has_moved = True

                    weight_after_step = self._scale.get_weight(stable=False)
                    weight_gained = max(0.0, weight_after_step - weight_before_step)
                    step_yield = weight_gained / step_size

                    flow_ema = flow_alpha * step_yield + (1 - flow_alpha) * flow_ema
                    yield_ema = yield_alpha * step_yield + (1 - yield_alpha) * yield_ema
                    step_count += 1

                    if motor_has_moved and step_count > warmup_steps:
                        if flow_ema < jam_threshold:
                            stagnant_count += 1
                        else:
                            stagnant_count = 0
                        if stagnant_count >= jam_iter_limit:
                            jam_auto_recovered = self._recover_from_jam_stall(
                                jam_auto_recovered=jam_auto_recovered,
                                recovery_vib_amp=jam_recovery_vib_amp,
                                recovery_wait_seconds=jam_recovery_wait_seconds,
                            )
                            stagnant_count = 0
                            flow_ema = 0.0
                            yield_ema = 0.0
                            self._set_trickler_vibration(current_vib_amp)
                            continue

            return True

        except Exception as e:
            logger.error("[Fill] Error filling mold with powder: %s", e)
            return False
        finally:
            try:
                self._set_trickler_vibration(0.0)
                self._machine.gcode("G90")  # restore absolute positioning
            except Exception:
                pass
            if not self.execute_close_powder_dispenser_cover():
                logger.warning("Failed to close powder dispenser cover servo")

    def execute_open_powder_dispenser_cover(self) -> bool:
        """Open the powder dispenser cover using configured servo channel/angle."""
        channel, open_angle, _, error = (
            self._extract_powder_dispenser_cover_servo_config()
        )
        if error:
            logger.warning("Cannot open powder dispenser cover: %s", error)
            return False
        return self._actuate_servo(
            mode="powder_dispenser_cover",
            servo_channel=channel,
            press_angle=open_angle,
            release_angle=open_angle,
            action="open_cover",
        )

    def execute_close_powder_dispenser_cover(self) -> bool:
        """Close the powder dispenser cover using configured servo channel/angle."""
        channel, _, closed_angle, error = (
            self._extract_powder_dispenser_cover_servo_config()
        )
        if error:
            logger.warning("Cannot close powder dispenser cover: %s", error)
            return False
        return self._actuate_servo(
            mode="powder_dispenser_cover",
            servo_channel=channel,
            press_angle=closed_angle,
            release_angle=closed_angle,
            action="close_cover",
        )

    def execute_home_tamper(
        self,
        tamper_axis: str,
    ) -> bool:
        """Home the tamper (V) axis using the mold cavity as reference.

        Safe while holding a mold **without** a top piston:

        - Start: ``v=2`` (tamper inserted into mold)
        - End: ``v=-7`` (tamper at mold bottom)

        Args:
            tamper_axis: Tamper axis letter (for example ``"V"``).

        Returns:
            ``True`` when homing completes.

        Raises:
            RuntimeError: If X, Y, Z, or U are not homed before tamper homing.

        Warning:
            Do not run when the mold has a top piston inserted.
        """
        # Check if axes are homed
        axes_homed = getattr(self._machine, "axes_homed", [False, False, False, False])
        axis_names = ["X", "Y", "Z", "U"]
        not_homed = [axis_names[i] for i in range(4) if not axes_homed[i]]

        if not_homed:
            logger.error("Axes not homed: %s", ", ".join(not_homed))
            raise RuntimeError(
                f"X, Y, Z, and U axes must be homed before homing the tamper "
                f"({tamper_axis}) axis."
            )

        # Perform homing for tamper axis
        self._machine.gcode(f'M98 P"home{tamper_axis.lower()}.g"')

        logger.info("Homing complete. %s axis position reset to 0.0mm", tamper_axis)
        return True

    def execute_home_manipulator(self, manipulator_axis: str) -> bool:
        """
        Home the manipulator axis (V).

        Args:
            manipulator_axis: Axis letter for manipulator (default 'V')

        Returns:
            True if successful, False otherwise
        """
        return self._home_axis(manipulator_axis, "Manipulator")

    def execute_home_trickler(self, trickler_axis: str = "W") -> bool:
        """
        Home the trickler axis (W).

        Args:
            trickler_axis: Axis letter for trickler (default 'W')

        Returns:
            True if successful, False otherwise
        """
        return self._home_axis(trickler_axis, "Trickler")
