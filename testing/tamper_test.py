#!/usr/bin/env python3
"""
Test script for the tamper functionality with stall detection and sensorless homing.
This demonstrates how to configure and use the tamper with TMC stall detection and sensorless homing.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
import time
from src.Manipulator import Manipulator, TamperStallEvent

class MockMachineConnection:
    """Mock machine connection for testing without actual hardware."""
    
    def __init__(self):
        self.commands_sent = []
        self.stall_detected = False
        self.homing_complete = False
    
    def send_command(self, command):
        """Mock sending a command to the machine."""
        self.commands_sent.append(command)
        print(f"Mock machine command: {command}")
        
        # Simulate homing completion
        if "G28 Z" in command:
            print("Simulating sensorless homing...")
            time.sleep(1.0)  # Simulate homing time
            self.homing_complete = True
            return "homing_complete"
        
        # Simulate stall detection for tamping commands
        if "G1 Z" in command and "F" in command and not self.stall_detected:
            print("Simulating tamper movement...")
            time.sleep(0.5)  # Simulate movement time
            if not self.stall_detected:
                self.stall_detected = True
                print("Simulating stall detection!")
                return "stall_detected"
    
    def get_commands(self):
        """Get list of commands sent to the machine."""
        return self.commands_sent.copy()

def test_tamper_configuration():
    """Test tamper configuration and stall detection setup."""
    print("=== Testing Tamper Configuration ===")
    
    # Load configuration
    with open('configs/tamper_config.json', 'r') as f:
        config = json.load(f)
    
    # Create manipulator with tamper configuration
    manipulator = Manipulator(index=0, name="test_manipulator", config=config)
    
    # Select tamper tool
    manipulator.select_tool(Manipulator.TOOL_TAMPER)
    
    # Get tamper status
    status = manipulator.get_tamper_status()
    print("Tamper status:")
    print(json.dumps(status, indent=2))
    
    # Calculate minimum stall speed
    min_speed = manipulator.calculate_min_stall_speed()
    print(f"Calculated minimum stall speed: {min_speed} steps/sec")
    
    return manipulator

def test_sensorless_homing_configuration(manipulator: Manipulator):
    """Test sensorless homing configuration."""
    print("\n=== Testing Sensorless Homing Configuration ===")
    
    # Create mock machine connection
    mock_connection = MockMachineConnection()
    
    # Configure sensorless homing
    manipulator.configure_sensorless_homing(mock_connection)
    
    # Check what commands were sent
    print("\nCommands sent to machine for sensorless homing:")
    for cmd in mock_connection.get_commands():
        print(f"  {cmd}")
    
    return mock_connection

def test_stall_detection_configuration(manipulator: Manipulator):
    """Test stall detection configuration."""
    print("\n=== Testing Stall Detection Configuration ===")
    
    # Create mock machine connection
    mock_connection = MockMachineConnection()
    
    # Configure stall detection
    manipulator.configure_stall_detection(mock_connection)
    
    # Check what commands were sent
    print("\nCommands sent to machine for stall detection:")
    for cmd in mock_connection.get_commands():
        print(f"  {cmd}")
    
    return mock_connection

def test_homing_operation(manipulator: Manipulator, mock_connection: MockMachineConnection):
    """Test sensorless homing operation."""
    print("\n=== Testing Sensorless Homing Operation ===")
    
    # Perform homing operation
    print("Starting sensorless homing...")
    manipulator.home_tamper(machine_connection=mock_connection)
    
    print("\nHoming operation complete!")
    print(f"Final tamper position: {manipulator.tamper_position}mm")
    
    # Check what commands were sent during homing
    print("\nCommands sent during homing:")
    for cmd in mock_connection.get_commands():
        print(f"  {cmd}")

def test_tamping_operation(manipulator: Manipulator, mock_connection: MockMachineConnection):
    """Test tamping operation with stall detection."""
    print("\n=== Testing Tamping Operation ===")
    
    # Perform tamping operation
    print("Starting tamping operation...")
    manipulator.tamp(target_depth=10.0, machine_connection=mock_connection)
    
    print("\nTamping operation complete!")
    print(f"Final tamper position: {manipulator.tamper_position}mm")

def test_batch_tamping(manipulator: Manipulator, mock_connection: MockMachineConnection):
    """Test batch tamping operations."""
    print("\n=== Testing Batch Tamping ===")
    
    depths = [5.0, 8.0, 12.0, 15.0]
    
    for i, depth in enumerate(depths, 1):
        print(f"\nTamping operation {i}/{len(depths)} to depth {depth}mm")
        manipulator.tamp(target_depth=depth, machine_connection=mock_connection)
        time.sleep(0.5)  # Brief pause between operations

def test_complete_workflow(manipulator: Manipulator):
    """Test complete workflow: homing -> tamping -> batch operations."""
    print("\n=== Testing Complete Workflow ===")
    
    # Create mock machine connection
    mock_connection = MockMachineConnection()
    
    # Step 1: Home the tamper
    print("Step 1: Homing tamper...")
    manipulator.home_tamper(machine_connection=mock_connection)
    
    # Step 2: Perform initial tamping
    print("\nStep 2: Initial tamping...")
    manipulator.tamp(target_depth=5.0, machine_connection=mock_connection)
    
    # Step 3: Perform deeper tamping
    print("\nStep 3: Deeper tamping...")
    manipulator.tamp(target_depth=12.0, machine_connection=mock_connection)
    
    # Step 4: Perform final tamping
    print("\nStep 4: Final tamping...")
    manipulator.tamp(target_depth=18.0, machine_connection=mock_connection)
    
    print(f"\nComplete workflow finished. Final position: {manipulator.tamper_position}mm")
    
    # Show all commands sent
    print("\nAll commands sent during workflow:")
    for i, cmd in enumerate(mock_connection.get_commands(), 1):
        print(f"  {i:2d}. {cmd}")

def main():
    """Main test function."""
    print("Tamper Stall Detection and Sensorless Homing Test")
    print("=" * 60)
    
    try:
        # Test configuration
        manipulator = test_tamper_configuration()
        
        # Test sensorless homing setup
        homing_connection = test_sensorless_homing_configuration(manipulator)
        
        # Test stall detection setup
        stall_connection = test_stall_detection_configuration(manipulator)
        
        # Test homing operation
        test_homing_operation(manipulator, homing_connection)
        
        # Test single tamping operation
        test_tamping_operation(manipulator, stall_connection)
        
        # Test batch tamping
        test_batch_tamping(manipulator, stall_connection)
        
        # Test complete workflow
        test_complete_workflow(manipulator)
        
        print("\n" + "=" * 60)
        print("All tests completed successfully!")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 