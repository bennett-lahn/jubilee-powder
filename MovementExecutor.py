"""
MotionPlatformExecutor - Low-level movement execution for validated state machine moves.

This module contains all the physical movement execution logic for the Jubilee
motion platform. All methods assume validation has already occurred in the
MotionPlatformStateMachine. 

The executor is owned by the state machine and is not accessed directly by other
components, so all movements go through validation.
"""
import time

from typing import Optional, Union
from enum import Enum
from science_jubilee.Machine import Machine
from Scale import Scale
from PistonDispenser import PistonDispenser
from MotionPlatformStateMachine import PositionType


class FeedRate(Enum):
    """Enumeration for feedrate settings."""
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"


class MovementExecutor:
    """
    Executes physical movements on the machine after state machine validation.
    
    This class should not be instantiated directly by user code. Instead, it is
    owned by MotionPlatformStateMachine and accessed through validated methods.
    """
    
    # Feedrate constants (in mm/min)
    FEEDRATE_FAST = 700
    FEEDRATE_MEDIUM = 700
    FEEDRATE_SLOW = 700
    
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
        self._feedrate = feedrate
    
    def _get_feedrate(self) -> int:
        """
        Get the current feedrate value based on the selected FeedRate enum.
        
        Returns:
            Feedrate value in mm/min
        """
        if self._feedrate == FeedRate.FAST:
            return self.FEEDRATE_FAST
        elif self._feedrate == FeedRate.MEDIUM:
            return self.FEEDRATE_MEDIUM
        elif self._feedrate == FeedRate.SLOW:
            return self.FEEDRATE_SLOW
        else:
            return self.FEEDRATE_MEDIUM  # Default fallback
    
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
            
            feedrate = self._get_feedrate()
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
            
            feedrate = self._get_feedrate()
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
            feedrate = self._get_feedrate()
            self._machine.move(dy=38, s=feedrate)    # Move from ready position towards scale
            self._machine.move_to(v=67, s=feedrate)  # Move mold to fit under trickler
            self._machine.gcode("M208 Z38:195")      # Move bed up so well fits under trickler, relax z-limit to do so
            self._machine.move_to(z=38, s=feedrate)
            self._machine.move(dy=26, s=feedrate)    # Move mold under trickler    
            self._machine.gcode("M208 Z28:195")      # Move bed up so well is resting on scale, relax z-limit to do so
            self._machine.move_to(z=28, s=feedrate)
            self._machine.move(dy=-1, s= feedrate)   # Back off mold so tool isn't touching
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
            feedrate = self._get_feedrate()
            self._machine.move(dy=1, s=feedrate)      # Return to model position
            self._machine.move_to(z=38, s=feedrate)  # Pick up well off scale
            self._machine.gcode("M208 Z38:195")      # Revert z-limit
            self._machine.move(dy=-26, s=feedrate)    # Move well from under trickler
            self._machine.move_to(z=ready_z, s=feedrate)  # Move mold out from trickler
            self._machine.gcode("M208 Z38:195")      # Restore z-limit to protect tool
            self._machine.move_to(v=30, s=feedrate)  # Move tool to travel position
            self._machine.move(dy=-38, s=feedrate)    # Restore y position to position before well was placed
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
        # TODO: Do NOT RUN THIS WITH MORE THAN ONE DISPENSER AS IT CURRENTLY USES ABSOLUTE COORDINATES, NOT RELATIVE
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
            
            feedrate = self._get_feedrate()
            feedrate_pickup = 2000 # TODO: hardcoded to minimum speed for smooth pickup, for now
            self._machine.move_to(y=177.7, s=feedrate_pickup) # Move into dispenser to dispense piston
            self._machine.gcode("M400") # Wait for previous command to finish
            self._machine.gcode("G4 S2") # Wait for 2 seconds
            self._machine.move_to(v=21, s=feedrate) # Move tool up to pickup piston
            self._machine.move_to(y=140, s=feedrate) # Move away from dispenser
            self._machine.move_to(v=8, s=feedrate) # Push piston into mold
            self._machine.move_to(x=ready_x, y=ready_y, z=ready_z, v=ready_v, s=feedrate) 
            
            return True
        except Exception as e:
            print(f"Error placing top piston from dispenser {piston_dispenser.index}: {e}")
            return False
    
    def execute_tamp(
        self,
        tamper_axis: str = 'V',
        scale_y: float = None
    ) -> bool:
        """
        Execute tamping movements.
        
        Args:
            tamper_axis: Axis letter for tamper (default 'V')
            scale_y: Y coordinate of the physical scale location (required for moving bed)
        
        Returns:
            True if successful, False otherwise.
        """
        if scale_y is None:
            raise RuntimeError("Scale Y coordinate must be provided for tamping")
        
        try:
            print("Executing tamp")
            
            feedrate = self._get_feedrate()
            self._machine._set_absolute_positioning()
            self._machine.move_to(v=38.5, s=feedrate)  # Prepare for tamp
            self._machine.move(dy=scale_y, s=feedrate)  # Move from under trickler
            self._machine.move_to(v=0, s=feedrate)  # Move until stall detection stops movement
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
                speed = self._get_feedrate()
            self._machine.move_to(x=x, y=y, z=z, v=v, s=speed)
            return True
        except Exception as e:
            print(f"Error executing basic move: {e}")
            return False
    
    
    def execute_home_all(self, registry) -> bool:
        """Home all axes and return to global_ready position.
        
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
                
                # Move to global_ready coordinates
                # Skip placeholders - they'll be handled by the state machine
                x = coords.x if (coords.x is not None and (not isinstance(coords.x, str) or not coords.x.startswith("PLACEHOLDER"))) else None
                y = coords.y if (coords.y is not None and (not isinstance(coords.y, str) or not coords.y.startswith("PLACEHOLDER"))) else None
                z = z_height if (z_height is not None and (not isinstance(z_height, str) or not z_height.startswith("PLACEHOLDER"))) else None
                v = coords.v if (coords.v is not None and (not isinstance(coords.v, str) or not coords.v.startswith("PLACEHOLDER"))) else None
                
                if x is not None or y is not None or z is not None or v is not None:
                    feedrate = self._get_feedrate()
                    self._machine.move_to(x=x, y=y, z=z, v=v, s=feedrate)
            return True
        except Exception as e:
            print(f"Error homing all axes: {e}")
            return False
    
    def execute_pickup_tool(
        self,
        tool,
        registry
    ) -> bool:
        """
        Pick up a tool and move to global_ready position.
        
        Note: The machine's pickup_tool() method is decorated with @requires_safe_z,
        which automatically raises the bed height to deck.safe_z + 20 if it is not
        already at that height.
        
        Args:
            tool: The Tool object to pick up (must be manipulator for now)
            registry: PositionRegistry to get global_ready coordinates
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate that only manipulator tool is supported
            if not hasattr(tool, 'name') or tool.name != "manipulator":
                raise ValueError(f"Only manipulator tool is supported. Attempted to pick up: {tool.name if hasattr(tool, 'name') else type(tool).__name__}")
            
            # Pick up the tool
            self._machine.pickup_tool(tool)
            
            # Move to global_ready position if not already there (tool macros should return to global ready)
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
                
                # Move to global_ready coordinates
                # Skip placeholders - they'll be handled by the state machine
                x = coords.x if (coords.x is not None and (not isinstance(coords.x, str) or not coords.x.startswith("PLACEHOLDER"))) else None
                y = coords.y if (coords.y is not None and (not isinstance(coords.y, str) or not coords.y.startswith("PLACEHOLDER"))) else None
                z = z_height if (z_height is not None and (not isinstance(z_height, str) or not z_height.startswith("PLACEHOLDER"))) else None
                v = coords.v if (coords.v is not None and (not isinstance(coords.v, str) or not coords.v.startswith("PLACEHOLDER"))) else None
                
                if x is not None or y is not None or z is not None or v is not None:
                    feedrate = self._get_feedrate()
                    self._machine.move_to(x=x, y=y, z=z, v=v, s=feedrate)
            
            return True
        except Exception as e:
            print(f"Error picking up tool: {e}")
            return False
    
    def execute_park_tool(
        self,
        registry
    ) -> bool:
        """
        Park the current tool and move to global_ready position.
        
        Note: The machine's park_tool() method is decorated with @requires_safe_z,
        which automatically raises the bed height to deck.safe_z + 20 if it is not
        already at that height. 
        
        Args:
            registry: PositionRegistry to get global_ready coordinates
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Park the tool
            self._machine.park_tool()
            
            # Move to global_ready position
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
                
                # Move to global_ready coordinates
                # Skip placeholders - they'll be handled by the state machine
                x = coords.x if (coords.x is not None and (not isinstance(coords.x, str) or not coords.x.startswith("PLACEHOLDER"))) else None
                y = coords.y if (coords.y is not None and (not isinstance(coords.y, str) or not coords.y.startswith("PLACEHOLDER"))) else None
                z = z_height if (z_height is not None and (not isinstance(z_height, str) or not z_height.startswith("PLACEHOLDER"))) else None
                v = coords.v if (coords.v is not None and (not isinstance(coords.v, str) or not coords.v.startswith("PLACEHOLDER"))) else None
                
                if x is not None or y is not None or z is not None or v is not None:
                    feedrate = self._get_feedrate()
                    self._machine.move_to(x=x, y=y, z=z, v=v, s=feedrate)
            
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
        z: Union[float, str, None] = None,
        v: Optional[float] = None,
        registry = None
    ) -> bool:
        """
        Move to a specific mold slot position using coordinates from motion_platform_positions.json.
        
        Args:
            x: X coordinate of mold slot ready position (required)
            y: Y coordinate of mold slot ready position (required)
            z: Z coordinate of mold slot ready position (optional, or "USE_Z_HEIGHT_POLICY")
            v: V coordinate of mold slot ready position (optional)
            registry: PositionRegistry to resolve z heights (required if z="USE_Z_HEIGHT_POLICY")
            
        Returns:
            True if successful, False otherwise
            
        Note:
            Z-height safety is enforced by state machine's z_height_policy validation.
            MOLD_READY positions require z_height_policy: allowed=['dispenser_safe', 'mold_transfer_safe']
            
            When z="USE_Z_HEIGHT_POLICY", the method infers the correct z height based on
            the current machine z position:
            - If currently at transfer height (mold_transfer_safe), use that
            - Otherwise use dispenser height (dispenser_safe)
        """
        try:
            resolved_z = z
            
            # Handle USE_Z_HEIGHT_POLICY
            if isinstance(z, str) and z == "USE_Z_HEIGHT_POLICY":
                if registry is None:
                    raise ValueError("Registry required when z=USE_Z_HEIGHT_POLICY")
                
                # Get current machine position
                current_pos = self._machine.get_position()
                current_z = float(current_pos.get('Z', 0.0))
                
                # Get z heights from registry
                z_heights = registry.z_heights
                tolerance = registry.coordinate_tolerance.get('z', 0.2)
                
                # Determine which z height we're currently at
                inferred_z_height_id = None
                
                # Check each z height to see if current position matches
                for z_height_id, z_config in z_heights.items():
                    if isinstance(z_config, dict):
                        z_coord = z_config.get("z_coordinate")
                        if z_coord and isinstance(z_coord, (int, float)):
                            if abs(current_z - z_coord) <= tolerance:
                                inferred_z_height_id = z_height_id
                                break
                
                # If we identified the current z height, use it
                if inferred_z_height_id:
                    z_config = z_heights[inferred_z_height_id]
                    if isinstance(z_config, dict):
                        resolved_z = z_config.get("z_coordinate")
                        print(f"Inferred z height: {inferred_z_height_id} (z={resolved_z}mm) based on current z={current_z:.2f}mm")
                else:
                    # Default to dispenser_safe if we can't determine current height
                    # This is the safer option (higher z)
                    if "dispenser_safe" in z_heights:
                        z_config = z_heights["dispenser_safe"]
                        if isinstance(z_config, dict):
                            resolved_z = z_config.get("z_coordinate")
                            if isinstance(resolved_z, str):
                                raise ValueError(f"dispenser_safe z_coordinate is a placeholder: '{resolved_z}'. Please configure a numeric value.")
                            print(f"Could not infer z height from current z={current_z:.2f}mm, defaulting to dispenser_safe (z={resolved_z}mm)")
                    elif "mold_transfer_safe" in z_heights:
                        # Fallback to mold_transfer_safe if dispenser_safe not available
                        z_config = z_heights["mold_transfer_safe"]
                        if isinstance(z_config, dict):
                            resolved_z = z_config.get("z_coordinate")
                            if isinstance(resolved_z, str):
                                raise ValueError(f"mold_transfer_safe z_coordinate is a placeholder: '{resolved_z}'. Please configure a numeric value.")
                            print(f"Could not infer z height from current z={current_z:.2f}mm, defaulting to mold_transfer_safe (z={resolved_z}mm)")
                    else:
                        raise ValueError(f"No suitable z height found in registry for current z={current_z:.2f}mm")
                
                # Final validation that resolved_z is numeric
                if not isinstance(resolved_z, (int, float)):
                    raise ValueError(f"Resolved z coordinate is not numeric: {resolved_z} (type: {type(resolved_z).__name__})")
            
            feedrate = self._get_feedrate()
            self._machine.move_to(x=x, y=y, z=resolved_z, v=v, s=feedrate)
            return True
        except Exception as e:
            print(f"Error moving to well: {e}")
            print (f"Coordinate: x={x}, y={y}, z={z}, v={v}")
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
            feedrate = self._get_feedrate()
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
            feedrate = self._get_feedrate()
            self._machine.move_to(x=ready_x, y=ready_y, z=ready_z, v=ready_v, s=feedrate)
            return True
        except Exception as e:
            print(f"Error moving to scale: {e}")
            return False
    
    def execute_dispense_powder(
        self,
        target_weight: float
    ) -> bool:
        """
        Dispense powder to the scale.
        
        Moved from JubileeManager._dispense_powder()
        
        Args:
            target_weight: Target weight to dispense
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self._machine.gcode("M400") # Ensure all other actions have finished so mold is actually under trickler
             # Determine feedrate string for G-code
            feedrate_str = str("F200")
            
            threshold_90_percent = 0.9 * target_weight
            max_step_size = 4                           # Maximum step size when weight is very low
            min_step_size = 0.2                         # Minimum step size when approaching 90% threshold
            feedback_step_size = 0.05
            
            # Track if threshold crossed
            threshold_crossed = False
            time.sleep(2) # Wait 1 second to stabilize
            self._scale.tare()
            initial_weight = self._scale.get_weight(stable=True)

            print(f"Target: {target_weight:.4f}g, 90% threshold: {threshold_90_percent:.4f}g\n")
            self._machine.gcode("G92 W0") # Reset trickler axis
            self._machine.gcode("G91") # Set relative positioning mode
            
            iteration = 0
            while True:
                iteration += 1
                
                # Get current weight (unstable) to determine behavior
                current_weight = self._scale.get_weight(stable=False)
                
                if current_weight >= threshold_90_percent:
                    # Above 90% threshold: feedback loop mode
                    if not threshold_crossed:
                        # First time crossing threshold - mark it
                        threshold_crossed = True
                        print(f"Crossed 90% threshold at {current_weight:.4f}g. Entering feedback loop mode.")
                    
                    # Keep vibration off
                    # Move -> unstable weight -> move
                    self._machine.gcode(f"G1 W{feedback_step_size} {feedrate_str}")
                    self._machine.gcode("M400")
                    time.sleep(0.2)                         # Small sleep to promote scale settling
                    
                    # Get unstable weight readin
                    try:
                        unstable_weight = self._scale.get_weight(stable=False)
                        
                        # Check if within 1% of target weight or above target
                        threshold_99_percent = 0.99 * target_weight
                        if unstable_weight >= threshold_99_percent:
                            # Wait 4 seconds to confirm actually over threshold
                            if unstable_weight >= target_weight:
                                print(f"Unstable weight {unstable_weight:.4f}g >= target {target_weight:.4f}g. Waiting 4 seconds for confirmation...")
                            else:
                                print(f"Unstable weight {unstable_weight:.4f}g is within 5% of target {target_weight:.4f}g (>= {threshold_99_percent:.4f}g). Waiting 4 seconds for confirmation...")
                            time.sleep(4.0)
                            
                            # Final stable measurement to confirm
                            final_weight = self._scale.get_weight(stable=True)
                                                
                            print(f"Final stable measurement: Weight={final_weight:.4f}g")
                            
                            # Check if stable weight is actually over threshold
                            if final_weight >= threshold_99_percent:
                                print(f"\nTarget weight of {target_weight:.4f}g reached!")
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
                    time.sleep(0.33)
                    self._machine.gcode(f"G1 W{step_size}{feedrate_str}")
                    self._machine.gcode("M400")
                    self._machine.gcode("M42 P0 S0.0 F20000") # Turn off vibration
                    time.sleep(0.33)
                    
                    # Take stabilized weight reading after big movement
                    try:
                        weight = self._scale.get_weight(stable=True)
                        
                        
                        print(f"Iteration {iteration}: Weight={weight:.4f}g, Step={step_size:.2f}mm")
                        
                    except Exception as e:
                        print(f"Error reading weight at iteration {iteration}: {e}")
            
            # Restore absolute positioning mode
            self._machine.gcode("G90")
            return True
        except Exception as e:
            print(f"Error dispensing powder: {e}")
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
        Perform sensorless homing for the tamper axis.
        
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
        self._machine.send_command(f'M98 P"home{tamper_axis.lower()}.g"')
        
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
            self._machine.send_command(f'M98 P"home{manipulator_axis.lower()}.g"')
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
            self._machine.send_command(f'M98 P"home{trickler_axis.lower()}.g"')
            print(f"Trickler ({trickler_axis}) homing complete. Position reset to 0.0mm")
            return True
        except Exception as e:
            print(f"Error homing trickler: {e}")
            return False
