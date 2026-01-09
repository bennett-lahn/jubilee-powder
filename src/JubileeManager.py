"""
JubileeManager - Centralized management of Jubilee machine and related components.

This module provides the JubileeManager class for coordinating complex powder dispensing
tasks that require interacting with the Jubilee machine, scale, dispensers, and manipulator
toolhead. It provides high-level abstractions for common operations.

The JubileeManager uses a MotionPlatformStateMachine to validate and execute all
movements, ensuring that operations cannot bypass safety checks.

Example:
    Basic usage of JubileeManager for powder dispensing::
    
        from src.JubileeManager import JubileeManager
        
        # Create manager
        manager = JubileeManager(
            num_piston_dispensers=2,
            num_pistons_per_dispenser=10
        )
        
        # Connect to hardware
        if manager.connect(machine_address="192.168.1.100"):
            # Dispense powder to well
            success = manager.dispense_to_well("A1", target_weight=50.0)
            
            # Clean up
            manager.disconnect()
"""

from typing import Optional, List
from pathlib import Path

# Import Jubilee components
from science_jubilee.Machine import Machine
from science_jubilee.decks.Deck import Deck
from src.Scale import Scale
from src.PistonDispenser import PistonDispenser
from src.Manipulator import Manipulator, ToolStateError
from src.MotionPlatformStateMachine import MotionPlatformStateMachine
from jubilee_api_config.constants import FeedRate
from src.ConfigLoader import config

class JubileeManager:
    """
    High-level manager for Jubilee powder dispensing operations.
    
    JubileeManager provides a simplified interface for controlling the Jubilee for powder dispensing tasks. 
    It coordinates multiple hardware components (machine, scale, dispensers, manipulator) and ensures all operations
    are safe through state machine validation.
    
    All movements are validated through the MotionPlatformStateMachine, which is owned
    by this manager and cannot be bypassed. This ensures safety and prevents invalid
    state transitions.
    
    Attributes:
        scale: Connected scale instance for weight measurements, or None if not connected.
        manipulator: Manipulator tool instance for mold handling, or None if not initialized.
        state_machine: Internal state machine for movement validation, or None before connection.
        connected: Boolean indicating whether hardware is connected and ready.
        
    Example:
        Basic usage pattern::
        
            manager = JubileeManager(num_piston_dispensers=2, num_pistons_per_dispenser=10)
            
            try:
                if manager.connect():
                    weight = manager.get_weight_stable()
                    manager.dispense_to_well("A1", 50.0)
            finally:
                manager.disconnect()
    
    Note:
        - Always call `disconnect()` when done to properly release hardware resources
        - Check `connected` property before performing operations
        - Use `machine_read_only` only for queries, never for movements
    """
    
    # TODO: make dispensers configurable from UI
    def __init__(
        self, 
        num_piston_dispensers: int = 0, 
        num_pistons_per_dispenser: int = 0, 
        feedrate: FeedRate = FeedRate.MEDIUM
    ) -> None:
        """
        Initialize the JubileeManager.
        
        Creates a new manager instance with specified dispenser configuration.
        Does not connect to hardware - call `connect()` to establish connections.
        
        Args:
            num_piston_dispensers: Number of piston dispenser units to initialize.
                Each dispenser can hold multiple pistons. Default is 0.
            num_pistons_per_dispenser: Initial number of pistons in each dispenser.
                Used to track available pistons. Default is 0.
            feedrate: Default movement speed for operations. Options are SLOW, MEDIUM,
                or FAST from the FeedRate enum. Default is MEDIUM.
        
        Example:
            ```python
            # Create manager with 2 dispensers, 10 pistons each, medium speed
            manager = JubileeManager(
                num_piston_dispensers=2,
                num_pistons_per_dispenser=10,
                feedrate=FeedRate.MEDIUM
            )
            ```
        
        Note:
            - No hardware connection is established during initialization
            - Dispenser counts can be zero if pistons are not needed
            - Feedrate affects all subsequent movements after connection
        """
        self.scale: Optional[Scale] = None
        self.manipulator: Optional[Manipulator] = None
        self.state_machine: Optional[MotionPlatformStateMachine] = None
        self.connected: bool = False
        self._num_piston_dispensers: int = num_piston_dispensers
        self._num_pistons_per_dispenser: int = num_pistons_per_dispenser
        self._feedrate: FeedRate = feedrate
    
    @property
    def machine_read_only(self) -> Optional[Machine]:
        """
        Read-only access to the underlying Jubilee Machine instance.
        
        Provides access to the Machine object for read operations only (queries,
        status checks, position reads). While it's technically possible to perform
        write operations through this property, doing so bypasses the state machine 
        safety guarantee and should be avoided.
        
        Returns:
            The Machine instance if connected, None otherwise.
        
        Warning:
            This property is named "read_only" as a strong hint that it should ONLY
            be used for read operations. Performing movements or state changes through
            this property bypasses the state machine safety guarantee and can lead to:
            
            - Collisions with labware
            - Invalid state transitions
            - Unsafe operations
            - Loss of state tracking
        
        Example:
            ```python
            # GOOD: Query current position
            if manager.machine_read_only:
                pos = manager.machine_read_only.get_position()
                print(f"Current position: {pos}")
            
            # BAD: Perform movements (bypasses validation!)
            manager.machine_read_only.move_to(x=100, y=100)  # Don't do this!
            ```
        
        Note:
            Always use JubileeManager's high-level methods or the state machine's
            validated methods for any operations that change machine state.
        """
        if self.state_machine:
            return self.state_machine.machine
        return None
    
    @property
    def deck(self) -> Optional[Deck]:
        """
        Access to the deck configuration and labware layout.
        
        Provides access to the Deck object which contains information about
        labware positions, well plates, and deck layout.
        
        Returns:
            The Deck instance if state machine is initialized, None otherwise.
        
        Example:
            ```python
            if manager.deck:
                labware = manager.deck.get_labware()
                print(f"Available labware: {list(labware.keys())}")
            ```
        """
        if self.state_machine:
            return self.state_machine.context.deck
        return None
    
    @property
    def piston_dispensers(self) -> List[PistonDispenser]:
        """
        Access to all configured piston dispensers.
        
        Provides access to the list of PistonDispenser instances managed by
        the state machine. Each dispenser tracks its piston count and position.
        
        Returns:
            List of PistonDispenser instances. Empty list if none configured
            or state machine not initialized.
        
        Example:
            ```python
            # Check available pistons across all dispensers
            for dispenser in manager.piston_dispensers:
                print(f"Dispenser {dispenser.index}: {dispenser.num_pistons} pistons")
            
            # Find first dispenser with available pistons
            available = next(
                (d for d in manager.piston_dispensers if d.num_pistons > 0),
                None
            )
            ```
        """
        if self.state_machine:
            return self.state_machine.context.piston_dispensers
        return []
        
    def connect(
        self,
        machine_address: Optional[str] = None,
        scale_port: str = "/dev/ttyUSB0",
        state_machine_config: Optional[str] = None
    ) -> bool:
        """
        Connect to all hardware and initialize the system.
        
        Establishes connections to the Jubilee machine controller and scale,
        initializes the state machine with configuration, sets up dispensers,
        and performs homing operations to establish a known state.
        
        This method performs the following sequence:
        
        1. Connect to Jubilee machine (Duet controller)
        2. Connect to precision scale
        3. Initialize state machine with configuration
        4. Initialize deck layout and piston dispensers
        5. Create and configure manipulator tool
        6. Home all machine axes (X, Y, Z, U)
        7. Pick up manipulator tool
        8. Home manipulator axis (V)
        
        Args:
            machine_address: IP address of the Jubilee's Duet controller. If None,
                uses the IP address from system configuration file. Examples:
                "192.168.1.100", "10.0.0.50".
            scale_port: Serial port path for scale connection. Common values:
                Linux: "/dev/ttyUSB0", "/dev/ttyACM0"
                Windows: "COM3", "COM4"
                macOS: "/dev/tty.usbserial-*"
            state_machine_config: Path to JSON file defining state machine positions
                and transitions. Relative or absolute path accepted.
        
        Returns:
            True if all connections and initializations succeeded, False if any
            step failed. Check the `connected` property after calling.
        
        Raises:
            FileNotFoundError: If state_machine_config file does not exist.
            RuntimeError: If homing, tool pickup, or manipulator homing fails.
            ConnectionError: If unable to connect to machine or scale.
        
        Example:
            ```python
            manager = JubileeManager(num_piston_dispensers=2, num_pistons_per_dispenser=10)
            
            # Connect with explicit IP
            if manager.connect(machine_address="192.168.1.100", scale_port="/dev/ttyUSB0"):
                print("Connected successfully!")
            else:
                print("Connection failed - check hardware and configuration")
            
            # Connect using config file IP
            if manager.connect():  # Uses IP from system_config.json
                print("Connected using configured IP")
            ```
        
        Note:
            - This operation can take 30-60 seconds due to homing
            - All axes must be clear of obstacles before homing
            - Ensure no tool is already picked up before calling
            - Connection state is stored in `self.connected` property
            - On failure, partial connections are not cleaned up automatically
        
        Warning:
            If connection fails partway through (e.g., after machine connects but
            before homing completes), you may need to manually reset the hardware
            before attempting to connect again.
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
            if state_machine_config is None:
                # Default to project root / jubilee_api_config / motion_platform_positions.json
                project_root = Path(__file__).parent.parent
                config_path = project_root / "jubilee_api_config" / "motion_platform_positions.json"
            else:
                config_path = Path(state_machine_config)
                # If relative path, resolve relative to project root
                if not config_path.is_absolute():
                    project_root = Path(__file__).parent.parent
                    config_path = project_root / config_path
            if not config_path.exists():
                raise FileNotFoundError(f"State machine config not found: {config_path}")
            
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
    
    def disconnect(self) -> None:
        """
        Disconnect from all hardware components and release resources.
        
        Cleanly disconnects from the Jubilee machine and scale, releasing
        any held resources. This should always be called when done using
        the manager.
        
        Example:
            ```python
            manager = JubileeManager()
            try:
                manager.connect()
                # ... perform operations ...
            finally:
                manager.disconnect()  # Always disconnect
            ```
        
        Note:
            - Safe to call multiple times
            - Safe to call even if not fully connected
            - Does not raise exceptions on disconnection errors
            - Sets `connected` property to False
        """
        if self.machine_read_only:
            self.machine_read_only.disconnect()
        if self.scale:
            self.scale.disconnect()
        self.connected = False
    
    def get_weight_stable(self) -> float:
        """
        Get current weight from scale, waiting for stability.
        
        Reads the scale weight, waiting for the reading to stabilize before
        returning. This is the recommended method for measurements that will
        be recorded or used for decisions.
        
        Returns:
            Weight in grams. Returns 0.0 if scale is not connected or on error.
        
        Example:
            ```python
            # Get stable reading for recording
            weight = manager.get_weight_stable()
            print(f"Stable weight: {weight:.3f}g")
            
            # Use in conditional
            if manager.get_weight_stable() > 50.0:
                print("Target weight exceeded")
            ```
        
        Note:
            - Waits for scale to report stable reading (may take 1-3 seconds)
            - More accurate than `get_weight_unstable()`
            - Returns 0.0 on error rather than raising exceptions
            - Check `scale.is_connected` if you need to distinguish no scale from zero weight
        
        See Also:
            get_weight_unstable: For real-time weight monitoring without waiting
        """
        if self.scale and self.scale.is_connected:
            try:
                return self.scale.get_weight(stable=True)
            except:
                return 0.0
        return 0.0

    def get_weight_unstable(self) -> float:
        """
        Get instantaneous weight from scale without waiting for stability.
        
        Reads the current scale weight immediately, without waiting for the
        reading to stabilize. Useful for real-time monitoring but not recommended
        for recorded measurements.
        
        Returns:
            Current weight in grams. Returns 0.0 if scale is not connected or on error.
        
        Example:
            ```python
            # Monitor weight in real-time during filling
            while filling:
                current = manager.get_weight_unstable()
                print(f"Current: {current:.2f}g", end='\r')
                time.sleep(0.1)
            
            # Get final stable reading
            final = manager.get_weight_stable()
            ```
        
        Note:
            - Returns immediately without waiting
            - Reading may still be changing (unstable)
            - Not suitable for decisions or permanent records
            - Use `get_weight_stable()` for measurements you'll record
            - Returns 0.0 on error rather than raising exceptions
        
        See Also:
            get_weight_stable: For accurate measurements after stabilization
        """
        if self.scale and self.scale.is_connected:
            try:
                return self.scale.get_weight(stable=False)
            except:
                return 0.0
        return 0.0
    
    def dispense_to_well(self, well_id: str, target_weight: float) -> bool:
        """
        Perform complete powder dispense operation to a well.
        
        This is the primary high-level operation for dispensing powder. It performs
        a complete workflow including picking up the mold, filling with powder to
        target weight, retrieving a piston, and returning the mold to its slot.
        
        The operation sequence is:
        
        1. Move to mold slot position
        2. Pick up empty mold from slot
        3. Move to scale
        4. Place mold on scale
        5. Fill with powder to target weight
        6. Pick up filled mold from scale
        7. Move to piston dispenser
        8. Retrieve piston from dispenser
        9. Move back to mold slot
        10. Place mold (now with powder and piston) back in slot
        
        Args:
            well_id: Identifier for the target well/mold slot. Must match an entry
                in the deck configuration (e.g., "A1", "B2", "C3").
            target_weight: Target weight of powder to dispense, in grams. The system
                will fill until this weight is reached (within tolerance).
        
        Returns:
            True if the entire operation completed successfully, False if any step
            failed or if not connected.
        
        Raises:
            ToolStateError: If manipulator or scale is not available.
            RuntimeError: If state machine is not configured.
            ValueError: If well_id is not found in deck configuration.
        
        Example:
            ```python
            manager = JubileeManager(num_piston_dispensers=2, num_pistons_per_dispenser=10)
            
            if manager.connect():
                # Dispense 50g of powder to well A1
                success = manager.dispense_to_well("A1", target_weight=50.0)
                
                if success:
                    print("Dispense completed successfully!")
                    weight = manager.get_weight_stable()
                    print(f"Final weight: {weight}g")
                else:
                    print("Dispense failed - check logs for details")
                
                manager.disconnect()
            ```
        
        Note:
            - Requires at least one dispenser with available pistons
            - All movements are validated through state machine
            - Operation can take 2-5 minutes depending on target weight
            - If operation fails partway through, system may be in intermediate state
            - Check return value before assuming success
        
        Warning:
            If the operation fails after picking up the mold but before returning it,
            the mold may be left at an intermediate position. Manual intervention
            may be required to return to a safe state.
        """
        if not self.connected:
            return False
        try:
            if not self.manipulator:
                raise ToolStateError("Manipulator is not connected or provided.")
            
            if not self.scale or not self.scale.is_connected:
                raise ToolStateError("Scale is not connected or provided.")
            
            if not self.state_machine:
                raise RuntimeError("State machine not configured")
            
            self._move_to_mold_slot(well_id)
            self.manipulator.pick_mold(well_id)
            self._move_to_scale()
            self.manipulator.place_mold_on_scale()
            self._fill_powder(target_weight)
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
            self._move_to_mold_slot(well_id)
            self.manipulator.place_mold(well_id)
            return True
        except Exception as e:
            print(f"Error filling mold: {e}")
            return False

    def _move_to_dispenser(self, dispenser_index: int) -> bool:
        """
        Move to the ready position for a specific piston dispenser.
        
        Internal method that moves the manipulator to the position where it can
        retrieve a piston from the specified dispenser. Movement is validated
        through the state machine.
        
        Args:
            dispenser_index: Index of the target dispenser (0-based). Must be less
                than the number of configured dispensers.
        
        Returns:
            True if movement succeeded, False if not connected, no dispensers, or
            movement validation failed.
        
        Raises:
            RuntimeError: If state machine is not configured or movement validation fails.
            ValueError: If dispenser_index is out of range.
        
        Note:
            - This is an internal method; typically called by `dispense_to_well()`
            - Movement is validated against current state (tool, payload, position)
            - Does not retrieve the piston, only positions for retrieval
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

    def get_piston_from_dispenser(self, dispenser_index: int) -> bool:
        """
        Retrieve the top piston from a specific dispenser.
        
        Retrieves a piston from the specified dispenser and places it into the
        mold currently held by the manipulator. The operation is validated through
        the state machine to ensure safety.
        
        Args:
            dispenser_index: Index of the dispenser to retrieve from (0-based).
                Must be less than the number of configured dispensers.
        
        Returns:
            True if piston was successfully retrieved, False if not connected,
            no dispensers available, or retrieval failed.
        
        Raises:
            RuntimeError: If state machine is not configured or retrieval validation fails.
            ValueError: If dispenser_index is out of range.
        
        Example:
            ```python
            # Manually retrieve piston (typically done by dispense_to_well)
            if manager._move_to_dispenser(0):
                if manager.get_piston_from_dispenser(0):
                    print("Piston retrieved successfully")
            ```
        
        Note:
            - Must already be at the dispenser ready position (call `_move_to_dispenser()` first)
            - Requires mold to be held by manipulator
            - Automatically decrements piston count in the dispenser
            - Validation ensures proper state before and after retrieval
        
        Warning:
            Calling this method without first moving to the dispenser position
            will fail validation. Always call `_move_to_dispenser()` first.
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

    def _move_to_mold_slot(self, well_id: str) -> bool:
        """
        Move to a specific mold slot position.
        
        Internal method that moves to the position where the manipulator can
        pick up or place a mold in the specified well. The target position is
        determined by the well's configuration in the deck layout.
        
        Args:
            well_id: Identifier for the target well (e.g., "A1", "B2"). Must exist
                in the deck configuration's labware definition.
        
        Returns:
            True if movement succeeded.
        
        Raises:
            RuntimeError: If state machine is not configured or movement validation
                fails. Validation failure reasons include wrong position, wrong tool,
                or invalid payload state.
            KeyError: If well_id is not found in deck configuration.
        
        Note:
            - This is an internal method; typically called by `dispense_to_well()`
            - Uses the well's `ready_pos` field from deck configuration
            - Movement is validated through state machine
            - Does not pick up or place the mold, only positions for access
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        result = self.state_machine.validated_move_to_mold_slot(
            well_id=well_id
        )
        if not result.valid:
            raise RuntimeError(f"Move to mold slot failed: {result.reason}")
        
        return True

    def _move_to_scale(self) -> bool:
        """
        Move to the scale ready position.
        
        Internal method that moves the manipulator to the position where it can
        place or pick up molds on the scale. Movement is validated through the
        state machine.
        
        Returns:
            True if movement succeeded, False if scale is not configured.
        
        Raises:
            RuntimeError: If state machine is not configured or movement validation
                fails. Common failure reasons include wrong tool active, invalid
                payload state, or unable to transition from current position.
        
        Note:
            - This is an internal method; typically called by `dispense_to_well()`
            - Moves to scale_ready position defined in state machine config
            - Does not place or pick up mold, only positions for access
            - Movement is validated against current state
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        if not self.scale:
            return False
        
        result = self.state_machine.validated_move_to_scale()
        
        if not result.valid:
            raise RuntimeError(f"Move to scale failed: {result.reason}")
        
        return True

    def _fill_powder(self, target_weight: float) -> bool:
        """
        Fill mold with powder to target weight.
        
        Internal method that dispenses powder into a mold using the trickler
        mechanism, monitoring the scale until the target weight is reached.
        The mold must already be placed on the scale.
        
        Args:
            target_weight: Target weight of powder to dispense, in grams.
        
        Returns:
            True if filling succeeded, False if scale is not configured.
        
        Raises:
            RuntimeError: If state machine is not configured or fill operation
                validation fails. Validation ensures mold is on scale and system
                is in correct state for powder dispensing.
        
        Note:
            - This is an internal method; typically called by `dispense_to_well()`
            - Mold must already be on the scale before calling
            - Operation continues until target weight is reached (within tolerance)
            - Duration depends on target weight and trickler speed (typically 1-3 min)
            - Continuously monitors scale during filling
        
        Warning:
            Calling this method without a mold on the scale will result in powder
            being dispensed directly onto the scale, which is incorrect operation.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        if not self.scale:
            return False
        
        result = self.state_machine.validated_fill_powder(
            target_weight=target_weight
        )
        
        if not result.valid:
            raise RuntimeError(f"Fill mold with powder failed: {result.reason}")
        
        return True
