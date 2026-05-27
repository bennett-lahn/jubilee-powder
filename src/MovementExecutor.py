"""
MotionPlatformExecutor - Low-level movement execution for validated state machine moves.

This module contains all the physical movement execution logic for the Jubilee
motion platform. All methods assume validation has already occurred in the
MotionPlatformStateMachine. 

The executor is owned by the state machine and is not accessed directly by other
components, so all movements go through validation.
"""
import time

from typing import Optional
from science_jubilee.Machine import Machine
from src.Scale import Scale
from src.HardnessTester import HardnessTester
from src.PistonDispenser import PistonDispenser
from src.MotionPlatformStateMachine import PositionType
from jubilee_api_config.constants import FeedRate


class MovementExecutor:
    """
    Executes physical movements on the machine after state machine validation.
    
    This class should not be instantiated directly by user code. Instead, it is
    owned by MotionPlatformStateMachine and accessed through validated methods.
    """
    
    def __init__(self, machine: Machine, scale: Optional[Scale] = None, feedrate: FeedRate = FeedRate.MEDIUM):
        """
        Initialize the movement executor with a machine reference.
        
        Args:
            machine: The Jubilee Machine instance to control
            scale: Optional Scale instance (reference to JubileeManager's scale)
            feedrate: FeedRate enum value to control movement speed (default: MEDIUM)
        """
        self._machine = machine
        self._scale = scale
        self._feedrate = feedrate.value
        self.last_fill_weight: Optional[float] = None
        self.last_hardness_result: Optional[float] = None
        self.last_hardness_error: Optional[str] = None
    
    @property
    def machine(self) -> Machine:
        """
        Read-only access to machine for state queries only. 
        Queries should not modify platform state.
        """
        return self._machine
    
    # ===== MANIPULATOR MOVEMENTS =====
    
    def execute_pick_mold(
        self,
        well_id: str,
        deck,
        tamper_axis: str = 'V',
        tamper_travel_pos: float = 30.0,
        safe_z: float = 195.0,
        ready_x: float = None,
        ready_y: float = None,
        ready_z: float = None,
        ready_v: float = None
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
        # TODO: Update to use variable instead of constant for z=90 safe transfer height
        # Get mold from deck for logging
        well = None
        try:
            # Convert well_id to slot index (well_id is already numerical: "0", "1", ... "17")
            slot_index = int(well_id)
            
            if 0 <= slot_index <= 17 and str(slot_index) in deck.slots:
                slot = deck.slots[str(slot_index)]
                if slot.has_labware and hasattr(slot.labware, 'wells'):
                    if well_id in slot.labware.wells:
                        well = slot.labware.wells[well_id]
        except Exception:
            pass
        
        try:
            well_name = well.name if (well and hasattr(well, 'name')) else well_id
            print(f"Picking up mold: {well_name}")
            
            feedrate = self._feedrate
            self._machine.move_to(v=66, s=feedrate)
            self._machine.move_to(z=40, s=feedrate)
            self._machine.move(dy=23, s=feedrate)
            self._machine.move_to(v=30, s=feedrate)
            self._machine.move(dy=-23, s=feedrate)
            self._machine.move_to(z=95, s=feedrate)

            # Move back to ready position, if not already there
            self._machine.move_to(x=ready_x, y=ready_y, z=ready_z, v=ready_v, s=feedrate)
            return True
        except Exception as e:
            print(f"Error picking up mold from mold slot {well_id}: {e}")
            return False
    
    def execute_place_mold(
        self,
        well_id: str,
        deck,
        ready_x: float,
        ready_y: float,
        ready_z: float,
        ready_v: float
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
        # Get mold from deck for logging
        well = None
        try:
            # Convert well_id to slot index (well_id is already numerical: "0", "1", ... "17")
            slot_index = int(well_id)
            
            if 0 <= slot_index <= 17 and str(slot_index) in deck.slots:
                slot = deck.slots[str(slot_index)]
                if slot.has_labware and hasattr(slot.labware, 'wells'):
                    if well_id in slot.labware.wells:
                        well = slot.labware.wells[well_id]
        except Exception:
            pass
        
        try:
            well_name = well.name if (well and hasattr(well, 'name')) else well_id
            print(f"Placing mold: {well_name}")
            
            feedrate = self._feedrate
            self._machine.move_to(v=66, s=feedrate)
            self._machine.move(dy=23, s=feedrate)
            self._machine.move_to(z=40, s=feedrate)
            self._machine.move(dy=-23, s=feedrate)
            self._machine.move_to(v=30, s=feedrate)
            self._machine.move_to(z=95, s=feedrate)
            
            # Move back to ready position, if not already there
            self._machine.move_to(x=ready_x, y=ready_y, z=ready_z, v=ready_v, s=feedrate)
            return True
        except Exception as e:
            print(f"Error placing mold in mold slot {well_id}: {e}")
            return False
    
    def execute_place_mold_on_scale(
        self,
        tamper_axis: str = 'V',
        ready_x: float = None,
        ready_y: float = None,
        ready_z: float = None,
        ready_v: float = None
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
            print("Placing mold on scale...")
            self._scale.tare()
            feedrate = self._feedrate
            self._machine.move(dy=38, s=feedrate)    # Move from ready position towards scale
            self._machine.move_to(v=67, s=feedrate)  # Move mold to fit under trickler
            self._machine.gcode("M208 Z32.5:195")      # Move bed up so well fits under trickler, relax z-limit to do so
            self._machine.move_to(z=34.5, s=feedrate)
            self._machine.move(dy=7, s=feedrate)
            # TODO: open chute
            self._machine.move_to(z=32.5, s=feedrate)
            self._machine.move(dy=19, s=feedrate)
            self._machine.gcode("M208 Z27:195")      # Move bed up so well is resting on scale, relax z-limit to do so
            self._machine.move_to(z=27, s=feedrate) # Place mold on scale

            # Post-place retreat: move away from scale and mold.
            self._machine.move(dy=-19, s= feedrate)   # Back off mold so tool isn't touching
            # This sequence is intentionally undone in execute_pick_mold_from_scale.
            self._machine.move_to(z=34.5, s=feedrate)
            self._machine.move(dy=-7)
            return True
        except Exception as e:
            print(f"Error placing mold on scale: {e}")
            return False
    
    def execute_pick_mold_from_scale(
        self,
        tamper_axis: str = 'V',
        ready_x: float = None,
        ready_y: float = None,
        ready_z: float = None,
        ready_v: float = None
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
            print("Picking mold from scale...")
            feedrate = self._feedrate
            # Phase 1: undo the post-place retreat exactly in reverse order.
            self._machine.move(dy=7, s=feedrate)
            self._machine.move_to(z=27, s=feedrate)
            self._machine.move(dy=19, s=feedrate)

            # Phase 2: execute the existing pickup and retreat sequence.
            self._machine.move(dy=1, s=feedrate)          # Return to model position
            self._machine.move_to(z=32.5, s=feedrate)     # Pick up mold off scale
            self._machine.gcode("M208 Z34.5:195")         # Revert z-limit to protect tool
            self._machine.move(dy=-19, s=feedrate)        # Move mold from under trickler
            self._machine.move_to(z=34.5, s=feedrate)     # Move within z-limits
            self._machine.move(dy=-7, s=feedrate)         # Move all the way back from under trickler
            self._machine.move_to(z=ready_z, s=feedrate)  # Move mold out from trickler
            self._machine.move_to(v=30, s=feedrate)       # Move tool to travel position
            self._machine.move(dy=-39, s=feedrate)        # Restore y position to position before mold was placed
            return True
        except Exception as e:
            print(f"Error picking mold from scale: {e}")
            return False

    
    def execute_place_top_piston(
        self,
        piston_dispenser: PistonDispenser,
        tamper_axis: str = 'V',
        tamper_travel_pos: float = 34.0,
        dispenser_safe_z: float = 254.0,
        ready_x: float = None,
        ready_y: float = None,
        ready_z: float = None,
        ready_v: float = None
    ) -> bool:
        """
        # TODO: DO NOT RUN THIS WITH MORE THAN ONE DISPENSER AS IT CURRENTLY USES ABSOLUTE COORDINATES, NOT RELATIVE
        Execute movements to place top piston on current mold.
        
        Args:
            piston_dispenser: The PistonDispenser with position and piston info
            tamper_axis: Axis letter for tamper (default 'V')
            tamper_travel_pos: Travel position for tamper axis (default 30.0 mm)
            dispenser_safe_z: Safe Z height for dispenser (default 254.0 mm)
            ready_x: X coordinate of dispenser ready position (required)
            ready_y: Y coordinate of dispenser ready position (required)
            ready_z: Z coordinate of dispenser ready position (required)
            ready_v: V coordinate of dispenser ready position (required)
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            print(f"Placing top piston from dispenser {piston_dispenser.index}")
            
            feedrate = self._feedrate
            feedrate_pickup = 2000 # TODO: hardcoded to minimum speed for smooth pickup, for now
            self._machine.move_to(y=175.7, s=feedrate_pickup) # Move into dispenser to dispense piston
            self._machine.gcode("M400") # Wait for previous command to finish
            self._machine.gcode("G4 S2") # Wait for 2 seconds
            self._machine.move_to(v=21, s=feedrate) # Move tool up to pickup piston
            self._machine.move_to(y=140, s=feedrate) # Move away from dispenser
            self._machine.move_to(v=8, s=feedrate) # Push piston into mold TODO: Should be more like ~v=6
            self._machine.move_to(x=ready_x, y=ready_y, z=ready_z, v=ready_v, s=feedrate) 
            
            return True
        except Exception as e:
            print(f"Error placing top piston from dispenser {piston_dispenser.index}: {e}")
            return False
    
    def execute_tamp(
        self,
        tamper_axis: str,
        tamp_depth: float,
        tamp_speed: int
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
            print("Executing tamp at scale_ready position...")
            
            feedrate = tamp_speed

            # Save current v value to return to after tamping
            current_position = self._machine.get_position()
            saved_v = float(current_position.get('V'))
            
            # Move tamper until it is just outside mold
            self._machine.move_to(v=2, s=feedrate)
            
            # Move by requested tamp depth
            self._machine.move_to(v=tamp_depth, s=feedrate)
            self._machine.gcode("M400")
            
            # Return tamper to safe position
            self._machine.move_to(v=30, s=feedrate)
            
            # Home V axis after tamping to ensure axis accuracy
            print("Homing V axis after tamp to ensure accuracy...")
            self.execute_home_tamper(tamper_axis)
            self._machine.move_to(v=saved_v, s=feedrate)
            
            print("Tamping complete")
            return True
        except Exception as e:
            print(f"Error during tamp: {e}")
            return False
    
    # ===== BASIC MOVEMENTS =====
    
    def execute_move_to_position(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        v: Optional[float] = None,
        speed: Optional[int] = None
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
            print(f"Error executing basic move: {e}")
            return False

    def execute_move_to_sample_tray(
        self,
        x: float,
        y: float,
        z: float
    ) -> bool:
        """
        Move the hardness tester to a sample tray ready coordinate.

        The state machine resolves tray and validates tool/position
        requirements before this executor is called.
        """
        try:
            feedrate = self._feedrate
            print(f"Moving hardness tester to sample tray: x={x}, y={y}, z={z}")
            self._machine.move_to(x=x, y=y, z=z, s=feedrate)
            return True
        except Exception as e:
            print(f"Error moving to hardness sample tray: {e}")
            return False

    def execute_test_sample(
        self,
        tray_index: int,
        sample_id: str,
        mode: Optional[str] = None,
        hardness_tester: HardnessTester = None,
        target_x: float = None,
        target_y: float = None,
        target_z: float = None,
        state_machine=None,
    ) -> bool:
        """
        Sketch of the hardness sample sequence with z-probe offset transition.

        Pre-condition (validated by the state machine before this is called):
          - ``context.position_id`` is the relevant ``sample_tray_X_ready``.
          - ``context.tool_offset_id == "durometer"`` (action's required_offset).
          - target_x / target_y / target_z are resolved base machine coords
            for the current logical sample-tray frame.

        Sequence:
          1. Move XY over the sample at the tray's safe (durometer) Z.
          2. Switch to ``durometer_z_probe`` (transient) so the probe tip
             is the active reference. Probe down to find the sample top.
          3. ALWAYS restore the ``durometer`` offset before returning so the
             action's required_offset post-condition is satisfied (try/finally).
          4. Drive the durometer down for contact pressure, read the LCD via
             the HardnessTester, then retract to the tray's safe Z.

        The offset switches are issued via ``state_machine.apply_tool_offset``,
        which both updates ``context.tool_offset_id`` and physically settles
        the bed at the same logical position under the new offset frame.
        """
        if state_machine is None:
            print("execute_test_sample requires a state_machine reference for offset switches")
            return False
        if target_x is None or target_y is None or target_z is None:
            print("execute_test_sample requires fully-resolved target_x/y/z")
            return False
        self.last_hardness_result = None
        self.last_hardness_error = None

        feedrate = self._feedrate

        # 1) Move XY over the sample at the durometer-offset safe Z.
        try:
            self._machine.move_to(x=target_x, y=target_y, z=target_z, s=feedrate)
            self.wait_for_moves_to_finish()
        except Exception as exc:
            print(f"Error moving over sample {sample_id} on tray {tray_index}: {exc}")
            return False

        try:
            # 2) Transient switch to the z-probe offset to find the sample
            # surface. apply_tool_offset re-resolves the tray ready position
            # under durometer_z_probe and moves the bed accordingly so the
            # probe tip is at the same logical (base) Z. Probe logic is
            # hardware-specific and is left as a stub.
            zprobe_result = state_machine.apply_tool_offset("durometer_z_probe")
            if not zprobe_result.valid:
                print(f"Failed to switch to durometer_z_probe offset: {zprobe_result.reason}")
                return False

            # TODO: Issue the actual z-probe descent (e.g. G38.2 / vendor
            # probe routine) and capture the contact Z. Until the probing
            # hardware is wired up, this is a no-op placeholder.
            probed_top_z = None  # Replace with real probe result.

            # 4) Drive the durometer onto the sample and read the LCD. This
            # belongs in the HardnessTester (which owns the camera / segment
            # decoder); the executor only sequences motion + offset state.
            # The HardnessTester can use ``probed_top_z`` to compute its
            # final approach Z under the durometer offset.
            print(
                "Hardness sample motion stub "
                f"(tray={tray_index}, sample={sample_id}, mode={mode}, "
                f"probed_top_z={probed_top_z})"
            )
            if hardness_tester is None:
                self.last_hardness_error = "Hardness tester instance was not provided for OCR."
                return True

            reading = hardness_tester.read_display(
                debug=False,
                debug_prefix=f"hardness_{tray_index}_{sample_id}",
            )
            measured_value, sample_error = hardness_tester._parse_hardness_reading(reading)
            self.last_hardness_result = measured_value
            self.last_hardness_error = sample_error
            return True
        finally:
            # 3) Always restore the durometer offset before returning so the
            # action's required_offset post-condition holds even on failure.
            restore_result = state_machine.apply_tool_offset("durometer")
            if not restore_result.valid:
                # Best-effort logging; we cannot raise from finally without
                # masking an in-flight exception.
                print(
                    "WARNING: failed to restore durometer offset after "
                    f"hardness sample: {restore_result.reason}"
                )

    def execute_hardness_turn_on(self, mode: Optional[str] = None) -> bool:
        """
        Placeholder for Shore tester power-button actuation.

        Intentionally left as a stub for hardware-specific implementation.
        """
        # TODO: Implement Shore tester power-button servo actuation.
        return False

    def execute_hardness_turn_off(self, mode: Optional[str] = None) -> bool:
        """
        Placeholder for Shore tester power-button actuation.

        Intentionally left as a stub for hardware-specific implementation.
        """
        # TODO: Implement Shore tester power-button servo actuation.
        return False

    def execute_hardness_zero(self, mode: Optional[str] = None) -> bool:
        """
        Placeholder for Shore tester zero-button actuation.

        Intentionally left as a stub for hardware-specific implementation.
        """
        # TODO: Implement Shore tester zero-button servo actuation.
        return False


    def execute_home_all(self, registry) -> bool:
        """Home all axes and return to global_ready position.

        After homing, the no-tool / manipulator (zero) offset frame is the
        only valid frame, so the global_ready coordinates can be sent without
        any offset adjustment.

        Returns:
            True if successful, False otherwise.
        """
        try:
            self._machine.home_all()
            # After homing, move to global_ready position if not already there
            global_ready_pos = registry.find_first_of_type(PositionType.GLOBAL_READY)
            if global_ready_pos and global_ready_pos.coordinates:
                coords = global_ready_pos.coordinates
                # Get z height from z_heights if needed
                z_height = None
                if coords.z == "USE_Z_HEIGHT_POLICY":
                    # Use mold_transfer_safe z height
                    z_heights = registry.z_heights
                    if "mold_transfer_safe" in z_heights:
                        z_config = z_heights["mold_transfer_safe"]
                        if isinstance(z_config, dict):
                            z_height = z_config.get("z_coordinate")

                # The manipulator offset is the zero/reference frame, so
                # global_ready coordinates can be commanded directly. We
                # query the registry for the offset to keep this honest if
                # someone configures a non-zero manipulator offset later.
                offset_x, offset_y, offset_z = registry.get_tool_offset("manipulator")

                def _adjusted(value, offset):
                    if value is None:
                        return None
                    if isinstance(value, str):
                        if value.startswith("PLACEHOLDER"):
                            return None
                        return None
                    return float(value) + offset

                x = _adjusted(coords.x, offset_x)
                y = _adjusted(coords.y, offset_y)
                z = _adjusted(z_height, offset_z)
                v = coords.v if (coords.v is not None and (not isinstance(coords.v, str) or not coords.v.startswith("PLACEHOLDER"))) else None

                if x is not None or y is not None or z is not None or v is not None:
                    feedrate = self._feedrate
                    self._machine.move_to(x=x, y=y, z=z, v=v, s=feedrate)
            return True
        except Exception as e:
            print(f"Error homing all axes: {e}")
            return False
    
    def execute_pickup_tool(
        self,
        tool,
        global_ready_x: float,
        global_ready_y: float,
        global_ready_z: float,
        global_ready_v: Optional[float] = None,
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
            print(f"Error picking up tool: {e}")
            return False

    def execute_park_tool(
        self,
        global_ready_x: float,
        global_ready_y: float,
        global_ready_z: float,
        global_ready_v: Optional[float] = None,
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
            print(f"Error parking tool: {e}")
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
            print(f"Error homing XYZ axes: {e}")
            return False
    
    def execute_move_to_mold_slot(
        self,
        x: float,
        y: float,
        z: float,
        v: Optional[float] = None,
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
            print(f"Error moving to well: {e}")
            print(f"Coordinate: x={x}, y={y}, z={z}, v={v}")
            return False
    
    def execute_move_to_scale(
        self,
        ready_x: float,
        ready_y: float,
        ready_z: float,
        ready_v: float
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
            SCALE_READY position requires z_height_policy: allowed=['dispenser_safe', 'mold_transfer_safe']
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            feedrate = self._feedrate
            self._machine.move_to(x=ready_x, y=ready_y, z=ready_z, v=ready_v, s=feedrate)
            return True
        except Exception as e:
            print(f"Error moving to scale ready position: {e}")
            return False
    
    def get_machine_position(self) -> dict:
        """Get current machine position."""
        return self._machine.get_position()
    
    def get_machine_axes_homed(self) -> list:
        """Get list of which axes are homed."""
        return getattr(self._machine, 'axes_homed', [False, False, False, False])

    def wait_for_moves_to_finish(self) -> None:
        """
        Wait for all buffered moves to complete execution.
        
        Executes the M400 G-code command, which blocks until all previously
        buffered moves in the machine's internal buffer have been executed.
        This ensures the Python program does not advance past the physical
        state of the Jubilee.
        """
        self._machine.gcode("M400")

    def execute_apply_tool_offset(
        self,
        tool_index: int,
        offset_x: float,
        offset_y: float,
        offset_z: float,
    ) -> bool:
        """
        Apply a firmware tool-frame offset using G10.

        Args:
            tool_index: Firmware tool index (G10 P value)
            offset_x: X offset in mm
            offset_y: Y offset in mm
            offset_z: Z offset in mm

        Returns:
            True if successful, False otherwise.
        """
        try:
            self._machine.gcode(
                f"G10 P{int(tool_index)} X{float(offset_x)} Y{float(offset_y)} Z{float(offset_z)}"
            )
            self._machine.gcode("M400")
            return True
        except Exception as e:
            print(
                "Error applying firmware tool offset "
                f"(P{tool_index} X{offset_x} Y{offset_y} Z{offset_z}): {e}"
            )
            return False
    
    def execute_move_to_scale_location(
        self,
        ready_x: float,
        ready_y: float,
        ready_z: float,
        ready_v: float
    ) -> bool:
        """
        Move to the scale ready location.
        
        Moved from JubileeManager._move_to_scale()
        
        Args:
            ready_x: X coordinate of scale ready position (required)
            ready_y: Y coordinate of scale ready position (required)
            ready_z: Z coordinate of scale ready position (required)
            ready_v: V coordinate of scale ready position (required)
        
        Returns:
            True if successful, False otherwise
            
        Note:
            Z-height safety is enforced by state machine's z_height_policy validation.
            SCALE_READY position requires z_height_policy: allowed=['dispenser_safe', 'mold_transfer_safe']
        """
        try:
            feedrate = self._feedrate
            self._machine.move_to(x=ready_x, y=ready_y, z=ready_z, v=ready_v, s=feedrate)
            return True
        except Exception as e:
            print(f"Error moving to scale: {e}")
            return False
    
    def execute_fill_powder(
        self,
        target_weight: float
    ) -> bool:
        """
        Fill mold with powder using the trickler.
        
        Moved from JubileeManager._fill_powder()
        
        Args:
            target_weight: Target weight to fill
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self._machine.gcode("M400") # Ensure all other actions have finished so mold is actually under trickler
             # Determine feedrate string for G-code
            feedrate_str = str("F200")
            
            threshold_90_percent = 0.9 * target_weight
            max_step_size = 8                           # Maximum step size when weight is very low
            min_step_size = 1.0                         # Minimum step size when approaching 90% threshold
            feedback_step_size = 0.2
            
            # Track if threshold crossed
            threshold_crossed = False
            time.sleep(2) # Wait 2 seconds to stabilize
            self._scale.tare()
            initial_weight = self._scale.get_weight(stable=True)

            print(f"Target: {target_weight:.4f}g, 90% threshold: {threshold_90_percent:.4f}g\n")
            self._machine.gcode("G92 W0") # Reset trickler axis
            self._machine.gcode("G91") # Set relative positioning mode
            
            iteration = 0
            rolling_avg_alpha = 0.5 # Reactivity parameter for exponential rolling average
            exp_rolling_avg = 0
            while True:
                iteration += 1
                
                # Get current weight (unstable) to determine behavior
                current_weight = self._scale.get_weight(stable=False)
                exp_rolling_avg = (rolling_avg_alpha * current_weight + ((1 - rolling_avg_alpha) * exp_rolling_avg))
                
                if current_weight >= threshold_90_percent:
                    # Above 90% threshold: feedback loop mode
                    if not threshold_crossed:
                        # First time crossing threshold - mark it
                        threshold_crossed = True
                        print(f"Crossed 90% threshold at {current_weight:.4f}g. Entering feedback loop mode.")
                    
                    # Keep vibration off unless powder dispensing has slowed
                    if exp_rolling_avg < 0.05:
                        self._machine.gcode("M42 P0 S0.5 F20000") # Turn on vibration
                    # Move -> unstable weight -> move
                    self._machine.gcode(f"G1 W{feedback_step_size} {feedrate_str}")
                    self._machine.gcode("M400")
                    self._machine.gcode("M42 P0 S0.0 F20000") # Turn off vibration
                    time.sleep(0.2) # Small sleep to promote scale settling
                    
                    # Get unstable weight readin
                    try:
                        unstable_weight = self._scale.get_weight(stable=False)
                        
                        # Check if within 1% of target weight or above target
                        threshold_99_percent = 0.99 * target_weight
                        if unstable_weight >= threshold_99_percent:
                            # Wait 2 seconds to confirm actually over threshold
                            if unstable_weight >= target_weight:
                                print(f"Unstable weight {unstable_weight:.4f}g >= target {target_weight:.4f}g. Waiting 4 seconds for confirmation...")
                            else:
                                print(f"Unstable weight {unstable_weight:.4f}g is within 1% of target {target_weight:.4f}g (>= {threshold_99_percent:.4f}g). Waiting 4 seconds for confirmation...")
                            time.sleep(2.0)
                            
                            # Final stable measurement to confirm
                            final_weight = self._scale.get_weight(stable=True)
                                                
                            print(f"Final stable measurement: Weight={final_weight:.4f}g")
                            
                            # Check if stable weight is actually over threshold
                            if final_weight >= threshold_99_percent:
                                print(f"\nTarget weight of {target_weight:.4f}g reached!")
                                self.last_fill_weight = final_weight
                                break
                            else:
                                # Stable weight is below threshold, restart trickling
                                print(f"Stable weight {final_weight:.4f}g is below threshold {threshold_99_percent:.4f}g. Restarting trickling...")
                                continue
                            
                    except Exception as e:
                        print(f"Error reading weight at iteration {iteration}: {e}")
                        # Continue the loop even if there's an error
                        continue
                else:
                    # Below 90% threshold: big movements with vibration, stable measurements after each
                    # Linear decrease: step_size decreases smoothly as weight approaches 90% threshold
                    progress = max(0, current_weight / threshold_90_percent)  # 0 to 1
                    step_size = max_step_size - ((max_step_size - min_step_size) * progress)
                    
                    # Move with vibration
                    self._machine.gcode("M42 P0 S0.5 F20000") # Turn on vibration
                    self._machine.gcode(f"G1 W{step_size}{feedrate_str}")
                    self._machine.gcode("M400")
                    self._machine.gcode("M42 P0 S0.0 F20000") # Turn off vibration
                    time.sleep(0.1) # Small sleep to promote scale settling
                    
                    # Take unstabilized weight reading after big movement
                    try:
                        weight = self._scale.get_weight(stable=False)
                        print(f"Iteration {iteration}: Weight={weight:.4f}g, Step={step_size:.2f}mm")
                        
                    except Exception as e:
                        print(f"Error reading weight at iteration {iteration}: {e}")
            
            # Restore absolute positioning mode
            self._machine.gcode("G90")
            return True
        except Exception as e:
            print(f"Error filling mold with powder: {e}")
            # Restore absolute positioning mode on error
            try:
                self._machine.gcode("G90")
            except:
                pass
            return False
        
    def execute_home_tamper(
        self,
        tamper_axis: str = 'V'
    ) -> None:
        """
        Perform homing for the tamper axis (V-axis).
        
        This homing process can be performed while holding a mold without a top piston.
        The homing uses the mold itself as a reference:
        - Start position: v=2 (tamper inserted into mold)
        - End position: v=-7 (tamper touching bottom of mold)
        
        This establishes accurate positioning by using the mold bottom as a reference point.
        
        Moved from Manipulator.home_tamper()
        
        Args:
            tamper_axis: Axis letter for tamper (default 'V')
            
        Raises:
            RuntimeError: If axes are not properly homed before attempting tamper homing
        """
        # Check if axes are homed
        axes_homed = getattr(self._machine, 'axes_homed', [False, False, False, False])
        axis_names = ['X', 'Y', 'Z', 'U']
        not_homed = [axis_names[i] for i in range(4) if not axes_homed[i]]
        
        if not_homed:
            print(f"Axes not homed: {', '.join(not_homed)}")
            raise RuntimeError(
                f"X, Y, Z, and U axes must be homed before homing the tamper "
                f"({tamper_axis}) axis."
            )
        
        # Perform homing for tamper axis
        self._machine.gcode(f'M98 P"home{tamper_axis.lower()}.g"')
        
        print(f"Homing complete. {tamper_axis} axis position reset to 0.0mm")
    
    def execute_home_manipulator(
        self,
        manipulator_axis: str = 'V'
    ) -> bool:
        """
        Home the manipulator axis (V).
        
        Args:
            manipulator_axis: Axis letter for manipulator (default 'V')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Perform homing for manipulator axis
            self._machine.gcode(f'M98 P"home{manipulator_axis.lower()}.g"')
            print(f"Manipulator ({manipulator_axis}) homing complete. Position reset to 0.0mm")
            return True
        except Exception as e:
            print(f"Error homing manipulator: {e}")
            return False
    
    def execute_home_trickler(
        self,
        trickler_axis: str = 'W'
    ) -> bool:
        """
        Home the trickler axis (W).
        
        Args:
            trickler_axis: Axis letter for trickler (default 'W')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Trickler can be homed at any time, no prerequisites
            self._machine.gcode(f'M98 P"home{trickler_axis.lower()}.g"')
            print(f"Trickler ({trickler_axis}) homing complete. Position reset to 0.0mm")
            return True
        except Exception as e:
            print(f"Error homing trickler: {e}")
            return False
