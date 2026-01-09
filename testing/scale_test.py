"""
Basic Scale Test Script
This script connects to a scale and measures the weight of an object.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import time
from src.Scale import Scale
import serial
from science_jubilee.Machine import Machine
import matplotlib.pyplot as plt
import numpy as np
import threading
import csv

def listener_mode(port):
    ser = serial.Serial(port, 2400, timeout=1)
    ser.reset_input_buffer()
    try:
        while True:
            if ser.in_waiting > 0:
                line = ser.readline().decode('ascii', errors='ignore').rstrip()
                print(f"Received: {line}")
    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        ser.close()

def scale_test_mode(port):
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

def continuous_weight_mode(port):
    scale = Scale(port)
    try:
        scale.connect()
        print("\nPlace the empty container on the scale and press Enter...")
        input()
        print("Taring the scale...")
        scale.tare()
        print("Tare complete.")
        print("Starting continuous weight monitoring...")
        print("Press Ctrl+C to stop.\n")
        time.sleep(1)
        
        # Continuously read weight
        while True:
            try:
                weight = scale.get_weight(stable=False)
                print(f"\rCurrent weight: {weight:>10.4f} g", end='', flush=True)
                time.sleep(0.1)  # Update 10 times per second
            except KeyboardInterrupt:
                print("\n\nStopping continuous monitoring...")
                break
            except Exception as e:
                print(f"\nError reading weight: {e}")
                time.sleep(0.5)
                
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        scale.disconnect()

def _run_single_movement_test(machine, scale, iterations, feedrate):
    """Helper function to run a single movement repeatability test"""
    weights = []
    equilibration_times = []
    iterations_list = []
    positions = []
    
    # Determine feedrate string for G-code
    feedrate_str = ""
    if feedrate is not None:
        feedrate_str = f" F{feedrate}"
    
    # Reset coordinate system for this trial
    machine.gcode("G92 X0 Y0 Z0 U0 V0 W0")
    machine.gcode("G91")
    time.sleep(0.5)
    
    for i in range(iterations):
        # Move W axis by 0.5mm with specified feedrate
        machine.gcode(f"G1 W0.5{feedrate_str}")
        time.sleep(2)  # Wait for movement to complete and settle
        
        # Take weight reading and measure equilibration time
        try:
            equilibration_start = time.perf_counter()
            weight = scale.get_weight(stable=True)
            equilibration_time = time.perf_counter() - equilibration_start
            
            weights.append(weight)
            equilibration_times.append(equilibration_time)
            iterations_list.append(i + 1)
            positions.append(0.5 * (i + 1))  # Cumulative position
            
            print(f"Iteration {i+1}/{iterations}: Position W={0.5*(i+1):.1f}mm, Weight={weight:.4f}g, Equilibration time={equilibration_time:.3f}s")
        except Exception as e:
            print(f"Error reading weight at iteration {i+1}: {e}")
            weights.append(np.nan)
            equilibration_times.append(np.nan)
            iterations_list.append(i + 1)
            positions.append(0.5 * (i + 1))
    
    return weights, equilibration_times, iterations_list, positions

def movement_repeatability_test(port, machine_address="192.168.1.2", iterations=100, feedrate=None):
    """Test movement repeatability by moving W axis and measuring weight changes (halting test) - runs 3 times"""
    scale = None
    machine = None
    all_trials_data = []  # Store data from all 3 trials
    
    try:
        print("Connecting to scale...")
        scale = Scale(port)
        scale.connect()
        print("Scale connected!")
        
        print("Connecting to Jubilee...")
        machine = Machine(address=machine_address)
        machine.connect()
        print("Jubilee connected!")
        
        # Determine feedrate string for display
        if feedrate is not None:
            print(f"\nUsing feedrate: F{feedrate}")
        else:
            print("\nUsing full speed (no feedrate limit)")
        
        # Run test 3 times
        for trial_num in range(1, 4):
            print("\n" + "="*60)
            print(f"TRIAL {trial_num} of 3")
            print("="*60)
            
            if trial_num == 1:
                print("\nPlace container on scale and press Enter...")
                input()
                print("Taring scale...")
                scale.tare()
                time.sleep(2)
            else:
                print("\nPrepare for next trial (refill reservoir, etc.) and press Enter when ready...")
                input()
                print("Taring scale...")
                scale.tare()
                time.sleep(2)
            
            print(f"\nStarting {iterations} movement cycles for trial {trial_num}...")
            print("This will move W axis by 0.5mm each iteration and record weight.\n")
            
            # Run single test
            weights, equilibration_times, iterations_list, positions = _run_single_movement_test(
                machine, scale, iterations, feedrate
            )
            
            all_trials_data.append({
                'trial': trial_num,
                'weights': weights,
                'equilibration_times': equilibration_times,
                'iterations': iterations_list,
                'positions': positions
            })
            
            print(f"\nTrial {trial_num} complete!")
        
        print("\n" + "="*60)
        print("All 3 Trials Complete - Generating Results")
        print("="*60)
        
        # Process and plot all trials
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        csv_filename = f"movement_repeatability_{timestamp}.csv"
        print(f"\nSaving data to CSV: {csv_filename}")
        
        # Save all trials to CSV
        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            # Write header
            writer.writerow(['Trial', 'Iteration', 'Position_W_mm', 'Weight_g', 'Equilibration_Time_s', 'Feedrate'])
            # Write data from all trials
            feedrate_val = feedrate if feedrate is not None else "full_speed"
            for trial_data in all_trials_data:
                for iter_num, pos, weight, eq_time in zip(
                    trial_data['iterations'], 
                    trial_data['positions'], 
                    trial_data['weights'], 
                    trial_data['equilibration_times']
                ):
                    writer.writerow([trial_data['trial'], iter_num, pos, weight, eq_time, feedrate_val])
        
        print(f"Data saved to: {csv_filename}")
        
        # Create graphs with all 3 trials
        print("\nGenerating graphs with all 3 trials...")
        
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 12))
        colors = ['b', 'g', 'r']
        
        # Graph 1: Weight over iterations (all trials)
        for idx, trial_data in enumerate(all_trials_data):
            valid_weights = [w for w in trial_data['weights'] if not np.isnan(w)]
            if valid_weights:
                ax1.plot(range(1, len(valid_weights)+1), valid_weights, 
                        f'{colors[idx]}-o', markersize=3, label=f'Trial {trial_data["trial"]}')
        
        ax1.set_xlabel('Iteration')
        ax1.set_ylabel('Weight (g)')
        ax1.set_title('Weight Measurements vs Movement Iterations (All Trials - Same Conditions)')
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        # Graph 2: Weight differences between consecutive readings (all trials)
        for idx, trial_data in enumerate(all_trials_data):
            valid_weights = [w for w in trial_data['weights'] if not np.isnan(w)]
            if len(valid_weights) > 1:
                differences = []
                for i in range(1, len(valid_weights)):
                    diff = valid_weights[i] - valid_weights[i-1]
                    differences.append(diff)
                if differences:
                    ax2.plot(range(1, len(differences)+1), differences, 
                            f'{colors[idx]}-o', markersize=3, label=f'Trial {trial_data["trial"]}')
        
        ax2.axhline(y=0, color='k', linestyle='-', alpha=0.3)
        ax2.set_xlabel('Movement Number')
        ax2.set_ylabel('Weight Change (g)')
        ax2.set_title('Weight Change Between Consecutive Movements (All Trials - Same Conditions)')
        ax2.grid(True, alpha=0.3)
        ax2.legend()
        
        # Graph 3: Equilibration times (all trials)
        for idx, trial_data in enumerate(all_trials_data):
            valid_equilibration_times = [t for t in trial_data['equilibration_times'] if not np.isnan(t)]
            if valid_equilibration_times:
                ax3.plot(range(1, len(valid_equilibration_times)+1), valid_equilibration_times, 
                        f'{colors[idx]}-o', markersize=3, label=f'Trial {trial_data["trial"]}')
        
        ax3.set_xlabel('Iteration')
        ax3.set_ylabel('Equilibration Time (s)')
        ax3.set_title('Scale Equilibration Time After Each Movement (All Trials - Same Conditions)')
        ax3.grid(True, alpha=0.3)
        ax3.legend()
        
        plt.tight_layout()
        
        # Save the figure
        png_filename = f"movement_repeatability_{timestamp}.png"
        plt.savefig(png_filename, dpi=150)
        print(f"Graph saved as: {png_filename}")
        
        # Calculate and print statistics for all trials
        print("\n" + "="*60)
        print("Summary Statistics (All Trials)")
        print("="*60)
        
        for trial_data in all_trials_data:
            valid_weights = [w for w in trial_data['weights'] if not np.isnan(w)]
            valid_equilibration_times = [t for t in trial_data['equilibration_times'] if not np.isnan(t)]
            
            if len(valid_weights) < 2:
                print(f"\nTrial {trial_data['trial']}: Insufficient valid weight readings.")
                continue
            
            differences = [valid_weights[i] - valid_weights[i-1] for i in range(1, len(valid_weights))]
            avg_difference = np.mean(differences)
            avg_equilibration_time = np.mean(valid_equilibration_times) if valid_equilibration_times else 0
            
            print(f"\nTrial {trial_data['trial']}:")
            print(f"  Initial weight: {valid_weights[0]:.4f} g")
            print(f"  Final weight: {valid_weights[-1]:.4f} g")
            print(f"  Total weight change: {valid_weights[-1] - valid_weights[0]:.4f} g")
            print(f"  Average weight change per movement: {avg_difference:.6f} g")
            print(f"  Average equilibration time: {avg_equilibration_time:.3f} s")
        
        # Show the plot
        plt.show()
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Return to absolute positioning and disconnect
        if machine:
            try:
                machine.gcode("G90")
            except:
                pass
            try:
                machine.disconnect()
            except:
                pass
        
        if scale:
            try:
                scale.disconnect()
            except:
                pass

def _run_single_spin_dispense_test(machine, scale, target_weight, feedrate):
    """Helper function to run a single spin-dispense test"""
    weights = []
    timestamps = []
    rotation_error = [None]  # Use list to allow modification in thread
    
    def rotation_thread():
        """Thread function to continuously rotate W axis"""
        try:
            # Use feedrate if specified, otherwise use default rotation speed
            if feedrate is not None:
                # Send a very long rotation command with specified feedrate
                # Rotate 36000 degrees (100 full rotations) - should be more than enough
                machine.gcode(f"G1 W36000 F{feedrate}")
            else:
                # Default rotation speed (full speed)
                rotation_speed = 3600  # degrees per minute (60 deg/s)
                machine.gcode(f"G1 W36000 F{rotation_speed}")
        except Exception as e:
            rotation_error[0] = e
    
    # Reset coordinate system for this trial
    machine.gcode("G92 X0 Y0 Z0 U0 V0 W0")
    machine.gcode("G91")
    time.sleep(0.5)
    
    # Read initial weight FIRST to establish baseline
    try:
        initial_weight = scale.get_weight(stable=False)
        weights.append(initial_weight)
        timestamps.append(0.0)
        print(f"Initial weight: {initial_weight:.4f}g")
    except Exception as e:
        print(f"Error reading initial weight: {e}")
        return None, None, None
    
    # Start timing AFTER initial weight reading
    start_time = time.perf_counter()
    
    # Start rotation in background thread
    rotation_thread_obj = threading.Thread(target=rotation_thread, daemon=True)
    rotation_thread_obj.start()
    
    # Give the movement command a moment to start
    time.sleep(0.2)
    
    # Continuously read weight while rotation is happening
    while True:
        # Check if rotation thread encountered an error
        if rotation_error[0] is not None:
            raise rotation_error[0]
        
        # Calculate elapsed time
        current_time = time.perf_counter() - start_time
        
        # Ensure monotonicity (prevent going back in time due to clock jitter)
        if timestamps and current_time <= timestamps[-1]:
            current_time = timestamps[-1] + 1e-6
        
        # Read weight without waiting for stabilization
        try:
            weight = scale.get_weight(stable=False)
            weights.append(weight)
            timestamps.append(current_time)
            
            weight_change = weight - initial_weight
            print(f"\rTime: {current_time:>6.2f}s | Weight: {weight:>8.4f}g | Change: {weight_change:>+8.4f}g | Target: {target_weight:.4f}g", 
                  end='', flush=True)
            
            # Check if target weight is reached
            if weight >= target_weight:
                print(f"\n\nTarget weight of {target_weight}g reached!")
                # Stop the rotation by sending M0 (pause)
                machine.gcode("M0")  # Pause print
                break
                
        except Exception as e:
            print(f"\nError reading weight: {e}")
            time.sleep(0.1)
            continue
        
        time.sleep(0.02)  # Fast sampling rate (50 Hz)
    
    return weights, timestamps, initial_weight

def spin_dispense_to_target_mode(port, machine_address="192.168.1.2", target_weight=0.5, feedrate=None):
    """Continuously spin W axis while recording weight until target weight is reached (continuous test) - runs 3 times"""
    scale = None
    machine = None
    all_trials_data = []  # Store data from all 3 trials
    
    try:
        print("Connecting to scale...")
        scale = Scale(port)
        scale.connect()
        print("Scale connected!")
        
        print("Connecting to Jubilee...")
        machine = Machine(address=machine_address)
        machine.connect()
        print("Jubilee connected!")
        
        # Display feedrate info
        if feedrate is not None:
            print(f"\nUsing feedrate: F{feedrate}")
        else:
            print("\nUsing full speed (default rotation speed)")
        
        # Run test 3 times
        for trial_num in range(1, 4):
            print("\n" + "="*60)
            print(f"TRIAL {trial_num} of 3")
            print("="*60)
            
            if trial_num == 1:
                print("\nPlace container on scale and press Enter...")
                input()
                print("Taring scale...")
                scale.tare()
                time.sleep(2)
            else:
                print("\nPrepare for next trial (refill reservoir, etc.) and press Enter when ready...")
                input()
                print("Taring scale...")
                scale.tare()
                time.sleep(2)
            
            print(f"\nStarting continuous W axis rotation until weight reaches {target_weight}g...")
            print("Press Ctrl+C to stop early.\n")
            
            # Run single test
            weights, timestamps, initial_weight = _run_single_spin_dispense_test(
                machine, scale, target_weight, feedrate
            )
            
            if weights is None or timestamps is None or initial_weight is None:
                print(f"Trial {trial_num} failed. Skipping...")
                continue
            
            all_trials_data.append({
                'trial': trial_num,
                'weights': weights,
                'timestamps': timestamps,
                'initial_weight': initial_weight
            })
            
            print(f"\nTrial {trial_num} complete!")
        
        if not all_trials_data:
            print("No successful trials completed.")
            return
        
        print("\n" + "="*60)
        print("All 3 Trials Complete - Generating Results")
        print("="*60)
        
        # Process and plot all trials
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        csv_filename = f"spin_dispense_{timestamp}.csv"
        print(f"\nSaving data to CSV: {csv_filename}")
        
        # Save all trials to CSV
        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            # Write header
            writer.writerow(['Trial', 'Time_s', 'Weight_g', 'Weight_Change_g', 'Feedrate', 'Target_Weight_g'])
            # Write data from all trials
            feedrate_val = feedrate if feedrate is not None else "full_speed"
            for trial_data in all_trials_data:
                initial_w = trial_data['initial_weight']
                for t, w in zip(trial_data['timestamps'], trial_data['weights']):
                    weight_change = w - initial_w
                    writer.writerow([trial_data['trial'], t, w, weight_change, feedrate_val, target_weight])
        
        print(f"Data saved to: {csv_filename}")
        
        # Create graphs with all 3 trials
        print("\nGenerating graphs with all 3 trials...")
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        colors = ['b', 'g', 'r']
        
        # Graph 1: Weight over time (all trials)
        for idx, trial_data in enumerate(all_trials_data):
            ax1.plot(trial_data['timestamps'], trial_data['weights'], 
                    f'{colors[idx]}-', linewidth=2, label=f'Trial {trial_data["trial"]}')
        
        ax1.set_xlabel('Time (s)')
        ax1.set_ylabel('Weight (g)')
        ax1.set_title(f'Weight vs Time - Continuous W Axis Rotation (Target: {target_weight}g) - All Trials - Same Conditions')
        ax1.grid(True, alpha=0.3)
        ax1.axhline(y=target_weight, color='r', linestyle='--', label=f'Target: {target_weight:.4f}g')
        ax1.legend()
        
        # Graph 2: Rate of weight change (derivative) for all trials
        for idx, trial_data in enumerate(all_trials_data):
            weights = trial_data['weights']
            timestamps = trial_data['timestamps']
            if len(weights) > 1:
                rates = []
                rate_times = []
                for i in range(1, len(weights)):
                    dt = timestamps[i] - timestamps[i-1]
                    if dt > 0:
                        dw = weights[i] - weights[i-1]
                        rate = dw / dt
                        rates.append(rate)
                        rate_times.append(timestamps[i])
                
                if rates:
                    ax2.plot(rate_times, rates, f'{colors[idx]}-', linewidth=1, alpha=0.7, 
                            label=f'Trial {trial_data["trial"]}')
        
        ax2.axhline(y=0, color='k', linestyle='-', alpha=0.3)
        ax2.set_xlabel('Time (s)')
        ax2.set_ylabel('Rate of Change (g/s)')
        ax2.set_title('Weight Change Rate Over Time (All Trials - Same Conditions)')
        ax2.grid(True, alpha=0.3)
        ax2.legend()
        
        plt.tight_layout()
        
        # Save the figure
        png_filename = f"spin_dispense_{timestamp}.png"
        plt.savefig(png_filename, dpi=150)
        print(f"Graph saved as: {png_filename}")
        
        # Calculate and print statistics for all trials
        print("\n" + "="*60)
        print("Summary Statistics (All Trials)")
        print("="*60)
        
        for trial_data in all_trials_data:
            weights = trial_data['weights']
            timestamps = trial_data['timestamps']
            initial_weight = trial_data['initial_weight']
            
            final_weight = weights[-1]
            total_change = final_weight - initial_weight
            duration = timestamps[-1]
            avg_rate = total_change / duration if duration > 0 else 0
            
            print(f"\nTrial {trial_data['trial']}:")
            print(f"  Duration: {duration:.2f} seconds")
            print(f"  Initial weight: {initial_weight:.4f} g")
            print(f"  Final weight: {final_weight:.4f} g")
            print(f"  Total weight change: {total_change:.4f} g")
            print(f"  Average rate: {avg_rate:.4f} g/s")
            print(f"  Total readings: {len(weights)}")
        
        # Show the plot
        plt.show()
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Return to absolute positioning and disconnect
        if machine:
            try:
                machine.gcode("G90")
            except:
                pass
            try:
                machine.disconnect()
            except:
                pass
        
        if scale:
            try:
                scale.disconnect()
            except:
                pass

def _run_single_target_weighing_test(machine, scale, target_weight, feedrate):
    """Helper function to run a single target weighing test with incremental dispensing"""
    weights = []
    equilibration_times = []
    iterations_list = []
    positions = []
    
    # Determine feedrate string for G-code
    feedrate_str = ""
    if feedrate is not None:
        feedrate_str = f" F{feedrate}"
    
    # Reset coordinate system for this trial
    machine.gcode("G92 X0 Y0 Z0 U0 V0 W0")
    machine.gcode("G91")
    time.sleep(0.5)
    
    current_position = 0.0
    iteration = 0
    threshold_90_percent = 0.9 * target_weight
    
    # Step size parameters
    max_step_size = 4  # Maximum step size when weight is very low
    min_step_size = 0.2  # Minimum step size when approaching 90% threshold
    feedback_step_size = 0.05
    
    # Track if we've crossed the threshold
    threshold_crossed = False
    
    print(f"Target: {target_weight:.4f}g, 90% threshold: {threshold_90_percent:.4f}g\n")
    
    while True:
        iteration += 1
        
        # Get current weight (unstable) to determine behavior
        current_weight = scale.get_weight(stable=False)
        
        if current_weight >= threshold_90_percent:
            # Above 90% threshold: feedback loop mode
            if not threshold_crossed:
                # First time crossing threshold - mark it
                threshold_crossed = True
                print(f"Crossed 90% threshold at {current_weight:.4f}g. Entering feedback loop mode.")
            
            # Keep vibration off
            # Move -> unstable weight -> move (feedback loop illusion)
            machine.gcode(f"G1 W{feedback_step_size} {feedrate_str}")
            machine.gcode("M400")
            time.sleep(0.2) # Small sleep to promote scale settling
            current_position += feedback_step_size
            
            # Get unstable weight reading (no stable measurement yet)
            try:
                unstable_weight = scale.get_weight(stable=False)
                print(f"Iteration {iteration}: Position W={current_position:.1f}mm, Unstable Weight={unstable_weight:.4f}g (feedback loop)")
                
                # Check if we're within 5% of target weight or above target
                threshold_95_percent = 0.99 * target_weight
                if unstable_weight >= threshold_95_percent:
                    # Wait 4 seconds to confirm we're actually over threshold
                    if unstable_weight >= target_weight:
                        print(f"Unstable weight {unstable_weight:.4f}g >= target {target_weight:.4f}g. Waiting 4 seconds for confirmation...")
                    else:
                        print(f"Unstable weight {unstable_weight:.4f}g is within 5% of target {target_weight:.4f}g (>= {threshold_95_percent:.4f}g). Waiting 4 seconds for confirmation...")
                    time.sleep(4.0)
                    
                    # Final stable measurement to confirm
                    equilibration_start = time.perf_counter()
                    final_weight = scale.get_weight(stable=True)
                    equilibration_time = time.perf_counter() - equilibration_start
                    
                    weights.append(final_weight)
                    equilibration_times.append(equilibration_time)
                    iterations_list.append(iteration)
                    positions.append(current_position)
                    
                    print(f"Final stable measurement: Weight={final_weight:.4f}g, Equilibration time={equilibration_time:.3f}s")
                    
                    # Check if stable weight is actually over threshold
                    if final_weight >= threshold_95_percent:
                        print(f"\nTarget weight of {target_weight:.4f}g reached!")
                        break
                    else:
                        # Stable weight is below threshold, restart trickling
                        print(f"Stable weight {final_weight:.4f}g is below threshold {threshold_95_percent:.4f}g. Restarting trickling...")
                        # Continue the loop to keep dispensing
                        continue
                    
            except Exception as e:
                print(f"Error reading weight at iteration {iteration}: {e}")
                # Continue the loop even if there's an error
                continue
        else:
            # Below 90% threshold: big movements with vibration, stable measurements after each
            # Linear decrease: step_size decreases smoothly as weight approaches 90% threshold
            progress = max(0, current_weight / threshold_90_percent)  # 0 to 1
            step_size = max_step_size - (max_step_size - min_step_size) * progress
            
            # Move with vibration
            machine.gcode("M42 P0 S0.10 F20000") # Turn on vibration
            time.sleep(0.33)
            machine.gcode(f"G1 W{step_size}{feedrate_str}")
            machine.gcode("M400")
            machine.gcode("M42 P0 S0.0 F20000") # Turn off vibration
            time.sleep(0.33)
            current_position += step_size
            
            # Take stabilized weight reading after big movement
            try:
                equilibration_start = time.perf_counter()
                weight = scale.get_weight(stable=True)
                equilibration_time = time.perf_counter() - equilibration_start
                
                weights.append(weight)
                equilibration_times.append(equilibration_time)
                iterations_list.append(iteration)
                positions.append(current_position)
                
                print(f"Iteration {iteration}: Position W={current_position:.1f}mm, Weight={weight:.4f}g, Equilibration time={equilibration_time:.3f}s, Step={step_size:.2f}mm")
                
            except Exception as e:
                print(f"Error reading weight at iteration {iteration}: {e}")
                weights.append(np.nan)
                equilibration_times.append(np.nan)
                iterations_list.append(iteration)
                positions.append(current_position)
    
    return weights, equilibration_times, iterations_list, positions

def target_weighing_mode(port, machine_address="192.168.1.2", target_weight=2.0, feedrate=None):
    """Incrementally dispense to target weight using adaptive step sizes - runs 10 times"""
    scale = None
    machine = None
    all_trials_data = []  # Store data from all 10 trials
    
    try:
        print("Connecting to scale...")
        scale = Scale(port)
        scale.connect()
        print("Scale connected!")
        
        print("Connecting to Jubilee...")
        machine = Machine(address=machine_address)
        machine.connect()
        print("Jubilee connected!")
        
        # Determine feedrate string for display
        if feedrate is not None:
            print(f"\nUsing feedrate: F{feedrate}")
        else:
            print("\nUsing full speed (no feedrate limit)")
        
        # Run test 10 times
        for trial_num in range(1, 11):
            print("\n" + "="*60)
            print(f"TRIAL {trial_num} of 10")
            print("="*60)
            
            if trial_num == 1:
                print("\nPlace container on scale and press Enter...")
                input()
                print("Taring scale...")
                # scale.tare()
                time.sleep(2)
            else:
                print("\nPrepare for next trial (empty container, etc.) and press Enter when ready...")
                input()
                print("Taring scale...")
                scale.tare()
                time.sleep(2)
            
            print(f"\nStarting target weighing to {target_weight}g for trial {trial_num}...")
            print("Will use W5 steps until 80%, then W0.5 steps.\n")
            
            # Run single test
            weights, equilibration_times, iterations_list, positions = _run_single_target_weighing_test(
                machine, scale, target_weight, feedrate
            )
            
            all_trials_data.append({
                'trial': trial_num,
                'weights': weights,
                'equilibration_times': equilibration_times,
                'iterations': iterations_list,
                'positions': positions
            })
            
            print(f"\nTrial {trial_num} complete!")
        
        print("\n" + "="*60)
        print("All 10 Trials Complete - Generating Results")
        print("="*60)
        
        # Process and plot all trials
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        csv_filename = f"target_weighing_{timestamp}.csv"
        print(f"\nSaving data to CSV: {csv_filename}")
        
        # Save all trials to CSV
        with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            # Write header
            writer.writerow(['Trial', 'Iteration', 'Position_W_mm', 'Weight_g', 'Equilibration_Time_s', 'Feedrate', 'Target_Weight_g'])
            # Write data from all trials
            feedrate_val = feedrate if feedrate is not None else "full_speed"
            for trial_data in all_trials_data:
                for iter_num, pos, weight, eq_time in zip(
                    trial_data['iterations'], 
                    trial_data['positions'], 
                    trial_data['weights'], 
                    trial_data['equilibration_times']
                ):
                    writer.writerow([trial_data['trial'], iter_num, pos, weight, eq_time, feedrate_val, target_weight])
        
        print(f"Data saved to: {csv_filename}")
        
        # Create graphs with all 10 trials
        print("\nGenerating graphs with all 10 trials...")
        
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 12))
        # Use colormap to generate distinct colors for 10 trials
        colors = plt.cm.tab10(np.linspace(0, 1, 10))
        
        # Graph 1: Weight over iterations (all trials)
        for idx, trial_data in enumerate(all_trials_data):
            valid_weights = [w for w in trial_data['weights'] if not np.isnan(w)]
            if valid_weights:
                ax1.plot(range(1, len(valid_weights)+1), valid_weights, 
                        '-o', color=colors[idx], markersize=3, label=f'Trial {trial_data["trial"]}')
        
        ax1.axhline(y=target_weight, color='red', linestyle='--', linewidth=2, label=f'Target: {target_weight:.4f}g')
        ax1.set_xlabel('Iteration')
        ax1.set_ylabel('Weight (g)')
        ax1.set_title(f'Target Weighing: Weight vs Iteration (Target: {target_weight}g) - All Trials - Same Conditions')
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        # Graph 2: Weight vs Position (all trials)
        for idx, trial_data in enumerate(all_trials_data):
            valid_weights = [w for w in trial_data['weights'] if not np.isnan(w)]
            valid_positions = [p for w, p in zip(trial_data['weights'], trial_data['positions']) if not np.isnan(w)]
            if valid_weights and valid_positions:
                ax2.plot(valid_positions, valid_weights, 
                        '-o', color=colors[idx], markersize=3, label=f'Trial {trial_data["trial"]}')
        
        ax2.axhline(y=target_weight, color='red', linestyle='--', linewidth=2, label=f'Target: {target_weight:.4f}g')
        ax2.set_xlabel('W Position (mm)')
        ax2.set_ylabel('Weight (g)')
        ax2.set_title(f'Target Weighing: Weight vs W Position - All Trials - Same Conditions')
        ax2.grid(True, alpha=0.3)
        ax2.legend()
        
        # Graph 3: Equilibration times (all trials)
        for idx, trial_data in enumerate(all_trials_data):
            valid_equilibration_times = [t for t in trial_data['equilibration_times'] if not np.isnan(t)]
            if valid_equilibration_times:
                ax3.plot(range(1, len(valid_equilibration_times)+1), valid_equilibration_times, 
                        '-o', color=colors[idx], markersize=3, label=f'Trial {trial_data["trial"]}')
        
        ax3.set_xlabel('Iteration')
        ax3.set_ylabel('Equilibration Time (s)')
        ax3.set_title('Scale Equilibration Time After Each Step - All Trials - Same Conditions')
        ax3.grid(True, alpha=0.3)
        ax3.legend()
        
        plt.tight_layout()
        
        # Save the figure
        png_filename = f"target_weighing_{timestamp}.png"
        plt.savefig(png_filename, dpi=150)
        print(f"Graph saved as: {png_filename}")
        
        # Calculate and print statistics for all trials
        print("\n" + "="*60)
        print("Summary Statistics (All Trials)")
        print("="*60)
        
        for trial_data in all_trials_data:
            valid_weights = [w for w in trial_data['weights'] if not np.isnan(w)]
            valid_equilibration_times = [t for t in trial_data['equilibration_times'] if not np.isnan(t)]
            
            if len(valid_weights) < 1:
                print(f"\nTrial {trial_data['trial']}: No valid weight readings.")
                continue
            
            final_weight = valid_weights[-1]
            iterations = len(valid_weights)
            avg_equilibration_time = np.mean(valid_equilibration_times) if valid_equilibration_times else 0
            
            print(f"\nTrial {trial_data['trial']}:")
            print(f"  Final weight: {final_weight:.4f} g")
            print(f"  Target weight: {target_weight:.4f} g")
            print(f"  Accuracy: {(final_weight/target_weight)*100:.2f}%")
            print(f"  Total iterations: {iterations}")
            print(f"  Average equilibration time: {avg_equilibration_time:.3f} s")
        
        # Show the plot
        plt.show()
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Return to absolute positioning and disconnect
        if machine:
            try:
                machine.gcode("G90")
            except:
                pass
            try:
                machine.disconnect()
            except:
                pass
        
        if scale:
            try:
                scale.disconnect()
            except:
                pass

def get_speed_selection():
    """Helper function to get speed selection from user"""
    print("\nSelect speed:")
    print("1. Full speed (no feedrate limit)")
    print("2. F200")
    print("3. F100")
    print("4. F50")
    choice = input("Enter 1, 2, 3, or 4 (default: 1): ").strip()
    
    if choice == "2":
        return 200
    elif choice == "3":
        return 100
    elif choice == "4":
        return 50
    else:
        return None  # Full speed

def main():
    port = input("Enter the serial port for the scale (default: /dev/ttyUSB0): ").strip()
    if not port:
        port = "/dev/ttyUSB0"
        print(f"Using default port: {port}")
    print("Select mode:")
    print("1. Listener mode (raw serial output)")
    print("2. Scale test mode (tare and weigh once)")
    print("3. Continuous weight mode (tare and continuous monitoring)")
    print("4. Movement repeatability test (Jubilee + scale)")
    print("5. Spin-dispense to target weight (continuous W axis rotation)")
    print("6. Target weighing mode (incremental dispensing to target weight)")
    mode = input("Enter 1, 2, 3, 4, 5, or 6: ").strip()
    if mode == "1":
        listener_mode(port)
    elif mode == "2":
        scale_test_mode(port)
    elif mode == "3":
        continuous_weight_mode(port)
    elif mode == "4":
        machine_address = input("Enter Jubilee IP address (default: 192.168.1.2): ").strip()
        if not machine_address:
            machine_address = "192.168.1.2"
        iterations_str = input("Enter number of iterations (default: 100): ").strip()
        iterations = int(iterations_str) if iterations_str else 100
        feedrate = get_speed_selection()
        movement_repeatability_test(port, machine_address, iterations, feedrate)
    elif mode == "5":
        machine_address = input("Enter Jubilee IP address (default: 192.168.1.2): ").strip()
        if not machine_address:
            machine_address = "192.168.1.2"
        target_weight_str = input("Enter target weight in grams (default: 0.5): ").strip()
        target_weight = float(target_weight_str) if target_weight_str else 0.5
        feedrate = get_speed_selection()
        spin_dispense_to_target_mode(port, machine_address, target_weight, feedrate)
    elif mode == "6":
        machine_address = input("Enter Jubilee IP address (default: 192.168.1.2): ").strip()
        if not machine_address:
            machine_address = "192.168.1.2"
        target_weight_str = input("Enter target weight in grams (default: 2.0): ").strip()
        target_weight = float(target_weight_str) if target_weight_str else 2.0
        feedrate = get_speed_selection()
        target_weighing_mode(port, machine_address, target_weight, feedrate)
    else:
        print("Invalid selection.")

if __name__ == "__main__":
    main()
