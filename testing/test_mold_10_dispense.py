"""
Physical test for mold 10 pick, dispense, and place workflow using MotionPlatformStateMachine.

Prerequisites (user must do before running this test):
1. Home jubilee (all axes)
2. Move to global_ready position
3. Pick up manipulator tool

This test performs:
1. Move to mold 10's ready point
2. Pick up mold 10
3. Move to scale
4. Place mold on scale
5. Fill mold with 0.25 grams of powder
6. Pick up mold from scale
7. Move to global ready (from scale ready)
8. Move to dispenser 0 ready position
9. Retrieve piston from dispenser 0
10. Return to global ready
11. Move to mold 10 ready and place mold back
12. Return to global ready finish

The test uses MotionPlatformStateMachine as the top-level module and performs
all the initialization tasks that JubileeManager typically handles.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
from science_jubilee.Machine import Machine
from src.Scale import Scale
from src.MotionPlatformStateMachine import MotionPlatformStateMachine
from src.Manipulator import Manipulator
from jubilee_api_config.constants import FeedRate
from src.ConfigLoader import config


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


def move_to_global_ready(state_machine) -> bool:
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
            # Use mold_transfer_safe as default
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
    # try:
    #     input()
    # except KeyboardInterrupt:
    #     print("\n\nAborted by user.")
    #     raise


def main():
    """Main test function"""
    
    # Configuration
    MACHINE_ADDRESS = config.get_duet_ip()  # Get from config
    SCALE_PORT = "/dev/ttyUSB0"  # Adjust as needed for your system
    # Resolve config path relative to project root
    project_root = Path(__file__).parent.parent
    STATE_MACHINE_CONFIG = str(project_root / "jubilee_api_config" / "motion_platform_positions.json")
    TARGET_WEIGHT = 0.25  # grams
    MOLD_ID = "10"  # Mold number to work with
    
    print("\n" + "="*60)
    print("MOLD 10 DISPENSE TEST")
    print("="*60)
    print("\nThis test assumes the following prerequisites have been met:")
    print("1. Jubilee has been homed (all axes)")
    print("2. Machine is at global_ready position")
    print("3. Manipulator tool has been picked up")
    print("\nPress Enter to continue or Ctrl+C to abort...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\nTest aborted by user.")
        return
    
    # Initialize components
    machine = None
    scale = None
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
        
        # Connect to scale
        print(f"Connecting to scale on {SCALE_PORT}...")
        scale = Scale(port=SCALE_PORT)
        scale.connect()
        print_success(f"Connected to scale)")
        
        # Initialize state machine
        print("Initializing motion platform state machine...")
        config_path = Path(STATE_MACHINE_CONFIG)
        if not config_path.exists():
            raise TestError(f"State machine config not found: {STATE_MACHINE_CONFIG}")
        
        state_machine = MotionPlatformStateMachine.from_config_file(
            config_path
            ,machine
            ,scale=scale
            ,feedrate=FeedRate.MEDIUM
        )
        print_success("State machine initialized")
        
        # Initialize deck (required for well operations)
        print("Initializing deck...")
        deck_config_path = str(project_root / "jubilee_api_config")
        state_machine.initialize_deck(config_path=deck_config_path)
        print_success("Deck initialized")
        
        # Initialize dispensers (required for piston operations)
        print("Initializing dispensers...")
        NUM_PISTON_DISPENSERS = 1  # At least dispenser 0
        NUM_PISTONS_PER_DISPENSER = 10  # Adjust as needed
        state_machine.initialize_dispensers(
            num_piston_dispensers=NUM_PISTON_DISPENSERS,
            num_pistons_per_dispenser=NUM_PISTONS_PER_DISPENSER
        )
        print_success("Dispensers initialized")
        
        # Create manipulator
        print("Initializing manipulator...")
        # Config will default to system_config.json
        manipulator = Manipulator(
            index=0
            ,name="manipulator"
            ,state_machine=state_machine
        )
        print_success("Manipulator initialized")
        
        # Update state machine context to reflect prerequisites
        # (Assumes user has already homed, moved to global_ready, and picked up tool)
        print("\nSetting initial context (assuming prerequisites completed)...")
        state_machine.context.position_id = "global_ready"
        state_machine.update_context(
            z_height_id="mold_transfer_safe"
            ,active_tool_id="manipulator"
            ,payload_state="empty"
        )
        print_success("Context updated: at global_ready with manipulator tool")
        
        # Verify current position matches expectations
        current_pos = machine.get_position()
        print(f"Current position: X={current_pos['X']}, Y={current_pos['Y']}, "
              f"Z={current_pos['Z']}, V={current_pos.get('V', 'N/A')}")
        
        print_success("Initialization complete")
        
        # ====================================================================
        # STEP 1: MOVE TO MOLD 10 READY POINT
        # ====================================================================
        print_step(1, f"Move to mold {MOLD_ID} ready point")
        
        wait_for_user_confirmation(f"Move to mold {MOLD_ID} ready point")
        result = state_machine.validated_move_to_mold_slot(well_id=MOLD_ID)
        if not result.valid:
            raise TestError(f"Failed to move to mold {MOLD_ID}: {result.reason}")
        
        print_success(f"Moved to mold {MOLD_ID} ready point")
        current_pos = machine.get_position()
        print(f"Position: X={current_pos['X']}, Y={current_pos['Y']}, "
              f"Z={current_pos['Z']}")
        
        # ====================================================================
        # STEP 2: PICK UP MOLD 10
        # ====================================================================
        print_step(2, f"Pick up mold {MOLD_ID}")
        
        wait_for_user_confirmation(f"Pick up mold {MOLD_ID} (manipulator will move)")
        manipulator.pick_mold(well_id=MOLD_ID)
        print_success(f"Picked up mold {MOLD_ID}")
        
        if state_machine.context.current_well is None:
            raise TestError("Mold was not registered as picked up")
        
        print(f"Current well: {state_machine.context.current_well.name}")
        print(f"Payload state: {state_machine.context.payload_state}")
        
        # ====================================================================
        # STEP 3: MOVE TO SCALE
        # ====================================================================
        print_step(3, "Move to scale")
        
        wait_for_user_confirmation("Move to scale ready position")
        result = state_machine.validated_move_to_scale()
        if not result.valid:
            raise TestError(f"Failed to move to scale: {result.reason}")
        
        print_success("Moved to scale ready position")
        current_pos = machine.get_position()
        print(f"Position: X={current_pos['X']}, Y={current_pos['Y']}, "
              f"Z={current_pos['Z']}")
        
        # ====================================================================
        # STEP 4: PLACE MOLD ON SCALE
        # ====================================================================
        print_step(4, "Place mold on scale")
        
        wait_for_user_confirmation("Place mold on scale (manipulator will move down)")
        manipulator.place_mold_on_scale()
        print_success("Placed mold on scale")
        
        if not state_machine.context.mold_on_scale:
            raise TestError("Mold was not registered as placed on scale")
        
        # ====================================================================
        # STEP 5: FILL MOLD WITH 0.25 GRAMS OF POWDER
        # ====================================================================
        print_step(5, f"Fill mold with {TARGET_WEIGHT} grams of powder")

        wait_for_user_confirmation(f"Fill mold with {TARGET_WEIGHT} grams of powder (trickler will move)")
        initial_weight = scale.get_weight(stable=True)
        result = state_machine.validated_fill_powder(target_weight=TARGET_WEIGHT)
        if not result.valid:
            raise TestError(f"Failed to fill mold with powder: {result.reason}")
        
        # Read final weight
        final_weight = scale.get_weight(stable=True)
        print_success("Filled mold with powder")
        print(f"Final weight: {final_weight:.4f} g")
        print(f"Dispensed amount: {final_weight:.4f} g")
        print(f"Target: {TARGET_WEIGHT:.4f} g")
        print(f"Error: {abs(final_weight - TARGET_WEIGHT):.4f} g")
        
        # ====================================================================
        # STEP 6: PICK UP MOLD FROM SCALE
        # ====================================================================
        print_step(6, "Pick up mold from scale")
        
        wait_for_user_confirmation("Pick up mold from scale (manipulator will move)")
        manipulator.pick_mold_from_scale()
        print_success("Picked up mold from scale")
        
        if state_machine.context.mold_on_scale:
            raise TestError("Mold still registered as on scale")
        
        if state_machine.context.current_well is None:
            raise TestError("Mold was not registered as picked up")
        
        # ====================================================================
        # STEP 7: MOVE TO GLOBAL READY (from scale ready)
        # ====================================================================
        print_step(7, "Move to global ready (from scale ready)")
        
        wait_for_user_confirmation("Move to global ready")
        valid, reason = move_to_global_ready(state_machine)
        if not valid:
            raise TestError(f"Failed to move to global_ready: {reason}")
        
        print_success("Moved to global ready")
        current_pos = machine.get_position()
        print(f"Position: X={current_pos['X']}, Y={current_pos['Y']}, "
              f"Z={current_pos['Z']}, V={current_pos.get('V', 'N/A')}")
        
        # ====================================================================
        # STEP 8: MOVE TO DISPENSER 0 READY POSITION
        # ====================================================================
        print_step(8, "Move to dispenser 0 ready position")
        
        # Get dispenser 0 from state machine
        if not state_machine.context.piston_dispensers or len(state_machine.context.piston_dispensers) == 0:
            raise TestError("No piston dispensers available")
        
        piston_dispenser_0 = state_machine.context.piston_dispensers[0]
        
        wait_for_user_confirmation("Move to dispenser 0 ready position")
        result = state_machine.validated_move_to_dispenser(
            piston_dispenser=piston_dispenser_0
        )
        if not result.valid:
            raise TestError(f"Failed to move to dispenser 0: {result.reason}")
        
        print_success("Moved to dispenser 0 ready position")
        current_pos = machine.get_position()
        print(f"Position: X={current_pos['X']}, Y={current_pos['Y']}, "
              f"Z={current_pos['Z']}")
        
        # ====================================================================
        # STEP 9: RETRIEVE PISTON ACTION
        # ====================================================================
        print_step(9, "Retrieve piston from dispenser 0")
        
        wait_for_user_confirmation("Retrieve piston from dispenser 0 (manipulator will move)")
        result = state_machine.validated_retrieve_piston(
            piston_dispenser=piston_dispenser_0,
            manipulator_config=manipulator._get_config_dict()
        )
        if not result.valid:
            raise TestError(f"Failed to retrieve piston: {result.reason}")
        
        print_success("Retrieved piston from dispenser 0")
        if state_machine.context.current_well is None:
            raise TestError("Mold was lost during piston retrieval")
        
        if not state_machine.context.current_well.has_top_piston:
            raise TestError("Piston was not registered as added to mold")
        
        print(f"Current well: {state_machine.context.current_well.name}")
        print(f"Has top piston: {state_machine.context.current_well.has_top_piston}")
        
        # ====================================================================
        # STEP 10: RETURN TO GLOBAL READY
        # ====================================================================
        print_step(10, "Return to global ready")
        
        wait_for_user_confirmation("Return to global ready")
        valid, reason = move_to_global_ready(state_machine)
        if not valid:
            raise TestError(f"Failed to return to global_ready: {reason}")
        
        print_success("Returned to global ready")
        current_pos = machine.get_position()
        print(f"Position: X={current_pos['X']}, Y={current_pos['Y']}, "
              f"Z={current_pos['Z']}, V={current_pos.get('V', 'N/A')}")
        
        # ====================================================================
        # STEP 11: MOVE TO MOLD 10 READY AND PLACE
        # ====================================================================
        print_step(11, f"Move to mold {MOLD_ID} ready and place mold back")
        
        wait_for_user_confirmation(f"Move to mold {MOLD_ID} ready point")
        result = state_machine.validated_move_to_mold_slot(well_id=MOLD_ID)
        if not result.valid:
            raise TestError(f"Failed to move to mold {MOLD_ID}: {result.reason}")
        
        print_success(f"Moved to mold {MOLD_ID} ready point")
        current_pos = machine.get_position()
        print(f"Position: X={current_pos['X']}, Y={current_pos['Y']}, "
              f"Z={current_pos['Z']}")
        
        wait_for_user_confirmation(f"Place mold {MOLD_ID} back (manipulator will move down)")
        manipulator.place_mold(well_id=MOLD_ID)
        print_success(f"Placed mold {MOLD_ID} back in position")
        
        if state_machine.context.current_well is not None:
            raise TestError("Mold still registered as being carried")
        
        print(f"Payload state: {state_machine.context.payload_state}")
        
        # ====================================================================
        # STEP 12: RETURN TO GLOBAL READY FINISH
        # ====================================================================
        print_step(12, "Return to global ready finish")
        
        wait_for_user_confirmation("Return to global ready finish")
        valid, reason = move_to_global_ready(state_machine)
        if not valid:
            raise TestError(f"Failed to return to global_ready: {reason}")
        
        print_success("Returned to global ready finish")
        current_pos = machine.get_position()
        print(f"Position: X={current_pos['X']}, Y={current_pos['Y']}, "
              f"Z={current_pos['Z']}, V={current_pos.get('V', 'N/A')}")
        
        # ====================================================================
        # TEST COMPLETE
        # ====================================================================
        print("\n" + "="*60)
        print("TEST COMPLETED SUCCESSFULLY")
        print("="*60)
        print("\nSummary:")
        print(f"  Mold ID: {MOLD_ID}")
        print(f"  Target weight: {TARGET_WEIGHT:.4f} g")
        print(f"  Dispensed weight: {final_weight - initial_weight:.4f} g")
        print(f"  Error: {abs(final_weight - initial_weight - TARGET_WEIGHT):.4f} g")
        print(f"  Final position: global_ready")
        print(f"  Payload state: {state_machine.context.payload_state}")
        if state_machine.context.current_well:
            print(f"  Carrying: {state_machine.context.current_well.name}")
            print(f"  Has top piston: {state_machine.context.current_well.has_top_piston}")
        
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
        
        if scale and scale.is_connected:
            print("Disconnecting scale...")
            try:
                scale.disconnect()
                print_success("Scale disconnected")
            except Exception as e:
                print_error(f"Failed to disconnect scale: {e}")
        
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

