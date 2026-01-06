"""
JubileeManager - Centralized management of Jubilee machine and related components.

This module provides the JubileeManager class for coordinating complex tasks
that require interacting with the instantiated Jubilee machine as well as other
components like trickler or toolhead to perform complex tasks like weighing containers.

The JubileeManager uses a MotionPlatformStateMachine to validate and execute all
movements, ensuring that operations cannot bypass safety checks.
"""

from typing import Optional, List
from pathlib import Path

# Import Jubilee components
from science_jubilee.Machine import Machine
from science_jubilee.decks.Deck import Deck
from Scale import Scale
from PistonDispenser import PistonDispenser
from Manipulator import Manipulator, ToolStateError
from MotionPlatformStateMachine import MotionPlatformStateMachine
from MovementExecutor import FeedRate
from ConfigLoader import config

# TODO: Set hard z limit for when tool is engaged so bed doesnt hit leadscrew

class JubileeManager:
    """
    Manages the Jubilee machine and related components.
    
    All movements are validated through the MotionPlatformStateMachine, which is owned
    by this manager and cannot be bypassed.
    """
    
    # TODO: make dispensers configurable from UI
    def __init__(self, num_piston_dispensers: int = 0, num_pistons_per_dispenser: int = 0, feedrate: FeedRate = FeedRate.MEDIUM):
        self.scale: Optional[Scale] = None
        self.manipulator: Optional[Manipulator] = None
        self.state_machine: Optional[MotionPlatformStateMachine] = None
        self.connected = False
        self._num_piston_dispensers = num_piston_dispensers
        self._num_pistons_per_dispenser = num_pistons_per_dispenser
        self._feedrate = feedrate
    
    @property
    def machine_read_only(self) -> Optional[Machine]:
        """
        Access to machine through state machine.
        This should ONLY be used for actions that do not change the Jubilee's state,
        even though it is possible to do so (IT IS UNSAFE).
        """
        if self.state_machine:
            return self.state_machine.machine
        return None
    
    @property
    def deck(self) -> Optional[Deck]:
        """Access to deck through state machine."""
        if self.state_machine:
            return self.state_machine.context.deck
        return None
    
    @property
    def piston_dispensers(self) -> List[PistonDispenser]:
        """Access to piston dispensers through state machine."""
        if self.state_machine:
            return self.state_machine.context.piston_dispensers
        return []
        
    def connect(
        self,
        machine_address: str = None,
        scale_port: str = "/dev/ttyUSB0",
        state_machine_config: str = "./jubilee_api_config/motion_platform_positions.json"
    ):
        """
        Connect to Jubilee machine, scale, and initialize the state machine.
        
        Args:
            machine_address: IP address of the Jubilee machine (uses config if None)
            scale_port: Serial port for the scale connection
            state_machine_config: Path to state machine configuration file
        """
        try:
            # Use config IP if no address provided
            if machine_address is None:
                machine_address = config.get_duet_ip()
            
            # Connect to machine
            real_machine = Machine(address=machine_address)
            real_machine.connect()
            
            # Connect to scale first (needed for state machine initialization)
            self.scale = Scale(port=scale_port)
            self.scale.connect()
            
            # Initialize the state machine with the real machine and scale
            # The state machine owns the machine and controls all access to it
            config_path = Path(state_machine_config)
            if not config_path.exists():
                raise FileNotFoundError(f"State machine config not found: {state_machine_config}")
            
            self.state_machine = MotionPlatformStateMachine.from_config_file(
                config_path,
                real_machine,
                scale=self.scale,
                feedrate=self._feedrate
            )
            
            # Initialize deck and dispensers in state machine
            self.state_machine.initialize_deck()
            self.state_machine.initialize_dispensers(
                num_piston_dispensers=self._num_piston_dispensers,
                num_pistons_per_dispenser=self._num_pistons_per_dispenser
            )

            # Create manipulator with state machine reference
            # Config will default to system_config.json
            self.manipulator = Manipulator(
                index=0,
                name="manipulator",
                state_machine=self.state_machine
            )

            # Ensure state machine context is set correctly for homing
            self.state_machine.update_context(
                active_tool_id=None,
                payload_state="empty"
            )
            
            # Home all axes (X, Y, Z, U) through state machine
            # This requires no tool picked up and no mold
            # Returns to global_ready position
            result = self.state_machine.validated_home_all()
            if not result.valid:
                raise RuntimeError(f"Failed to home all axes: {result.reason}")
            
            # Load the manipulator tool (this registers it but doesn't pick it up)
            self.machine_read_only.load_tool(self.manipulator)
            
            # Pick up the tool through state machine
            # This validates we're at a valid position, picks up the tool, and moves to global_ready
            result = self.state_machine.validated_pickup_tool(self.manipulator)
            if not result.valid:
                raise RuntimeError(f"Failed to pick up tool: {result.reason}")
            
            # Home the manipulator axis (V) through state machine
            # This requires no mold picked up
            result = self.state_machine.validated_home_manipulator(manipulator_axis='V')
            if not result.valid:
                raise RuntimeError(f"Failed to home manipulator: {result.reason}")
            
            self.connected = True
            return True
            
        except Exception as e:
            print(f"Connection error: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from all components"""
        if self.machine_read_only:
            self.machine_read_only.disconnect()
        if self.scale:
            self.scale.disconnect()
        self.connected = False
    
    def get_weight_stable(self) -> float:
        """Get current weight from scale when stabilized"""
        if self.scale and self.scale.is_connected:
            try:
                return self.scale.get_weight(stable=True)
            except:
                return 0.0
        return 0.0

    def get_weight_unstable(self) -> float:
        """Get instantaneous weight from scale"""
        if self.scale and self.scale.is_connected:
            try:
                return self.scale.get_weight(stable=False)
            except:
                return 0.0
        return 0.0
    
    def dispense_to_well(self, well_id: str, target_weight: float) -> bool:
        """Dispense powder to a specific well"""
        if not self.connected:
            return False
        try:
            if not self.manipulator:
                raise ToolStateError("Manipulator is not connected or provided.")
            
            if not self.scale or not self.scale.is_connected:
                raise ToolStateError("Scale is not connected or provided.")
            
            if not self.state_machine:
                raise RuntimeError("State machine not configured")
            
            self._move_to_well(well_id)
            self.manipulator.pick_mold(well_id)
            self._move_to_scale()
            self.manipulator.place_mold_on_scale()
            self._dispense_powder(target_weight)
            self.manipulator.pick_mold_from_scale()
            dispenser_index = -1
            for dispenser in self.piston_dispensers:
                if dispenser.num_pistons > 0:
                    dispenser_index = dispenser.index
                    break
            if dispenser_index == -1:
                raise ToolStateError("No dispenser with pistons found.")
            self._move_to_dispenser(dispenser_index)
            self.get_piston_from_dispenser(dispenser_index)
            self._move_to_well(well_id)
            self.manipulator.place_mold(well_id)
            return True
        except Exception as e:
            print(f"Dispensing error: {e}")
            return False

    def _move_to_dispenser(self, dispenser_index: int):
        """
        Move to the dispenser ready position for a specific dispenser.
        
        Validates and executes through MotionPlatformStateMachine.
        
        Args:
            dispenser_index: Index of the dispenser (0, 1, etc.)
        """
        if not self.connected or not self.piston_dispensers:
            return False
        
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        if dispenser_index >= len(self.piston_dispensers):
            raise ValueError(f"Invalid dispenser index: {dispenser_index}")
        
        try:
            piston_dispenser = self.piston_dispensers[dispenser_index]
            
            # Move to dispenser position through state machine
            result = self.state_machine.validated_move_to_dispenser(
                piston_dispenser=piston_dispenser
            )
            
            if not result.valid:
                raise RuntimeError(f"Failed to move to dispenser position: {result.reason}")
            
            return True
        except Exception as e:
            print(f"Error moving to dispenser: {e}")
            return False

    def get_piston_from_dispenser(self, dispenser_index: int):
        """
        Get the top piston from a specific dispenser.
        
        Validates and executes through MotionPlatformStateMachine.
        Requires being at the dispenser ready position for that dispenser.
        Call _move_to_dispenser() first to move to the correct position.
        
        Args:
            dispenser_index: Index of the dispenser (0, 1, etc.)
        """
        if not self.connected or not self.piston_dispensers:
            return False
        
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        if dispenser_index >= len(self.piston_dispensers):
            raise ValueError(f"Invalid dispenser index: {dispenser_index}")
        
        try:
            piston_dispenser = self.piston_dispensers[dispenser_index]
            
            # Retrieve piston through state machine
            result = self.state_machine.validated_retrieve_piston(
                piston_dispenser=piston_dispenser,
                manipulator_config=self.manipulator._get_config_dict()
            )
            
            if not result.valid:
                raise RuntimeError(f"Failed to retrieve piston: {result.reason}")
            
            return True
        except Exception as e:
            print(f"Getting piston from dispenser error: {e}")
            return False

    def _move_to_well(self, well_id: str):
        """
        Move to a specific well.
        
        Validates and executes through MotionPlatformStateMachine.
        Uses the well's ready_pos field to determine the state machine position.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        result = self.state_machine.validated_move_to_well(
            well_id=well_id
        )
        if not result.valid:
            raise RuntimeError(f"Move to well failed: {result.reason}")
        
        return True

    def _move_to_scale(self):
        """
        Move to the scale.
        
        Validates and executes through MotionPlatformStateMachine.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        if not self.scale:
            return False
        
        result = self.state_machine.validated_move_to_scale()
        
        if not result.valid:
            raise RuntimeError(f"Move to scale failed: {result.reason}")
        
        return True

    def _dispense_powder(self, target_weight: float):
        """
        Dispense powder to the scale.
        
        Validates and executes through MotionPlatformStateMachine.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        if not self.scale:
            return False
        
        result = self.state_machine.validated_dispense_powder(
            target_weight=target_weight
        )
        
        if not result.valid:
            raise RuntimeError(f"Dispense powder failed: {result.reason}")
        
        return True
