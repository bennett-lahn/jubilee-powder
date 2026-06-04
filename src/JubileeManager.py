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
            # Dispense powder to well 0
            success = manager.dispense_to_well("0", target_weight=50.0)
            
            # Clean up
            manager.disconnect()
"""

from __future__ import annotations

import time
import traceback
from typing import Callable, List, TYPE_CHECKING
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
                    manager.dispense_to_well("0", 50.0)
            finally:
                manager.disconnect()
    
    Note:
        - Always call `disconnect()` when done to properly release hardware resources
        - Check `connected` property before performing operations
        - Use `machine_read_only` only for queries, never for movements
    """
    
    # TODO: Improve soft fail for scale tare, add functionality for if a communication failure occurs when mold is on scale it is automatically returned
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
        self.scale: Scale | None = None
        self.manipulator: Manipulator | None = None
        self.hardness_tester_shore_a: HardnessTester | None = None
        self.hardness_tester_shore_d: HardnessTester | None = None
        self.state_machine: MotionPlatformStateMachine | None = None
        self.connected: bool = False
        self._num_piston_dispensers: int = num_piston_dispensers
        self._num_pistons_per_dispenser: int = num_pistons_per_dispenser
        self._feedrate: FeedRate = feedrate
        self.active_job_log: "JobLog" | None = None
        self.last_dispense_weight: float | None = None
        self.last_hardness_result: float | None = None
        self.last_hardness_error: str | None = None
        self.last_hardness_image_path: str | None = None
        self.last_error: str | None = None
        self._on_jam_callback: Callable | None = None
    
    @property
    def machine_read_only(self) -> Machine | None:
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
    def deck(self) -> Deck | None:
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

    # ── Jam detection helpers ─────────────────────────────────────────────────

    @property
    def jam_detected(self) -> bool:
        """True while the dispensing loop is blocked waiting for jam clearance."""
        if self.state_machine and self.state_machine._executor:
            return self.state_machine._executor.jam_detected
        return False

    def set_jam_callback(self, callback: Callable | None) -> None:
        """Register a callback invoked when a powder jam is detected.

        The callback is called from the dispensing thread immediately before
        it blocks.  It should be lightweight (e.g. set a flag in JobProgress).
        """
        self._on_jam_callback = callback
        if self.state_machine and self.state_machine._executor:
            self.state_machine._executor._on_jam_detected = callback

    def clear_jam(self) -> None:
        """Resume dispensing after the operator has cleared the blockage."""
        if self.state_machine and self.state_machine._executor:
            self.state_machine._executor.clear_jam()

    def connect(
        self,
        machine_address: str | None = None,
        scale_port: str | None = None,
        state_machine_config: str | None = None
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
        7. Leave tools parked; pick up occurs on-demand per operation
        
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
            RuntimeError: If homing fails.
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
            _t0 = time.monotonic()

            # Use config IP if no address provided
            if machine_address is None:
                machine_address = config.get_duet_ip()
            if scale_port is None:
                scale_port = config.get_scale_port()

            # Connect to machine
            real_machine = Machine(address=machine_address)
            real_machine.connect()
            print(f"[TIMING] Duet connect: {time.monotonic() - _t0:.2f}s")
            
            # Connect to scale first (needed for state machine initialization)
            _t1 = time.monotonic()
            self.scale = Scale(port=scale_port)
            self.scale.connect()
            print(f"[TIMING] Scale connect: {time.monotonic() - _t1:.2f}s")
            
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
                raise FileNotFoundError(f"State machine config not found: {config_path}")

            _t2 = time.monotonic()
            self.state_machine = MotionPlatformStateMachine.from_config_file(
                config_path,
                real_machine,
                scale=self.scale,
                feedrate=config.get_default_feedrate(),
            )
            
            # Initialize deck and dispensers in state machine
            deck_config_path = config.get_jubilee_api_config_dir()
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
                num_pistons_per_dispenser=self._num_pistons_per_dispenser
            )

            # Create manipulator with state machine reference
            # Config will default to system_config.json
            tool = config.system.tools.manipulator
            self.manipulator = Manipulator(
                index=tool.index,
                name=tool.name,
                state_machine=self.state_machine,
            )
            testers = config.system.hardness_testers
            self.hardness_tester_shore_a = HardnessTester.from_system_config(
                tester_mode="shore_a",
                cfg=testers.shore_a,
                state_machine=self.state_machine,
            )
            self.hardness_tester_shore_d = HardnessTester.from_system_config(
                tester_mode="shore_d",
                cfg=testers.shore_d,
                state_machine=self.state_machine,
            )
            print(f"[TIMING] State machine + tools init: {time.monotonic() - _t2:.2f}s")

            # Ensure state machine context is set correctly for homing
            # Set z_height_id to mold_transfer_safe which is the default height after homing
            self.state_machine.update_context(
                active_tool_id=None,
                payload_state="empty",
                z_height_id="mold_transfer_safe"
            )
            
            # Home all axes (X, Y, Z, U, V) through state machine
            # This requires no tool picked up and no mold
            # Returns to global_ready position at mold_transfer_safe z-height
            _t3 = time.monotonic()
            result = self.state_machine.validated_home_all()
            print(f"[TIMING] validated_home_all (incl. post-home move + M400): {time.monotonic() - _t3:.2f}s")
            if not result.valid:
                raise RuntimeError(f"Failed to home all axes: {result.reason}")
            
            # Load the manipulator tool (this registers it but doesn't pick it up)
            _t4 = time.monotonic()
            self.machine_read_only.load_tool(self.manipulator)
            # self.machine_read_only.load_tool(self.hardness_tester_shore_a)
            # self.machine_read_only.load_tool(self.hardness_tester_shore_d)
            print(f"[TIMING] load_tool: {time.monotonic() - _t4:.2f}s")
            print(f"[TIMING] Total connect: {time.monotonic() - _t0:.2f}s")
            
            self.connected = True
            return True
            
        except Exception as e:
            self.last_error = str(e)
            print(f"Connection error: {e}")
            traceback.print_exc()
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
            - Parks the active tool before releasing the machine connection
            - Turns off a mounted hardness tester before parking it
            - Sets `connected` property to False
        """
        self._disconnect_cleanup()
        if self.machine_read_only:
            self.machine_read_only.disconnect()
        if self.scale:
            self.scale.disconnect()
        self.connected = False
    
    def get_weight_stable(self) -> float | None:
        """
        Get current weight from scale, waiting for stability.
        
        Reads the scale weight, waiting for the reading to stabilize before
        returning. This is the recommended method for measurements that will
        be recorded or used for decisions.
        
        Returns:
            Weight in grams, or ``None`` if the scale is not connected.
            Scale communication errors propagate to the caller.
        
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
            - Returns ``None`` when no scale is connected (distinct from zero weight)
        
        See Also:
            get_weight_unstable: For real-time weight monitoring without waiting
        """
        if self.scale and self.scale.is_connected:
            return self.scale.get_weight(stable=True)
        return None

    def get_weight_unstable(self) -> float | None:
        """
        Get instantaneous weight from scale without waiting for stability.
        
        Reads the current scale weight immediately, without waiting for the
        reading to stabilize. Useful for real-time monitoring but not recommended
        for recorded measurements.
        
        Returns:
            Current weight in grams, or ``None`` if the scale is not connected.
            Scale communication errors propagate to the caller.
        
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
            - Returns ``None`` when no scale is connected (distinct from zero weight)
        
        See Also:
            get_weight_stable: For accurate measurements after stabilization
        """
        if self.scale and self.scale.is_connected:
            return self.scale.get_weight(stable=False)
        return None

    def _hardness_tester_for_tool_id(self, tool_id: str | None) -> HardnessTester | None:
        """Return the configured hardness tester whose name matches tool_id."""
        if not tool_id:
            return None
        if self.hardness_tester_shore_a and tool_id == self.hardness_tester_shore_a.name:
            return self.hardness_tester_shore_a
        if self.hardness_tester_shore_d and tool_id == self.hardness_tester_shore_d.name:
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
        """Park the currently mounted tool if one is active."""
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
        """Pick up the requested tool without assuming current tool state."""
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        if not tool:
            raise ToolStateError("Requested tool is not configured")

        if self.state_machine.context.position_id != "global_ready":
            self.move_to_global_ready()

        pickup_result = self.state_machine.validated_pickup_tool(tool)
        if not pickup_result.valid:
            raise RuntimeError(f"Failed to pick up tool '{tool.name}': {pickup_result.reason}")

        return True

    def ensure_tool_active(self, required_tool) -> bool:
        """
        Ensure the required tool is mounted.

        If another tool is currently active, it is parked first. If no tool is
        active, the required tool is picked up directly.
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
            well_id: Identifier for the target well/mold slot using numerical indexing.
                Must match an entry in the deck configuration (e.g., "0", "1", "2").
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
                # Dispense 50g of powder to mold 0
                success = manager.dispense_to_well("0", target_weight=50.0)
                
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
            self.manipulator.place_mold_on_scale()
            self.fill_powder(target_weight)
            self.manipulator.pick_mold_from_scale()
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
        image_save_path=None,
    ) -> bool:
        """
        Select a Shore tester and delegate sample testing to it.

        ``mode`` must be ``shore_a`` or ``shore_d`` (the pass being measured).
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

            selected_tester = self._resolve_hardness_tester(mode)
            self.ensure_tool_active(selected_tester)
            measurement = selected_tester.test_sample(
                tray_index, sample_index, self.state_machine, image_save_path=image_save_path
            )
            if isinstance(measurement, dict):
                self.last_hardness_result = measurement.get("result")
                self.last_hardness_error = measurement.get("sample_error")
                self.last_hardness_image_path = measurement.get("image_path")
            else:
                self.last_hardness_result = None
                self.last_hardness_error = "Hardness tester did not return measurement metadata."

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
        """Select a Shore tester and delegate power-on to it."""
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
        """Select a Shore tester and delegate power-off to it."""
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
        """Select a Shore tester and delegate zeroing to it."""
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
        """
        Move to the ready position of the next available piston dispenser.
        
        The state machine selects the first dispenser that still has pistons and
        moves to its ready position. All dispenser tracking and selection is
        handled by the state machine.
        
        Returns:
            True if movement succeeded, False if not connected or movement failed.
        
        Raises:
            RuntimeError: If state machine is not configured or movement validation fails.
        
        Note:
            - Typically called by `dispense_to_well()`
            - Does not retrieve the piston, only positions for retrieval
        """
        if not self.connected:
            return False
        
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        try:
            result = self.state_machine.validated_move_to_dispenser()
            
            if not result.valid:
                raise RuntimeError(f"Failed to move to dispenser position: {result.reason}")
            
            return True
        except Exception as e:
            print(f"Error moving to dispenser: {e}")
            return False

    def get_piston_from_dispenser(self) -> bool:
        """
        Retrieve a piston from the current dispenser position.
        
        The state machine derives which dispenser to use from the current position
        and executes the retrieval. All dispenser tracking and validation is
        handled by the state machine.
        
        Returns:
            True if piston was successfully retrieved, False if not connected
            or retrieval failed.
        
        Raises:
            RuntimeError: If state machine is not configured or retrieval fails.
        
        Example:
            ```python
            # Manually retrieve piston (typically done by dispense_to_well)
            if manager.move_to_dispenser():
                if manager.get_piston_from_dispenser():
                    print("Piston retrieved successfully")
            ```
        
        Note:
            - Must already be at a dispenser_ready position (call `move_to_dispenser()` first)
            - Requires mold to be held by manipulator
            - State machine decrements piston count on success
        
        Warning:
            Calling this method without first moving to the dispenser position
            will fail validation. Always call `move_to_dispenser()` first.
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
        """
        Move to a specific mold slot position.
        
        Moves to the position where the manipulator can pick up or place a mold
        in the specified well. The target position is determined by the well's
        configuration in the deck layout.
        
        Args:
            well_id: Identifier for the target well using numerical indexing (e.g., "0", "1", "2").
                Must exist in the deck configuration's labware definition.
        
        Returns:
            True if movement succeeded.
        
        Raises:
            RuntimeError: If state machine is not configured or movement validation
                fails. Validation failure reasons include wrong position, wrong tool,
                or invalid payload state.
            KeyError: If well_id is not found in deck configuration.
        
        Note:
            - Typically called by `dispense_to_well()`
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

    def move_to_global_ready(self) -> bool:
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        result = self.state_machine.validated_move_to_global_ready()
        if not result.valid:
            raise RuntimeError(f"Move to mold slot failed: {result.reason}")
        return True

    def move_to_scale(self) -> bool:
        """
        Move to the scale ready position.
        
        Moves the manipulator to the position where it can place or pick up molds
        on the scale. Movement is validated through the state machine.
        
        Returns:
            True if movement succeeded, False if scale is not configured.
        
        Raises:
            RuntimeError: If state machine is not configured or movement validation
                fails. Common failure reasons include wrong tool active, invalid
                payload state, or unable to transition from current position.
        
        Note:
            - Typically called by `dispense_to_well()`
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

    def set_dispenser_pistons(self, index: int, num_pistons: int) -> bool:
        """
        Set the piston count for a specific dispenser.
        
        Allows reloading a dispenser while the machine remains connected
        and idle. Delegates to the state machine, which owns all dispenser state.
        
        Args:
            index: Zero-based dispenser index.
            num_pistons: New piston count (must be >= 0).
        
        Returns:
            True on success, False if the state machine is not initialized or
            the index is out of range.
        
        Example:
            ```python
            # Reload dispenser 0 with 10 pistons
            manager.set_dispenser_pistons(0, 10)
            ```
        """
        if not self.state_machine:
            return False
        return self.state_machine.set_dispenser_pistons(index, num_pistons)

    def abort(self) -> None:
        """
        Send an emergency-stop (M112) to the Jubilee controller.

        This is the only method in JubileeManager that intentionally bypasses
        the MotionPlatformStateMachine.  This bypass is safe because:

        - M112 is a firmware-level emergency stop that immediately halts all
          motion regardless of software state.  There is no higher-priority
          fail-safe mechanism that the state machine could add on top of it.

        - After M112 the Duet firmware requires a full reset before accepting
          any new motion commands.  The machine is therefore
          inoperable until the operator intervenes, so the invariants of
          MotionPlatformStateMachine (consistent position tracking, validated
          state transitions) become irrelevant.

        The method is a best-effort call: if no machine connection is available
        (e.g. abort is called before connect() succeeds) it is silently ignored.
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
        """
        Fill mold with powder to target weight.
        
        Dispenses powder into a mold using the trickler mechanism, monitoring
        the scale until the target weight is reached. The mold must already be
        placed on the scale.
        
        Args:
            target_weight: Target weight of powder to dispense, in grams.
        
        Returns:
            True if filling succeeded, False if scale is not configured.
        
        Raises:
            RuntimeError: If state machine is not configured or fill operation
                validation fails. Validation ensures mold is on scale and system
                is in correct state for powder dispensing.
        
        Note:
            - Typically called by `dispense_to_well()`
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

        # Keep the executor's callback in sync with whatever the hardware
        # manager registered via set_jam_callback().
        if self.state_machine._executor is not None:
            self.state_machine._executor._on_jam_detected = self._on_jam_callback

        result = self.state_machine.validated_fill_powder(
            target_weight=target_weight
        )
        
        if not result.valid:
            raise RuntimeError(f"Fill mold with powder failed: {result.reason}")
        
        self.last_dispense_weight = self.state_machine.last_fill_weight
        return True
