"""
Jubilee Complete Test Program

This script tests the complete workflow of:
1. Picking up a mold from a mold slot
2. Placing it on the scale
3. Taring the scale
4. Weighing out powder
5. Returning the mold to its original location

Each step requires user confirmation before proceeding.
"""

# TODO: finish z homing script
# figure out scale preset point to get movement under scale working
# before running script, confirm all functions are implelmented

import time
from JubileeManager import JubileeManager
from MovementExecutor import FeedRate, MovementExecutor
from Scale import Scale, ScaleException
from Manipulator import ToolStateError
from trickler_labware import Mold


def wait_for_user(message: str = "Press Enter to continue..."):
    """Display a message and wait for user input before continuing"""
    input(f"\n{'='*70}\n{message}\n{'='*70}\n")


def display_step(step_num: int, total_steps: int, description: str):
    """Display a formatted step header"""
    print(f"\n{'='*70}")
    print(f"STEP {step_num}/{total_steps}: {description}")
    print('='*70)


def validate_jubilee_manager_config(manager: JubileeManager) -> bool:
    """
    Validate that JubileeManager configuration is properly loaded.
    
    Checks:
    - Deck initialization
    - All 16 slots are accessible
    - Labware is loaded in each slot
    - Molds are Mold objects with valid properties
    - Scale coordinates are set
    
    Args:
        manager: JubileeManager instance to validate
        
    Returns:
        True if all checks pass, False otherwise
    """
    print("\n" + "="*70)
    print("CONFIGURATION VALIDATION")
    print("="*70)
    
    validation_passed = True
    errors = []
    warnings = []
    
    # Check 1: Deck initialization
    print("\n[1/6] Checking deck initialization...")
    if manager.deck is None:
        errors.append("❌ CRITICAL: Deck is not initialized")
        validation_passed = False
        print("  ❌ Deck is None")
    else:
        print(f"  ✓ Deck initialized: {manager.deck.name if hasattr(manager.deck, 'name') else 'unnamed'}")
        print(f"  ✓ Deck safe_z: {manager.deck.safe_z}mm")
    
    # Check 2: Verify all 16 slots exist
    print("\n[2/6] Checking deck slots...")
    expected_slots = 16
    if manager.deck and hasattr(manager.deck, 'slots'):
        actual_slots = len(manager.deck.slots)
        if actual_slots != expected_slots:
            warnings.append(f"⚠ Expected {expected_slots} slots, found {actual_slots}")
            print(f"  ⚠ Found {actual_slots} slots (expected {expected_slots})")
        else:
            print(f"  ✓ All {expected_slots} slots present")
    else:
        errors.append("❌ CRITICAL: Cannot access deck slots")
        validation_passed = False
        print("  ❌ Deck slots not accessible")
    
    # Check 3: Verify labware loaded in slots
    print("\n[3/6] Checking labware in each slot...")
    if manager.deck and hasattr(manager.deck, 'slots'):
        labware_count = 0
        missing_labware = []
        
        for slot_id in range(16):
            slot_key = str(slot_id)
            if slot_key in manager.deck.slots:
                slot = manager.deck.slots[slot_key]
                if hasattr(slot, 'has_labware') and slot.has_labware:
                    labware_count += 1
                else:
                    missing_labware.append(slot_id)
            else:
                missing_labware.append(slot_id)
        
        print(f"  ✓ Labware loaded in {labware_count}/{expected_slots} slots")
        
        if missing_labware:
            # Map slot numbers to mold slot IDs for user reference
            missing_well_ids = []
            for slot_id in missing_labware:
                row = chr(ord('A') + (slot_id // 4))
                col = (slot_id % 4) + 1
                missing_well_ids.append(f"{row}{col}")
            
            warnings.append(f"⚠ No labware in slots: {', '.join(missing_well_ids)}")
            print(f"  ⚠ Missing labware in wells: {', '.join(missing_well_ids)}")
    
        # Check 4: Verify molds are Mold objects
    print("\n[4/6] Checking mold types and properties...")
    if manager.deck and hasattr(manager.deck, 'slots'):
        mold_count = 0
        invalid_wells = []
        well_property_issues = []
        
        for slot_id in range(16):
            slot_key = str(slot_id)
            row = chr(ord('A') + (slot_id // 4))
            col = (slot_id % 4) + 1
            well_id = f"{row}{col}"
            
            # Try to get the well
            if manager.state_machine:
                well = manager.state_machine.get_mold_from_deck(well_id)
            else:
                well = None
            
            if well is None:
                invalid_wells.append(well_id)
                continue
            
            # Check if it's a Mold
            if isinstance(well, Mold):
                mold_count += 1
                
                # Verify essential properties exist
                required_props = ['valid', 'has_top_piston', 'current_weight', 
                                 'target_weight', 'x', 'y', 'z']
                missing_props = []
                for prop in required_props:
                    if not hasattr(well, prop):
                        missing_props.append(prop)
                
                if missing_props:
                    well_property_issues.append(
                        f"{well_id} missing: {', '.join(missing_props)}"
                    )
            else:
                invalid_wells.append(f"{well_id} (not Mold)")
        
        print(f"  ✓ Found {mold_count} Mold objects")
        
        if invalid_wells:
            warnings.append(f"⚠ Wells not accessible or wrong type: {', '.join(invalid_wells)}")
            print(f"  ⚠ Invalid wells: {', '.join(invalid_wells)}")
        
        if well_property_issues:
            warnings.append(f"⚠ Wells with missing properties: {len(well_property_issues)}")
            print(f"  ⚠ Property issues in {len(well_property_issues)} wells")
            for issue in well_property_issues[:3]:  # Show first 3
                print(f"     - {issue}")
            if len(well_property_issues) > 3:
                print(f"     ... and {len(well_property_issues) - 3} more")
    
    # Check 5: Verify scale configuration
    print("\n[5/6] Checking scale configuration...")
    if manager.scale is None:
        errors.append("❌ CRITICAL: Scale object is not initialized")
        validation_passed = False
        print("  ❌ Scale is None")
    else:
        print("  ✓ Scale object initialized")
        
        # Check if scale coordinates are set
        scale_coords_set = (
            hasattr(manager.scale, 'x') and 
            hasattr(manager.scale, 'y') and 
            hasattr(manager.scale, 'z')
        )
        
        if scale_coords_set:
            # Check if they're not Ellipsis (...)
            if (manager.scale.x is ... or 
                manager.scale.y is ... or 
                manager.scale.z is ...):
                errors.append("❌ CRITICAL: Scale coordinates not set (still Ellipsis)")
                validation_passed = False
                print(f"  ❌ Scale coordinates not configured:")
                print(f"     X: {manager.scale.x}")
                print(f"     Y: {manager.scale.y}")
                print(f"     Z: {manager.scale.z}")
                print("  ⚠ You must set scale.x, scale.y, scale.z in JubileeManager.__init__")
            else:
                print(f"  ✓ Scale coordinates set:")
                print(f"     X: {manager.scale.x}mm")
                print(f"     Y: {manager.scale.y}mm")
                print(f"     Z: {manager.scale.z}mm")
        else:
            errors.append("❌ CRITICAL: Scale coordinates (x, y, z) not defined")
            validation_passed = False
            print("  ❌ Scale coordinates not defined")
    
    # Check 6: Verify manipulator configuration
    print("\n[6/6] Checking manipulator configuration...")
    if manager.manipulator is None:
        errors.append("❌ CRITICAL: Manipulator is not initialized")
        validation_passed = False
        print("  ❌ Manipulator is None")
    else:
        print("  ✓ Manipulator object initialized")
        print(f"     Index: {manager.manipulator.index}")
        print(f"     Name: {manager.manipulator.name}")
        
        # Check if manipulator has necessary attributes
        if hasattr(manager.manipulator, 'current_well'):
            print(f"     Carrying well: {manager.manipulator.current_well is not None}")
        
        if hasattr(manager.manipulator, 'SAFE_Z'):
            print(f"     Safe Z: {manager.manipulator.SAFE_Z}mm")
    
    # Summary
    print("\n" + "="*70)
    print("VALIDATION SUMMARY")
    print("="*70)
    
    if validation_passed and not errors:
        print("✓ All critical checks PASSED")
    else:
        print("❌ Validation FAILED - Critical issues found")
    
    if warnings:
        print(f"\n⚠ {len(warnings)} Warning(s):")
        for warning in warnings:
            print(f"  {warning}")
    
    if errors:
        print(f"\n❌ {len(errors)} Error(s):")
        for error in errors:
            print(f"  {error}")
        print("\n⚠ Cannot proceed with test until critical errors are resolved.")
    
    print("="*70)
    
    return validation_passed and len(errors) == 0


def main():
    """Main test program"""
    
    # Configuration
    DUET_IP = "192.168.1.2"
    SCALE_PORT = "/dev/ttyUSB0"
    TARGET_WEIGHT = 0.5  # grams
    TEST_WELL_ID = "A1"  # Mold slot to pick up mold from (A1 = slot 0)
    FEEDRATE = FeedRate.MEDIUM  # Movement feedrate (FAST=5000, MEDIUM=1000, SLOW=500 mm/min)
    
    # Total number of steps
    TOTAL_STEPS = 7
    
    print("\n" + "="*70)
    print("JUBILEE COMPLETE WORKFLOW TEST")
    print("="*70)
    print("\nThis test will perform the following operations:")
    print("  1. Connect to Jubilee machine and scale")
    print("  2. Pick up a mold from a mold slot")
    print("  3. Place the mold on the scale")
    print("  4. Tare the scale")
    print("  5. Weigh out powder (simulated)")
    print("  6. Pick up mold from scale")
    print("  7. Return the mold to its original location")
    print("\nEach step will pause for user confirmation.")
    
    # Get user configuration
    print("\n" + "-"*70)
    print("CONFIGURATION")
    print("-"*70)
    
    duet_input = input(f"Enter Jubilee IP address (default: {DUET_IP}): ").strip()
    if duet_input:
        DUET_IP = duet_input
    
    scale_input = input(f"Enter scale serial port (default: {SCALE_PORT}): ").strip()
    if scale_input:
        SCALE_PORT = scale_input
    
    well_input = input(f"Enter well ID to test (A1-A7, B1-B7, C1-C4, default: {TEST_WELL_ID}): ").strip().upper()
    if well_input:
        TEST_WELL_ID = well_input
    
    weight_input = input(f"Enter target weight in grams (default: {TARGET_WEIGHT}): ").strip()
    if weight_input:
        try:
            TARGET_WEIGHT = float(weight_input)
        except ValueError:
            print(f"Invalid weight, using default: {TARGET_WEIGHT}g")
    
    feedrate_input = input(f"Enter feedrate (fast/medium/slow, default: {FEEDRATE.value}): ").strip().lower()
    if feedrate_input:
        if feedrate_input == "fast":
            FEEDRATE = FeedRate.FAST
        elif feedrate_input == "slow":
            FEEDRATE = FeedRate.SLOW
        elif feedrate_input == "medium":
            FEEDRATE = FeedRate.MEDIUM
        else:
            print(f"Invalid feedrate, using default: {FEEDRATE.value}")
    
    # Get feedrate value for display
    feedrate_value = MovementExecutor.FEEDRATE_FAST if FEEDRATE == FeedRate.FAST else (MovementExecutor.FEEDRATE_MEDIUM if FEEDRATE == FeedRate.MEDIUM else MovementExecutor.FEEDRATE_SLOW)
    
    print(f"\nConfiguration:")
    print(f"  Jubilee IP: {DUET_IP}")
    print(f"  Scale Port: {SCALE_PORT}")
    print(f"  Test Well: {TEST_WELL_ID}")
    print(f"  Target Weight: {TARGET_WEIGHT}g")
    print(f"  Feedrate: {FEEDRATE.value} ({feedrate_value} mm/min)")
    
    wait_for_user("Press Enter to start the test...")
    
    # Initialize manager
    manager = None
    original_mold = None
    
    try:
        # ======================================================================
        # PREPROCESSING: Validate Configuration
        # ======================================================================
        print(f"\nInitializing JubileeManager...")
        manager = JubileeManager(feedrate=FEEDRATE)
        print("✓ JubileeManager initialized")
        
        # Validate configuration before connecting to hardware
        print("\nValidating JubileeManager configuration...")
        if not validate_jubilee_manager_config(manager):
            print("\n" + "!"*70)
            print("! CONFIGURATION VALIDATION FAILED")
            print("!"*70)
            print("\nPlease fix the errors above before running the test.")
            print("Common fixes:")
            print("  1. Set scale coordinates in JubileeManager.__init__()")
            print("  2. Ensure deck configuration files are in ./jubilee_api_config/")
            print("  3. Verify weight_well_labware.json is properly formatted")
            return
        
        print("\n✓ Configuration validation passed!")
        wait_for_user("Press Enter to proceed with hardware connection...")
        
        # ======================================================================
        # STEP 1: Connect to Jubilee and Scale
        # ======================================================================
        display_step(1, TOTAL_STEPS, "Connect to Jubilee and Scale")
        
        wait_for_user("Ready to connect to Jubilee and scale. Press Enter to continue...")
        
        print(f"Connecting to Jubilee at {DUET_IP}...")
        print(f"Connecting to scale at {SCALE_PORT}...")
        
        success = manager.connect(machine_address=DUET_IP, scale_port=SCALE_PORT)
        
        if not success:
            raise RuntimeError("Failed to connect to Jubilee or scale")
        
        print("✓ Successfully connected to Jubilee machine")
        print("✓ Successfully connected to scale")
        print("✓ Manipulator tool loaded and homed")
        
        # Verify scale is working
        print("\nVerifying scale connection...")
        initial_weight = manager.get_weight_stable()
        print(f"✓ Scale reading: {initial_weight:.4f}g")
        
        wait_for_user("STEP 1 COMPLETE. Press Enter to continue to next step...")
        
        # ======================================================================
        # STEP 2: Pick up mold from mold slot
        # ======================================================================
        display_step(2, TOTAL_STEPS, f"Pick up mold from mold slot {TEST_WELL_ID}")
        
        print(f"Preparing to pick up mold from mold slot {TEST_WELL_ID}")
        print("\nIMPORTANT: Ensure the following:")
        print(f"  - A mold is placed in mold slot {TEST_WELL_ID}")
        print(f"  - The mold does NOT have a top piston")
        print(f"  - The area is clear for movement")
        
        wait_for_user("Press Enter to pick up the mold...")
        
        # Get well from deck
        if not manager.state_machine:
            raise RuntimeError("State machine not configured")
        well = manager.state_machine.get_mold_from_deck(TEST_WELL_ID)
        if not well:
            raise ValueError(f"Well {TEST_WELL_ID} not found in deck")
        if not well.valid:
            raise ValueError(f"Well {TEST_WELL_ID} is not valid")
        
        # Well coordinates come from motion_platform_positions.json (mold_ready_{TEST_WELL_ID})
        print(f"Well {TEST_WELL_ID} ready position: {well.ready_pos}")
        
        # Move to well location
        print(f"Moving to well {TEST_WELL_ID}...")
        manager._move_to_well(TEST_WELL_ID)
        print("✓ Positioned over well")
        
        # Pick up mold
        print("Picking up mold...")
        manager.manipulator.pick_mold(TEST_WELL_ID)
        original_mold = well  # Store reference to original location
        print(f"✓ Mold picked up from {TEST_WELL_ID}")
        
        # Verify manipulator is carrying mold
        if not manager.manipulator.is_carrying_well():
            raise ToolStateError("Manipulator failed to pick up mold")
        
        status = manager.manipulator.get_status()
        print(f"✓ Manipulator status: Carrying mold '{status['current_well']['name']}'")
        
        wait_for_user("STEP 2 COMPLETE. Press Enter to continue to next step...")
        
        # ======================================================================
        # STEP 3: Place mold on scale
        # ======================================================================
        display_step(3, TOTAL_STEPS, "Place mold on scale")
        
        print("Preparing to place mold on scale")
        print("\nIMPORTANT: Ensure the scale pan is clear")
        
        wait_for_user("Press Enter to place mold on scale...")
        
        # Move to scale location
        print("Moving to scale...")
        manager._move_to_scale()
        print("✓ Positioned over scale")
        
        # Place mold on scale
        print("Placing mold on scale...")
        manager.manipulator.place_mold_on_scale()
        print("✓ Mold placed on scale")
        
        # Wait for scale to stabilize
        print("\nWaiting for scale to stabilize...")
        time.sleep(3)
        
        # Read weight with mold
        mold_weight = manager.get_weight_stable()
        print(f"✓ Scale reading with mold: {mold_weight:.4f}g")
        
        wait_for_user("STEP 3 COMPLETE. Press Enter to continue to next step...")
        
        # ======================================================================
        # STEP 4: Tare the scale
        # ======================================================================
        display_step(4, TOTAL_STEPS, "Tare the scale")
        
        print("Preparing to tare the scale")
        print("This will zero the scale with the mold on it.")
        
        wait_for_user("Press Enter to tare the scale...")
        
        print("Taring scale...")
        manager.scale.tare()
        time.sleep(2)
        
        # Verify tare
        tared_weight = manager.get_weight_stable()
        print(f"✓ Scale tared. Current reading: {tared_weight:.4f}g")
        
        if abs(tared_weight) > 0.01:
            print(f"⚠ Warning: Scale reading after tare is {tared_weight:.4f}g (expected ~0.00g)")
        
        wait_for_user("STEP 4 COMPLETE. Press Enter to continue to next step...")
        
        # ======================================================================
        # STEP 5: Weigh out powder (simulated)
        # ======================================================================
        display_step(5, TOTAL_STEPS, f"Weigh out powder (target: {TARGET_WEIGHT}g)")
        
        print(f"Preparing to weigh out {TARGET_WEIGHT}g of powder")
        print("\nNOTE: This is a simulated step.")
        print("In a real system, powder would be dispensed via trickler.")
        print("\nFor this test, manually add powder to the mold:")
        print(f"  Target weight: {TARGET_WEIGHT}g")
        
        wait_for_user(f"Add approximately {TARGET_WEIGHT}g of material to the mold, then press Enter...")
        
        # Monitor weight
        print("\nMonitoring weight...")
        time.sleep(2)
        
        for i in range(5):
            current_weight = manager.get_weight_stable()
            print(f"  Reading {i+1}/5: {current_weight:.4f}g (target: {TARGET_WEIGHT:.4f}g)")
            time.sleep(1)
        
        final_weight = manager.get_weight_stable()
        print(f"\n✓ Final weight: {final_weight:.4f}g")
        
        if abs(final_weight - TARGET_WEIGHT) < 0.1:
            print(f"✓ Weight is within tolerance (±0.1g)")
        else:
            print(f"⚠ Weight difference: {abs(final_weight - TARGET_WEIGHT):.4f}g")
        
        wait_for_user("STEP 5 COMPLETE. Press Enter to continue to next step...")
        
        # ======================================================================
        # STEP 6: Pick up mold from scale
        # ======================================================================
        display_step(6, TOTAL_STEPS, "Pick up mold from scale")
        
        print("Preparing to pick up mold from scale")
        
        wait_for_user("Press Enter to pick up mold from scale...")
        
        print("Picking up mold from scale...")
        manager.manipulator.pick_mold_from_scale()
        print("✓ Mold picked up from scale")
        
        # Verify manipulator is carrying mold
        if not manager.manipulator.is_carrying_well():
            raise ToolStateError("Manipulator failed to pick up mold from scale")
        
        print("✓ Manipulator is carrying mold")
        
        wait_for_user("STEP 6 COMPLETE. Press Enter to continue to next step...")
        
        # ======================================================================
        # STEP 7: Return mold to original location
        # ======================================================================
        display_step(7, TOTAL_STEPS, f"Return mold to well {TEST_WELL_ID}")
        
        print(f"Preparing to return mold to well {TEST_WELL_ID}")
        
        wait_for_user("Press Enter to return mold to original location...")
        
        # Move back to original well location
        print(f"Moving to well {TEST_WELL_ID}...")
        manager._move_to_well(TEST_WELL_ID)
        print("✓ Positioned over original well")
        
        # Place mold back
        print("Placing mold back in well...")
        returned_mold = manager.manipulator.place_mold(TEST_WELL_ID)
        print(f"✓ Mold returned to {TEST_WELL_ID}")
        
        # Verify manipulator is no longer carrying mold
        if manager.manipulator.is_carrying_well():
            raise ToolStateError("Manipulator still carrying mold after placing")
        
        print("✓ Manipulator released mold successfully")
        
        # ======================================================================
        # TEST COMPLETE
        # ======================================================================
        print("\n" + "="*70)
        print("TEST COMPLETE - ALL STEPS SUCCESSFUL")
        print("="*70)
        print("\nSummary:")
        print(f"  ✓ Picked up mold from mold slot {TEST_WELL_ID}")
        print(f"  ✓ Placed mold on scale")
        print(f"  ✓ Tared scale")
        print(f"  ✓ Weighed out powder (final: {final_weight:.4f}g)")
        print(f"  ✓ Returned mold to well {TEST_WELL_ID}")
        print("\nAll operations completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n⚠ Test interrupted by user (Ctrl+C)")
        print("Attempting cleanup...")
        
    except Exception as e:
        print(f"\n\n❌ ERROR: {e}")
        print("\nTest failed. Check error message above.")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        print("\n" + "-"*70)
        print("CLEANUP")
        print("-"*70)
        
        if manager:
            try:
                # If manipulator is still carrying a mold, try to return it
                if manager.manipulator and manager.manipulator.is_carrying_well():
                    print("⚠ Manipulator still carrying mold")
                    try:
                        if original_mold:
                            print(f"Attempting to return mold to {TEST_WELL_ID}...")
                            manager._move_to_well(TEST_WELL_ID)
                            manager.manipulator.place_mold(TEST_WELL_ID)
                            print(f"✓ Mold returned to {TEST_WELL_ID}")
                    except Exception as e:
                        print(f"⚠ Failed to return mold automatically: {e}")
                        print("Please manually return the mold to its original location")
                
                # Move to safe position
                print("Moving to safe position...")
                if manager.machine_read_only:
                    manager.machine_read_only.safe_z_movement()
                print("✓ Machine moved to safe position")
                
                # Disconnect
                print("Disconnecting from devices...")
                manager.disconnect()
                print("✓ Disconnected from Jubilee and scale")
                
            except Exception as e:
                print(f"⚠ Error during cleanup: {e}")
        
        print("\nCleanup complete.")


if __name__ == "__main__":
    main()

