"""
Physical test for piston retrieval workflow using MotionPlatformStateMachine.

Prerequisites (user must do before running this test):
1. Home jubilee (all axes)
2. Move to global_ready position
3. Pick up manipulator tool
4. Pick up a mold (without top piston)

This test performs:
1. Move to dispenser 0 ready position
2. Retrieve piston from dispenser 0
3. Return to global ready

The test uses MotionPlatformStateMachine as the top-level module and simulates
the prerequisite state (carrying a mold) by manually setting the context.
"""

from pathlib import Path
from science_jubilee.Machine import Machine
from MotionPlatformStateMachine import MotionPlatformStateMachine
from Manipulator import Manipulator
from MovementExecutor import FeedRate
from ConfigLoader import config
from trickler_labware import Mold


class TestError(Exception):
    """Exception raised when test encounters an error"""


def print_step(step_num: int, description: str):
    """Print a formatted step message"""
    print(f"\n{'='*60}")
    print(f"STEP {step_num}: {description}")
    print(f"{'='*60}")


def print_success(message: str):
    """Print a success message"""
    print(f"✓ {message}")


def print_error(message: str):
    """Print an error message"""
    print(f"✗ ERROR: {message}")


def move_to_global_ready(state_machine) -> tuple:
    """Helper function to move to global_ready position"""
    # Get global_ready position from registry
    global_ready = state_machine._registry.get("global_ready")
    if not global_ready or not global_ready.coordinates:
        raise TestError("global_ready position not found or has no coordinates")
    
    coords = global_ready.coordinates
    
    # Resolve z coordinate if needed
    ready_z = None
    if coords.z == "USE_Z_HEIGHT_POLICY":
        if not state_machine.context.z_height_id:
            # Use dispenser_safe for dispenser operations
            state_machine.context.z_height_id = "mold_transfer_safe"
        z_heights = state_machine._registry.z_heights
        if state_machine.context.z_height_id in z_heights:
            z_config = z_heights[state_machine.context.z_height_id]
            if isinstance(z_config, dict):
                ready_z = z_config.get("z_coordinate")
    elif coords.z is not None:
        ready_z = coords.z
    
    result = state_machine._validate_and_execute_move(
        target_position_id="global_ready",
        execution_func=state_machine._executor.execute_move_to_position,
        x=coords.x,
        y=coords.y,
        z=ready_z,
        v=coords.v
    )
    return result.valid, result.reason if not result.valid else None


def wait_for_user_confirmation(action: str):
    """Wait for user to press Enter before proceeding with movement"""
    print(f"\n⚠️  READY TO: {action}")
    print("   Press Enter to proceed or Ctrl+C to abort...")
    try:
        input()
    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        raise


def main():
    """Main test function"""
    
    # Configuration
    MACHINE_ADDRESS = config.get_duet_ip()  # Get from config
    STATE_MACHINE_CONFIG = "./jubilee_api_config/motion_platform_positions.json"
    
    print("\n" + "="*60)
    print("PISTON RETRIEVAL TEST")
    print("="*60)
    print("\nThis test assumes the following prerequisites have been met:")
    print("1. Jubilee has been homed (all axes)")
    print("2. Machine is at global_ready position")
    print("3. Manipulator tool has been picked up")
    print("4. A mold (without top piston) has been picked up by the manipulator")
    print("\nPress Enter to continue or Ctrl+C to abort...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\nTest aborted by user.")
        return
    
    # Initialize components
    machine = None
    state_machine = None
    manipulator = None
    
    try:
        # ====================================================================
        # INITIALIZATION
        # ====================================================================
        print_step(0, "INITIALIZATION")
        
        # Connect to Jubilee machine
        print(f"Connecting to Jubilee at {MACHINE_ADDRESS}...")
        machine = Machine(address=MACHINE_ADDRESS)
        machine.connect()
        print_success("Connected to Jubilee")
        
        # Initialize state machine
        print("Initializing motion platform state machine...")
        config_path = Path(STATE_MACHINE_CONFIG)
        if not config_path.exists():
            raise TestError(f"State machine config not found: {STATE_MACHINE_CONFIG}")
        
        state_machine = MotionPlatformStateMachine.from_config_file(
            config_path,
            machine,
            scale=None,  # Scale not needed for piston retrieval
            feedrate=FeedRate.MEDIUM
        )
        print_success("State machine initialized")
        
        # Initialize dispensers (required for piston operations)
        print("Initializing dispensers...")
        NUM_PISTON_DISPENSERS = 1  # At least dispenser 0
        NUM_PISTONS_PER_DISPENSER = 10  # Adjust as needed
        state_machine.initialize_dispensers(
            num_piston_dispensers=NUM_PISTON_DISPENSERS,
            num_pistons_per_dispenser=NUM_PISTONS_PER_DISPENSER
        )
        print_success("Dispensers initialized")
        print(f"  Dispenser 0 has {NUM_PISTONS_PER_DISPENSER} pistons")
        
        # Create manipulator
        print("Initializing manipulator...")
        manipulator = Manipulator(
            index=0,
            name="manipulator",
            state_machine=state_machine
        )
        print_success("Manipulator initialized")
        
        # Create a mock mold to simulate carrying one
        print("Creating mock mold (simulating picked up mold)...")
        mock_mold = Mold(
            name="test_mold",
            depth=10.0,
            totalLiquidVolume=1000.0,
            shape="cylindrical",
            x=0.0,
            y=0.0,
            z=0.0,
            valid=True,
            has_top_piston=False,  # No piston yet
            current_weight=0.0,
            target_weight=0.0,
            max_weight=None,
            ready_pos="mold_ready_10"  # Use a valid position
        )
        print_success("Mock mold created")
        
        # Update state machine context to reflect prerequisites
        print("\nSetting initial context (assuming prerequisites completed)...")
        state_machine.context.position_id = "global_ready"
        state_machine.update_context(
            z_height_id="mold_transfer_safe",  # Required for dispenser operations
            active_tool_id="manipulator",
            payload_state="mold_without_top_piston"  # Critical: must be mold_without_top_piston
        )
        # Manually set current_well to simulate carrying a mold
        state_machine.context.current_well = mock_mold
        state_machine.context.mold_on_scale = False  # Not on scale
        
        print_success("Context updated:")
        print(f"  Position: {state_machine.context.position_id}")
        print(f"  Z-height: {state_machine.context.z_height_id}")
        print(f"  Active tool: {state_machine.context.active_tool_id}")
        print(f"  Payload state: {state_machine.context.payload_state}")
        print(f"  Carrying mold: {mock_mold.name}")
        print(f"  Mold has piston: {mock_mold.has_top_piston}")
        print(f"  Mold on scale: {state_machine.context.mold_on_scale}")
        
        # Verify current position matches expectations
        current_pos = machine.get_position()
        print(f"\nCurrent machine position:")
        print(f"  X={current_pos['X']}, Y={current_pos['Y']}, "
              f"Z={current_pos['Z']}, V={current_pos.get('V', 'N/A')}")
        
        # Verify all prerequisites for piston retrieval
        print("\nVerifying prerequisites for piston retrieval:")
        prerequisites_met = True
        
        # Check 1: Active tool is manipulator
        if state_machine.context.active_tool_id != "manipulator":
            print_error("Active tool is not 'manipulator'")
            prerequisites_met = False
        else:
            print_success("Active tool: manipulator ✓")
        
        # Check 2: Payload state is mold_without_top_piston
        if state_machine.context.payload_state != "mold_without_top_piston":
            print_error(f"Payload state is '{state_machine.context.payload_state}', must be 'mold_without_top_piston'")
            prerequisites_met = False
        else:
            print_success("Payload state: mold_without_top_piston ✓")
        
        # Check 3: Carrying a mold (current_well is not None)
        if state_machine.context.current_well is None:
            print_error("Not carrying a mold (current_well is None)")
            prerequisites_met = False
        else:
            print_success(f"Carrying mold: {state_machine.context.current_well.name} ✓")
        
        # Check 4: Mold does not have top piston
        if state_machine.context.current_well and state_machine.context.current_well.has_top_piston:
            print_error("Mold already has a top piston")
            prerequisites_met = False
        else:
            print_success("Mold does not have top piston ✓")
        
        # Check 5: Mold is not on scale
        if state_machine.context.mold_on_scale:
            print_error("Mold is on scale (must not be)")
            prerequisites_met = False
        else:
            print_success("Mold is not on scale ✓")
        
        # Check 6: Dispenser has pistons available
        if not state_machine.context.piston_dispensers or len(state_machine.context.piston_dispensers) == 0:
            print_error("No piston dispensers available")
            prerequisites_met = False
        elif state_machine.context.piston_dispensers[0].num_pistons == 0:
            print_error("Dispenser 0 has no pistons")
            prerequisites_met = False
        else:
            print_success(f"Dispenser 0 has {state_machine.context.piston_dispensers[0].num_pistons} pistons ✓")
        
        # Check 7: Z-height is appropriate for dispenser operations
        if state_machine.context.z_height_id not in ["dispenser_safe", "mold_transfer_safe"]:
            print_error(f"Z-height '{state_machine.context.z_height_id}' may not be suitable for dispenser operations")
            prerequisites_met = False
        else:
            print_success(f"Z-height: {state_machine.context.z_height_id} ✓")
        
        # Check 8: Dispenser position exists in registry
        piston_dispenser_0 = state_machine.context.piston_dispensers[0]
        if not state_machine._registry.has(piston_dispenser_0.ready_pos):
            print_error(f"Dispenser position '{piston_dispenser_0.ready_pos}' not found in registry")
            prerequisites_met = False
        else:
            dispenser_pos = state_machine._registry.get(piston_dispenser_0.ready_pos)
            if not dispenser_pos.coordinates:
                print_error(f"Dispenser position '{piston_dispenser_0.ready_pos}' has no coordinates")
                prerequisites_met = False
            else:
                print_success(f"Dispenser position '{piston_dispenser_0.ready_pos}' configured ✓")
                print(f"  Coordinates: x={dispenser_pos.coordinates.x}, y={dispenser_pos.coordinates.y}")
        
        if not prerequisites_met:
            raise TestError("Prerequisites not met - cannot proceed with test")
        
        print("\n" + "="*60)
        print("ALL PREREQUISITES MET - READY TO START TEST")
        print("="*60)
        
        print_success("Initialization complete")
        
        # ====================================================================
        # STEP 1: MOVE TO DISPENSER 0 READY POSITION
        # ====================================================================
        print_step(1, "Move to dispenser 0 ready position")
        
        wait_for_user_confirmation("Move to dispenser 0 ready position")
        result = state_machine.validated_move_to_dispenser(
            piston_dispenser=piston_dispenser_0
        )
        if not result.valid:
            raise TestError(f"Failed to move to dispenser 0: {result.reason}")
        
        print_success("Moved to dispenser 0 ready position")
        current_pos = machine.get_position()
        print(f"Position: X={current_pos['X']}, Y={current_pos['Y']}, "
              f"Z={current_pos['Z']}, V={current_pos.get('V', 'N/A')}")
        print(f"Context position: {state_machine.context.position_id}")
        
        # ====================================================================
        # STEP 2: RETRIEVE PISTON FROM DISPENSER 0
        # ====================================================================
        print_step(2, "Retrieve piston from dispenser 0")
        
        print(f"Dispenser 0 pistons before retrieval: {piston_dispenser_0.num_pistons}")
        print(f"Mold has piston before retrieval: {mock_mold.has_top_piston}")
        
        wait_for_user_confirmation("Retrieve piston from dispenser 0 (manipulator will move)")
        result = state_machine.validated_retrieve_piston(
            piston_dispenser=piston_dispenser_0,
            manipulator_config=manipulator._get_config_dict()
        )
        if not result.valid:
            raise TestError(f"Failed to retrieve piston: {result.reason}")
        
        print_success("Retrieved piston from dispenser 0")
        
        # Verify piston was added to mold
        if state_machine.context.current_well is None:
            raise TestError("Mold was lost during piston retrieval")
        
        if not state_machine.context.current_well.has_top_piston:
            raise TestError("Piston was not registered as added to mold")
        
        print(f"Dispenser 0 pistons after retrieval: {piston_dispenser_0.num_pistons}")
        print(f"Mold has piston after retrieval: {mock_mold.has_top_piston}")
        print(f"Current well: {state_machine.context.current_well.name}")
        print(f"Payload state: {state_machine.context.payload_state}")
        
        # ====================================================================
        # STEP 3: RETURN TO GLOBAL READY
        # ====================================================================
        print_step(3, "Return to global ready")
        
        wait_for_user_confirmation("Return to global ready")
        valid, reason = move_to_global_ready(state_machine)
        if not valid:
            raise TestError(f"Failed to return to global_ready: {reason}")
        
        print_success("Returned to global ready")
        current_pos = machine.get_position()
        print(f"Position: X={current_pos['X']}, Y={current_pos['Y']}, "
              f"Z={current_pos['Z']}, V={current_pos.get('V', 'N/A')}")
        print(f"Context position: {state_machine.context.position_id}")
        
        # ====================================================================
        # TEST COMPLETE
        # ====================================================================
        print("\n" + "="*60)
        print("TEST COMPLETED SUCCESSFULLY")
        print("="*60)
        print("\nSummary:")
        print(f"  Started at: global_ready")
        print(f"  Moved to: dispenser_ready_0")
        print(f"  Retrieved piston: Yes")
        print(f"  Returned to: global_ready")
        print(f"  Final position: {state_machine.context.position_id}")
        print(f"  Payload state: {state_machine.context.payload_state}")
        print(f"  Carrying mold: {state_machine.context.current_well.name if state_machine.context.current_well else 'None'}")
        if state_machine.context.current_well:
            print(f"  Mold has piston: {state_machine.context.current_well.has_top_piston}")
        print(f"  Dispenser 0 remaining pistons: {piston_dispenser_0.num_pistons}")
        
    except TestError as e:
        print_error(str(e))
        print("\nTEST FAILED")
        return 1
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        return 1
        
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        print("\nTEST FAILED")
        return 1
        
    finally:
        # Cleanup
        print("\n" + "="*60)
        print("CLEANUP")
        print("="*60)
        
        if machine:
            print("Disconnecting machine...")
            try:
                machine.disconnect()
                print_success("Machine disconnected")
            except Exception as e:
                print_error(f"Failed to disconnect machine: {e}")
        
        print("\nCleanup complete")
    
    return 0


if __name__ == "__main__":
    exit(main())

