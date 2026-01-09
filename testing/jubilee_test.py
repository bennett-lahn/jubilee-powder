"""
Basic Jubilee Test Script
This script homes the Jubilee motion platform and moves it in a circle twice using G28 arc commands.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import math
import time
from science_jubilee.Machine import Machine
from src.Scale import Scale

def main():
    # Initialize the Machine
    # Note: May need to adjust the address parameter based on Jubilee's IP
    print("Initializing Jubilee machine...")
    machine = Machine(address="192.168.1.2")  # Default Jubilee IP
    
    try:
        machine.connect()
        # Home all axes
        print("Homing all axes...")
        # machine.home_all()
        print("Homing complete!")
        
        # Wait a moment for homing to complete
        while not all(machine.axes_homed):
            time.sleep(1)
        
        # Move to starting position (center of work area)
        center_x = 150  # mm (adjust based on your bed size)
        center_y = 150  # mm (adjust based on your bed size)
        safe_z = 50    # mm (safe height above bed)
        radius = 90    # mm (circle radius)
        
        print(f"Moving to starting position: X={center_x}, Y={center_y}")
        # Move to safe Z height first (since no deck is loaded)
        machine.move_to(z=safe_z)
        machine.move_to(x=center_x, y=center_y)
        
        # Calculate starting point on the circle (at 0 degrees)
        start_x = center_x + radius
        start_y = center_y
        
        print("Starting circular motion using G2/G3 arc commands...")
        
        # Perform two complete circles using G2/G3 arc commands
        for circle_num in range(2):
            print(f"Circle {circle_num + 1}/2")
            
            # Move to starting point of the circle
            machine.move_to(x=start_x, y=start_y, z=safe_z)
            
            # Create a full circle using G2 (clockwise) or G3 (counterclockwise)
            # G2/G3 X<end_x> Y<end_y> I<offset_x> J<offset_y> F<feedrate>
            # For a full circle, end point = start point, and I/J are the center offset from start
            end_x = start_x  # End where we started
            end_y = start_y
            i_offset = -radius  # Center is radius distance in negative X from start point
            j_offset = 0       # Center is at same Y as start point
            
            gcode_command = f"G2 X{end_x} Y{end_y} I{i_offset} J{j_offset} F3000"
            print(f"Executing: {gcode_command}")
            machine.gcode(gcode_command)
            
            print(f"Circle {circle_num + 1} completed!")
            time.sleep(1)  # Pause between circles
        
        # Return to center position
        print("Returning to center position...")
        machine.move_to(x=center_x, y=center_y, z=safe_z)
        
        print("Motion sequence completed successfully!")
        
    except Exception as e:
        print(f"Error occurred: {e}")
        print("Make sure your Jubilee is connected and properly configured.")
        
    finally:
        # Clean disconnect
        print("Disconnecting from machine...")
        machine.disconnect()

if __name__ == "__main__":
    port = input("Enter the serial port for the scale (e.g., COM3 or /dev/ttyUSB0): ")
    scale = Scale(port)
    try:
        scale.connect()
        print("\nPlace the empty container on the scale and press Enter...")
        input()
        print("Taring the scale...")
        scale.tare()
        print("Tare complete. Remove your hands and wait for the scale to stabilize.")
        time.sleep(2)
        print("\nPlace the object to be weighed in the container and press Enter...")
        input()
        print("Measuring weight...")
        weight = scale.get_weight(stable=True)
        print(f"Measured weight: {weight:.4f} g")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        scale.disconnect()
