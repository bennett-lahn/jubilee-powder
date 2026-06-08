"""
Interactive Jubilee Test - Powder Dispensing with Tamping

This script provides an interactive workflow for powder dispensing with tamping:
1. Displays splash screen with requirements
2. Homes all axes
3. Picks up manipulator tool
4. Accepts user input for mold selection (0-17)
5. Dispenses powder to selected mold
6. Tamps the powder
7. Retrieves and places top piston
8. Returns mold to slot
9. Returns to global ready position for next operation

Press Ctrl+C to exit at any time.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import time
from src.JubileeManager import JubileeManager
from jubilee_api_config.constants import FeedRate


def display_splash_screen():
    """Display splash screen with requirements"""
    print("\n" + "=" * 70)
    print(" " * 15 + "JUBILEE POWDER DISPENSE TEST")
    print("=" * 70)
    print("\nREQUIREMENTS:")
    print("  • Tool must be parked (Tool 0)")
    print("  • Gantry must be at global ready position")
    print("  • Scale must be connected and tared")
    print("  • Piston dispensers must be loaded")
    print("\nOPERATION:")
    print("  1. System will home all axes")
    print("  2. System will pick up manipulator tool")
    print("  3. You will select mold number (0-17)")
    print("  4. System will dispense, tamp, and place piston")
    print("  5. Repeat for additional molds or Ctrl+C to exit")
    print("=" * 70)


def wait_for_user(message: str = "Press Enter to continue..."):
    """Display a message and wait for user input"""
    input(f"\n{message}")


def get_mold_selection() -> str:
    """Get mold number from user (0-17)"""
    while True:
        try:
            user_input = input(
                "\nEnter mold number to dispense (0-17) or 'q' to quit: "
            ).strip()

            if user_input.lower() == "q":
                return None

            mold_num = int(user_input)

            if 0 <= mold_num <= 17:
                return str(mold_num)
            else:
                print("❌ Invalid input. Please enter a number between 0 and 17.")

        except ValueError:
            print("❌ Invalid input. Please enter a number between 0 and 17.")


def get_target_weight() -> float:
    """Get target weight from user"""
    DEFAULT_WEIGHT = 0.5  # grams (matching jubilee_complete_test.py)

    while True:
        try:
            user_input = input(
                f"Enter target weight in grams (default: {DEFAULT_WEIGHT}): "
            ).strip()

            # If empty, use default
            if not user_input:
                return DEFAULT_WEIGHT

            weight = float(user_input)

            if weight > 0:
                return weight
            else:
                print("❌ Weight must be greater than 0.")

        except ValueError:
            print("❌ Invalid input. Please enter a numeric value.")


def dispense_with_tamp(
    manager: JubileeManager, well_id: str, target_weight: float
) -> bool:
    """
    Perform complete powder dispense operation with tamping.

    Uses the high-level JubileeManager.dispense_to_well() method which now includes:
    1. Picks up mold from slot
    2. Places on scale
    3. Fills with powder to target weight
    4. Picks up from scale
    5. Tamps the powder
    6. Retrieves piston from dispenser
    7. Places top piston on mold
    8. Returns mold to slot
    9. Returns to global ready position

    Args:
        manager: JubileeManager instance
        well_id: Mold slot identifier (0-17)
        target_weight: Target powder weight in grams

    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"\n{'=' * 70}")
        print(f"DISPENSING TO MOLD {well_id}")
        print(f"Target weight: {target_weight}g")
        print("=" * 70)

        # Tare scale before starting
        print("\nTaring scale...")
        time.sleep(2)  # Wait for stabilization
        manager.scale.tare()
        time.sleep(1)
        print("✓ Scale tared")

        # Use the high-level dispense_to_well method
        # This handles the entire workflow including tamping
        print(f"\nStarting dispense operation to mold {well_id}...")
        success = manager.dispense_to_well(well_id, target_weight)

        if not success:
            print("\n❌ Dispense operation failed")
            return False

        # Get final weight
        final_weight = manager.get_weight_stable()
        print(f"\n✓ Dispense completed. Final weight: {final_weight:.3f}g")

        # Return to global ready position
        print("\nReturning to global ready position...")
        if manager.state_machine:
            result = manager.state_machine.validated_move_to_global_ready()
            if not result.valid:
                print(f"⚠ Warning: Failed to return to global ready: {result.reason}")
            else:
                print("✓ Returned to global ready position")

        print(f"\n{'=' * 70}")
        print(f"✓ DISPENSE TO MOLD {well_id} COMPLETE")
        print("=" * 70)

        return True

    except Exception as e:
        print(f"\n❌ ERROR during dispense: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Main program loop"""
    manager = None

    try:
        # Display splash screen
        display_splash_screen()

        # Wait for user to verify requirements
        wait_for_user("\nPress Enter when ready to begin...")

        # Get connection parameters
        print("\n" + "=" * 70)
        print("CONNECTION SETUP")
        print("=" * 70)

        # Default configuration (matching jubilee_complete_test.py)
        DUET_IP = "192.168.1.2"
        SCALE_PORT = "/dev/ttyUSB0"
        NUM_DISPENSERS = 2
        PISTONS_PER_DISPENSER = 10

        machine_ip = input(f"Enter Jubilee IP address (default: {DUET_IP}): ").strip()
        if not machine_ip:
            machine_ip = DUET_IP

        scale_port = input(f"Enter scale port (default: {SCALE_PORT}): ").strip()
        if not scale_port:
            scale_port = SCALE_PORT

        num_dispensers_input = input(
            f"Enter number of piston dispensers (default: {NUM_DISPENSERS}): "
        ).strip()
        num_dispensers = (
            int(num_dispensers_input) if num_dispensers_input else NUM_DISPENSERS
        )

        pistons_input = input(
            f"Enter pistons per dispenser (default: {PISTONS_PER_DISPENSER}): "
        ).strip()
        pistons_per_dispenser = (
            int(pistons_input) if pistons_input else PISTONS_PER_DISPENSER
        )

        # Display configuration summary
        print("\nConfiguration:")
        print(f"  Jubilee IP: {machine_ip}")
        print(f"  Scale Port: {scale_port}")
        print(f"  Piston Dispensers: {num_dispensers}")
        print(f"  Pistons per Dispenser: {pistons_per_dispenser}")
        print(f"  Feedrate: {FeedRate.SLOW.value} mm/min")

        # Create manager
        print("\n" + "=" * 70)
        print("INITIALIZING JUBILEE SYSTEM")
        print("=" * 70)

        manager = JubileeManager(
            num_piston_dispensers=num_dispensers,
            num_pistons_per_dispenser=pistons_per_dispenser,
            feedrate=FeedRate.SLOW,
        )

        print("\nStep 1: Connecting to hardware...")
        wait_for_user("Press Enter to connect...")

        print("\nConnecting to Jubilee and scale...")
        print("This will:")
        print("  • Connect to machine")
        print("  • Connect to scale")
        print("  • Home all axes (X, Y, Z, U)")
        print("  • Pick up manipulator tool")
        print("  • Home manipulator axis (V)")

        wait_for_user("\nPress Enter to begin homing sequence...")

        if not manager.connect(machine_address=machine_ip, scale_port=scale_port):
            print("❌ Failed to connect to hardware")
            return

        print("\n✓ System ready!")
        print("  ✓ Connected to Jubilee")
        print("  ✓ Connected to scale")
        print("  ✓ All axes homed")
        print("  ✓ Manipulator tool picked up")
        print("  ✓ System at global ready position")

        # Main operation loop
        print("\n" + "=" * 70)
        print("READY FOR OPERATIONS")
        print("=" * 70)
        print("\nYou can now dispense to molds.")
        print("Enter 'q' at mold selection to quit.\n")

        while True:
            # Get mold selection
            mold_id = get_mold_selection()

            if mold_id is None:
                print("\nExiting...")
                break

            # Get target weight
            target_weight = get_target_weight()

            # Confirm operation
            confirm = (
                input(f"\nDispense {target_weight}g to mold {mold_id}? (y/n): ")
                .strip()
                .lower()
            )

            if confirm != "y":
                print("Operation cancelled.")
                continue

            # Perform dispense operation
            success = dispense_with_tamp(manager, mold_id, target_weight)

            if success:
                print("\n✓ Operation completed successfully!")

                # Show remaining pistons
                print("\nRemaining pistons:")
                for dispenser in manager.piston_dispensers:
                    print(
                        f"  Dispenser {dispenser.index}: {dispenser.num_pistons} pistons"
                    )
            else:
                print("\n❌ Operation failed. Check error messages above.")
                retry = input("\nContinue with next operation? (y/n): ").strip().lower()
                if retry != "y":
                    break

    except KeyboardInterrupt:
        print("\n\n⚠ Program interrupted by user (Ctrl+C)")

    except Exception as e:
        print(f"\n\n❌ UNEXPECTED ERROR: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Cleanup
        if manager and manager.connected:
            print("\n" + "=" * 70)
            print("DISCONNECTING")
            print("=" * 70)

            try:
                # Check if manipulator is carrying a mold
                if manager.manipulator and manager.manipulator.is_carrying_mold():
                    print("⚠ Warning: Manipulator is still carrying a mold")
                    print("Please manually return the mold before disconnecting")
                    wait_for_user("Press Enter after mold is returned...")

                print("Disconnecting from hardware...")
                manager.disconnect()
                print("✓ Disconnected")

            except Exception as e:
                print(f"⚠ Error during disconnect: {e}")

        print("\nProgram terminated.")


if __name__ == "__main__":
    main()
