"""
Scale and trickler test script.

Connects to the SIR scale and optionally the Jubilee machine for trickler
experiments. Mode 6 runs the production trickler loop using trickler settings
from ``api_config/system_config.json``, with unstable weight reads in
coarse phase and stable reads in fine phase (no SIR streaming).
"""

import sys
import time
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ConfigLoader import config
from src.MovementExecutor import MovementExecutor
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
                line = ser.readline().decode("ascii", errors="ignore").rstrip()
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
                print(f"\rCurrent weight: {weight:>10.4f} g", end="", flush=True)
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

            print(
                f"Iteration {i + 1}/{iterations}: Position W={0.5 * (i + 1):.1f}mm, Weight={weight:.4f}g, Equilibration time={equilibration_time:.3f}s"
            )
        except Exception as e:
            print(f"Error reading weight at iteration {i + 1}: {e}")
            weights.append(np.nan)
            equilibration_times.append(np.nan)
            iterations_list.append(i + 1)
            positions.append(0.5 * (i + 1))

    return weights, equilibration_times, iterations_list, positions


def movement_repeatability_test(
    port, machine_address="192.168.1.2", iterations=100, feedrate=None
):
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
            print("\n" + "=" * 60)
            print(f"TRIAL {trial_num} of 3")
            print("=" * 60)

            if trial_num == 1:
                print("\nPlace container on scale and press Enter...")
                input()
                print("Taring scale...")
                scale.tare()
                time.sleep(2)
            else:
                print(
                    "\nPrepare for next trial (refill reservoir, etc.) and press Enter when ready..."
                )
                input()
                print("Taring scale...")
                scale.tare()
                time.sleep(2)

            print(f"\nStarting {iterations} movement cycles for trial {trial_num}...")
            print("This will move W axis by 0.5mm each iteration and record weight.\n")

            # Run single test
            weights, equilibration_times, iterations_list, positions = (
                _run_single_movement_test(machine, scale, iterations, feedrate)
            )

            all_trials_data.append(
                {
                    "trial": trial_num,
                    "weights": weights,
                    "equilibration_times": equilibration_times,
                    "iterations": iterations_list,
                    "positions": positions,
                }
            )

            print(f"\nTrial {trial_num} complete!")

        print("\n" + "=" * 60)
        print("All 3 Trials Complete - Generating Results")
        print("=" * 60)

        # Process and plot all trials
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        csv_filename = f"movement_repeatability_{timestamp}.csv"
        print(f"\nSaving data to CSV: {csv_filename}")

        # Save all trials to CSV
        with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            # Write header
            writer.writerow(
                [
                    "Trial",
                    "Iteration",
                    "Position_W_mm",
                    "Weight_g",
                    "Equilibration_Time_s",
                    "Feedrate",
                ]
            )
            # Write data from all trials
            feedrate_val = feedrate if feedrate is not None else "full_speed"
            for trial_data in all_trials_data:
                for iter_num, pos, weight, eq_time in zip(
                    trial_data["iterations"],
                    trial_data["positions"],
                    trial_data["weights"],
                    trial_data["equilibration_times"],
                ):
                    writer.writerow(
                        [
                            trial_data["trial"],
                            iter_num,
                            pos,
                            weight,
                            eq_time,
                            feedrate_val,
                        ]
                    )

        print(f"Data saved to: {csv_filename}")

        # Create graphs with all 3 trials
        print("\nGenerating graphs with all 3 trials...")

        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 12))
        colors = ["b", "g", "r"]

        # Graph 1: Weight over iterations (all trials)
        for idx, trial_data in enumerate(all_trials_data):
            valid_weights = [w for w in trial_data["weights"] if not np.isnan(w)]
            if valid_weights:
                ax1.plot(
                    range(1, len(valid_weights) + 1),
                    valid_weights,
                    f"{colors[idx]}-o",
                    markersize=3,
                    label=f"Trial {trial_data['trial']}",
                )

        ax1.set_xlabel("Iteration")
        ax1.set_ylabel("Weight (g)")
        ax1.set_title(
            "Weight Measurements vs Movement Iterations (All Trials - Same Conditions)"
        )
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        # Graph 2: Weight differences between consecutive readings (all trials)
        for idx, trial_data in enumerate(all_trials_data):
            valid_weights = [w for w in trial_data["weights"] if not np.isnan(w)]
            if len(valid_weights) > 1:
                differences = []
                for i in range(1, len(valid_weights)):
                    diff = valid_weights[i] - valid_weights[i - 1]
                    differences.append(diff)
                if differences:
                    ax2.plot(
                        range(1, len(differences) + 1),
                        differences,
                        f"{colors[idx]}-o",
                        markersize=3,
                        label=f"Trial {trial_data['trial']}",
                    )

        ax2.axhline(y=0, color="k", linestyle="-", alpha=0.3)
        ax2.set_xlabel("Movement Number")
        ax2.set_ylabel("Weight Change (g)")
        ax2.set_title(
            "Weight Change Between Consecutive Movements (All Trials - Same Conditions)"
        )
        ax2.grid(True, alpha=0.3)
        ax2.legend()

        # Graph 3: Equilibration times (all trials)
        for idx, trial_data in enumerate(all_trials_data):
            valid_equilibration_times = [
                t for t in trial_data["equilibration_times"] if not np.isnan(t)
            ]
            if valid_equilibration_times:
                ax3.plot(
                    range(1, len(valid_equilibration_times) + 1),
                    valid_equilibration_times,
                    f"{colors[idx]}-o",
                    markersize=3,
                    label=f"Trial {trial_data['trial']}",
                )

        ax3.set_xlabel("Iteration")
        ax3.set_ylabel("Equilibration Time (s)")
        ax3.set_title(
            "Scale Equilibration Time After Each Movement (All Trials - Same Conditions)"
        )
        ax3.grid(True, alpha=0.3)
        ax3.legend()

        plt.tight_layout()

        # Save the figure
        png_filename = f"movement_repeatability_{timestamp}.png"
        plt.savefig(png_filename, dpi=150)
        print(f"Graph saved as: {png_filename}")

        # Calculate and print statistics for all trials
        print("\n" + "=" * 60)
        print("Summary Statistics (All Trials)")
        print("=" * 60)

        for trial_data in all_trials_data:
            valid_weights = [w for w in trial_data["weights"] if not np.isnan(w)]
            valid_equilibration_times = [
                t for t in trial_data["equilibration_times"] if not np.isnan(t)
            ]

            if len(valid_weights) < 2:
                print(
                    f"\nTrial {trial_data['trial']}: Insufficient valid weight readings."
                )
                continue

            differences = [
                valid_weights[i] - valid_weights[i - 1]
                for i in range(1, len(valid_weights))
            ]
            avg_difference = np.mean(differences)
            avg_equilibration_time = (
                np.mean(valid_equilibration_times) if valid_equilibration_times else 0
            )

            print(f"\nTrial {trial_data['trial']}:")
            print(f"  Initial weight: {valid_weights[0]:.4f} g")
            print(f"  Final weight: {valid_weights[-1]:.4f} g")
            print(
                f"  Total weight change: {valid_weights[-1] - valid_weights[0]:.4f} g"
            )
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
            print(
                f"\rTime: {current_time:>6.2f}s | Weight: {weight:>8.4f}g | Change: {weight_change:>+8.4f}g | Target: {target_weight:.4f}g",
                end="",
                flush=True,
            )

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


def spin_dispense_to_target_mode(
    port, machine_address="192.168.1.2", target_weight=0.5, feedrate=None
):
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
            print("\n" + "=" * 60)
            print(f"TRIAL {trial_num} of 3")
            print("=" * 60)

            if trial_num == 1:
                print("\nPlace container on scale and press Enter...")
                input()
                print("Taring scale...")
                scale.tare()
                time.sleep(2)
            else:
                print(
                    "\nPrepare for next trial (refill reservoir, etc.) and press Enter when ready..."
                )
                input()
                print("Taring scale...")
                scale.tare()
                time.sleep(2)

            print(
                f"\nStarting continuous W axis rotation until weight reaches {target_weight}g..."
            )
            print("Press Ctrl+C to stop early.\n")

            # Run single test
            weights, timestamps, initial_weight = _run_single_spin_dispense_test(
                machine, scale, target_weight, feedrate
            )

            if weights is None or timestamps is None or initial_weight is None:
                print(f"Trial {trial_num} failed. Skipping...")
                continue

            all_trials_data.append(
                {
                    "trial": trial_num,
                    "weights": weights,
                    "timestamps": timestamps,
                    "initial_weight": initial_weight,
                }
            )

            print(f"\nTrial {trial_num} complete!")

        if not all_trials_data:
            print("No successful trials completed.")
            return

        print("\n" + "=" * 60)
        print("All 3 Trials Complete - Generating Results")
        print("=" * 60)

        # Process and plot all trials
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        csv_filename = f"spin_dispense_{timestamp}.csv"
        print(f"\nSaving data to CSV: {csv_filename}")

        # Save all trials to CSV
        with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            # Write header
            writer.writerow(
                [
                    "Trial",
                    "Time_s",
                    "Weight_g",
                    "Weight_Change_g",
                    "Feedrate",
                    "Target_Weight_g",
                ]
            )
            # Write data from all trials
            feedrate_val = feedrate if feedrate is not None else "full_speed"
            for trial_data in all_trials_data:
                initial_w = trial_data["initial_weight"]
                for t, w in zip(trial_data["timestamps"], trial_data["weights"]):
                    weight_change = w - initial_w
                    writer.writerow(
                        [
                            trial_data["trial"],
                            t,
                            w,
                            weight_change,
                            feedrate_val,
                            target_weight,
                        ]
                    )

        print(f"Data saved to: {csv_filename}")

        # Create graphs with all 3 trials
        print("\nGenerating graphs with all 3 trials...")

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
        colors = ["b", "g", "r"]

        # Graph 1: Weight over time (all trials)
        for idx, trial_data in enumerate(all_trials_data):
            ax1.plot(
                trial_data["timestamps"],
                trial_data["weights"],
                f"{colors[idx]}-",
                linewidth=2,
                label=f"Trial {trial_data['trial']}",
            )

        ax1.set_xlabel("Time (s)")
        ax1.set_ylabel("Weight (g)")
        ax1.set_title(
            f"Weight vs Time - Continuous W Axis Rotation (Target: {target_weight}g) - All Trials - Same Conditions"
        )
        ax1.grid(True, alpha=0.3)
        ax1.axhline(
            y=target_weight,
            color="r",
            linestyle="--",
            label=f"Target: {target_weight:.4f}g",
        )
        ax1.legend()

        # Graph 2: Rate of weight change (derivative) for all trials
        for idx, trial_data in enumerate(all_trials_data):
            weights = trial_data["weights"]
            timestamps = trial_data["timestamps"]
            if len(weights) > 1:
                rates = []
                rate_times = []
                for i in range(1, len(weights)):
                    dt = timestamps[i] - timestamps[i - 1]
                    if dt > 0:
                        dw = weights[i] - weights[i - 1]
                        rate = dw / dt
                        rates.append(rate)
                        rate_times.append(timestamps[i])

                if rates:
                    ax2.plot(
                        rate_times,
                        rates,
                        f"{colors[idx]}-",
                        linewidth=1,
                        alpha=0.7,
                        label=f"Trial {trial_data['trial']}",
                    )

        ax2.axhline(y=0, color="k", linestyle="-", alpha=0.3)
        ax2.set_xlabel("Time (s)")
        ax2.set_ylabel("Rate of Change (g/s)")
        ax2.set_title("Weight Change Rate Over Time (All Trials - Same Conditions)")
        ax2.grid(True, alpha=0.3)
        ax2.legend()

        plt.tight_layout()

        # Save the figure
        png_filename = f"spin_dispense_{timestamp}.png"
        plt.savefig(png_filename, dpi=150)
        print(f"Graph saved as: {png_filename}")

        # Calculate and print statistics for all trials
        print("\n" + "=" * 60)
        print("Summary Statistics (All Trials)")
        print("=" * 60)

        for trial_data in all_trials_data:
            weights = trial_data["weights"]
            timestamps = trial_data["timestamps"]
            initial_weight = trial_data["initial_weight"]

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


def _print_trickler_config() -> None:
    """Print trickler settings loaded from system_config.json."""
    coarse_pct = config.get_trickler_coarse_threshold_pct()
    finish_pct = config.get_trickler_finish_threshold_pct()
    print("\nTrickler settings (from system_config.json):")
    print(f"  flow_ema_alpha:             {config.get_trickler_flow_ema_alpha()}")
    print(f"  yield_ema_alpha:            {config.get_trickler_yield_ema_alpha()}")
    print(f"  jam_yield_threshold:        {config.get_trickler_jam_yield_threshold()}")
    print(f"  jam_iter_threshold:         {config.get_trickler_jam_iter_threshold()}")
    print(f"  max_step_size_mm:           {config.get_trickler_max_step_size_mm()}")
    print(f"  min_step_size_mm:           {config.get_trickler_min_step_size_mm()}")
    print(f"  warmup_steps:               {config.get_trickler_warmup_steps()}")
    print(f"  warmup_max_step_mm:         {config.get_trickler_warmup_max_step_mm()}")
    print(f"  coarse_threshold_pct:       {coarse_pct}")
    print(f"  finish_threshold_pct:       {finish_pct}")
    print(f"  coarse_target_steps:        {config.get_trickler_coarse_target_steps()}")
    print(f"  coarse_feedrate:            {config.get_trickler_coarse_feedrate()}")
    print(f"  fine_feedrate:              {config.get_trickler_fine_feedrate()}")
    print(
        f"  coarse_vibration_amplitude: {config.get_trickler_coarse_vibration_amplitude()}"
    )
    print(
        f"  fine_vibration_amplitude:   {config.get_trickler_fine_vibration_amplitude()}"
    )
    print(f"  max_dribble_step_mm:        {config.get_trickler_max_dribble_step_mm()}")


def _make_jam_callback(
    executor: MovementExecutor,
    scale: Scale,
    target_weight: float,
    log_weight,
):
    """Return a callback that clears jams via coarse vibration and weight monitoring."""
    coarse_vib_amp = config.get_trickler_coarse_vibration_amplitude()
    jam_stop_threshold = 0.9 * target_weight
    jam_vib_duration_s = 5.0

    def on_jam_detected() -> None:
        print("\n" + "=" * 60)
        print("POWDER JAM DETECTED")
        print(
            f"Running coarse vibration recovery for up to {jam_vib_duration_s:.0f}s "
            f"(stop early if weight >= {jam_stop_threshold:.4f} g)"
        )
        print("=" * 60)

        executor._set_trickler_vibration(coarse_vib_amp)
        recovery_start = time.perf_counter()

        try:
            while time.perf_counter() - recovery_start < jam_vib_duration_s:
                weight = scale.get_weight(stable=False)
                log_weight(
                    weight,
                    event="jam_recovery_sample",
                    phase="jam",
                    stable=False,
                )
                elapsed = time.perf_counter() - recovery_start
                print(
                    f"\r[Jam] Recovery: t={elapsed:.1f}s weight={weight:.4f}g "
                    f"(stop at {jam_stop_threshold:.4f}g)",
                    end="",
                    flush=True,
                )
                if weight >= jam_stop_threshold:
                    print(
                        f"\n[Jam] Weight reached 90% of target ({weight:.4f}g) - "
                        "stopping vibration early"
                    )
                    break
                time.sleep(0.1)
            else:
                print(f"\n[Jam] Recovery duration complete ({jam_vib_duration_s:.0f}s)")
        finally:
            executor._set_trickler_vibration(0.0)

        executor.clear_jam()

    return on_jam_detected


def _execute_fill_powder_polling(
    executor: MovementExecutor, target_weight: float
) -> tuple[bool, list[dict]]:
    """Run the production trickler loop using stable/unstable scale polling."""
    machine = executor._machine
    scale = executor._scale
    weight_log: list[dict] = []
    fill_start = time.perf_counter()

    def log_weight(
        weight: float,
        *,
        event: str,
        phase: str,
        stable: bool,
        iteration: int | None = None,
        step_mm: float | None = None,
    ) -> None:
        weight_log.append(
            {
                "iteration": step_count if iteration is None else iteration,
                "time_s": time.perf_counter() - fill_start,
                "weight_g": weight,
                "phase": phase,
                "event": event,
                "stable": stable,
                "step_mm": step_mm,
            }
        )

    flow_alpha = config.get_trickler_flow_ema_alpha()
    yield_alpha = config.get_trickler_yield_ema_alpha()
    jam_threshold = config.get_trickler_jam_yield_threshold()
    jam_iter_limit = config.get_trickler_jam_iter_threshold()
    max_step = config.get_trickler_max_step_size_mm()
    min_step = config.get_trickler_min_step_size_mm()
    warmup_steps = config.get_trickler_warmup_steps()
    warmup_max_step = config.get_trickler_warmup_max_step_mm()
    coarse_pct = config.get_trickler_coarse_threshold_pct()
    finish_pct = config.get_trickler_finish_threshold_pct()
    coarse_tgt_steps = config.get_trickler_coarse_target_steps()
    coarse_feedrate = config.get_trickler_coarse_feedrate()
    fine_feedrate = config.get_trickler_fine_feedrate()
    coarse_vib_amp = config.get_trickler_coarse_vibration_amplitude()
    fine_vib_amp = config.get_trickler_fine_vibration_amplitude()
    max_dribble_step = config.get_trickler_max_dribble_step_mm()

    coarse_feedrate_str = f"F{coarse_feedrate}"
    fine_feedrate_str = f"F{fine_feedrate}"
    coarse_threshold = coarse_pct * target_weight
    finish_threshold = finish_pct * target_weight

    executor._on_jam_detected = _make_jam_callback(
        executor, scale, target_weight, log_weight
    )

    try:
        machine.gcode("M400")

        scale.tare()
        initial_weight = scale.get_weight(stable=True)
        log_weight(
            initial_weight,
            event="initial_after_tare",
            phase="coarse",
            stable=True,
            iteration=0,
        )
        print(f"[Fill] Initial weight after tare: {initial_weight:.4f}g")
        print(
            f"[Fill] Target: {target_weight:.4f}g  coarse: {coarse_threshold:.4f}g  "
            f"finish: {finish_threshold:.4f}g"
        )

        machine.gcode("G92 W0")
        machine.gcode("G91")

        current_vib_amp = coarse_vib_amp
        executor._set_trickler_vibration(current_vib_amp)

        flow_ema = 0.0
        yield_ema = 0.0
        step_count = 0
        stagnant_count = 0
        motor_has_moved = False
        threshold_crossed = False

        while True:
            if threshold_crossed:
                current_weight = scale.get_weight(stable=True)
                log_weight(
                    current_weight,
                    event="loop_sample",
                    phase="fine",
                    stable=True,
                )
                print(f"[FillTrace] stable sample: weight={current_weight:.4f}")
            else:
                current_weight = scale.get_weight(stable=False)
                log_weight(
                    current_weight,
                    event="loop_sample",
                    phase="coarse",
                    stable=False,
                )
                print(f"[FillTrace] unstable sample: weight={current_weight:.4f}")

            if current_weight >= coarse_threshold:
                if not threshold_crossed:
                    threshold_crossed = True
                    current_vib_amp = fine_vib_amp
                    print(
                        f"[Fill] Coarse threshold crossed at {current_weight:.4f}g"
                    )
                    executor._set_trickler_vibration(current_vib_amp)
                    time.sleep(0.15)
                    current_weight = scale.get_weight(stable=True)
                    log_weight(
                        current_weight,
                        event="coarse_threshold_crossed",
                        phase="fine",
                        stable=True,
                    )
                    print(
                        f"[FillTrace] stable sample after coarse crossing: "
                        f"weight={current_weight:.4f}"
                    )

                remaining = max(0.0, finish_threshold - current_weight)
                if yield_ema > 0 and remaining > 0:
                    step_size = remaining / yield_ema
                else:
                    step_size = min_step
                step_size = max(min_step, min(max_dribble_step, step_size))

                weight_before_step = current_weight
                print(
                    "[FillTrace] fine step command: "
                    f"step_mm={step_size:.4f}, feedrate={fine_feedrate}"
                )
                machine.gcode(f"G1 W{step_size:.4f} {fine_feedrate_str}")
                machine.gcode("M400")
                motor_has_moved = True

                weight_after_step = scale.get_weight(stable=True)
                log_weight(
                    weight_after_step,
                    event="after_fine_step",
                    phase="fine",
                    stable=True,
                    step_mm=step_size,
                )
                print(
                    f"[FillTrace] stable sample after fine step: "
                    f"weight={weight_after_step:.4f}"
                )
                weight_gained = max(0.0, weight_after_step - weight_before_step)
                step_yield = weight_gained / step_size

                flow_ema = flow_alpha * step_yield + (1 - flow_alpha) * flow_ema
                yield_ema = yield_alpha * step_yield + (1 - yield_alpha) * yield_ema
                step_count += 1

                if flow_ema < jam_threshold:
                    stagnant_count += 1
                else:
                    stagnant_count = 0
                if stagnant_count >= jam_iter_limit:
                    executor._handle_jam()
                    stagnant_count = 0
                    flow_ema = 0.0
                    yield_ema = 0.0
                    executor._set_trickler_vibration(current_vib_amp)
                    continue

                current_weight = weight_after_step

                if current_weight >= finish_threshold:
                    executor._set_trickler_vibration(0.0)
                    time.sleep(4)
                    final_weight = scale.get_weight(stable=True)
                    log_weight(
                        final_weight,
                        event="final_confirmation",
                        phase="fine",
                        stable=True,
                    )
                    print(f"[Fill] Stable confirmation: {final_weight:.4f}g")
                    if final_weight >= finish_threshold:
                        print(f"[Fill] Target reached: {final_weight:.4f}g")
                        executor.last_fill_weight = final_weight
                        return True, weight_log
                    print(
                        f"[Fill] Stable weight {final_weight:.4f}g below threshold, "
                        "continuing..."
                    )
                    executor._set_trickler_vibration(current_vib_amp)

            else:
                if step_count < warmup_steps or yield_ema == 0.0:
                    progress = max(0.0, current_weight / coarse_threshold)
                    step_size = max_step - (max_step - min_step) * progress
                    step_size = min(
                        step_size,
                        warmup_max_step if step_count < warmup_steps else max_step,
                    )
                else:
                    target_remaining = coarse_threshold - current_weight
                    step_size = target_remaining / (yield_ema * coarse_tgt_steps)
                    step_size = max(min_step, min(max_step, step_size))

                weight_before_step = current_weight
                print(
                    "[FillTrace] coarse step command: "
                    f"step_mm={step_size:.4f}, feedrate={coarse_feedrate}"
                )
                machine.gcode(f"G1 W{step_size:.4f} {coarse_feedrate_str}")
                machine.gcode("M400")
                motor_has_moved = True

                weight_after_step = scale.get_weight(stable=False)
                log_weight(
                    weight_after_step,
                    event="after_coarse_step",
                    phase="coarse",
                    stable=False,
                    step_mm=step_size,
                )
                print(
                    f"[FillTrace] unstable sample after coarse step: "
                    f"weight={weight_after_step:.4f}"
                )
                weight_gained = max(0.0, weight_after_step - weight_before_step)
                step_yield = weight_gained / step_size

                flow_ema = flow_alpha * step_yield + (1 - flow_alpha) * flow_ema
                yield_ema = yield_alpha * step_yield + (1 - yield_alpha) * yield_ema
                step_count += 1

                if motor_has_moved and step_count > warmup_steps:
                    if flow_ema < jam_threshold:
                        stagnant_count += 1
                    else:
                        stagnant_count = 0
                    if stagnant_count >= jam_iter_limit:
                        executor._handle_jam()
                        stagnant_count = 0
                        flow_ema = 0.0
                        yield_ema = 0.0
                        executor._set_trickler_vibration(current_vib_amp)

        return True, weight_log

    except Exception as e:
        print(f"[Fill] Error filling mold with powder: {e}")
        return False, weight_log
    finally:
        try:
            executor._set_trickler_vibration(0.0)
            machine.gcode("G90")
        except Exception:
            pass


def execute_fill_powder_mode(
    port: str,
    machine_address: str,
    target_weight: float,
    num_trials: int = 3,
) -> None:
    """Run production trickling via MovementExecutor.execute_fill_powder."""
    scale = None
    machine = None
    all_trials_data = []

    coarse_pct = config.get_trickler_coarse_threshold_pct()
    finish_pct = config.get_trickler_finish_threshold_pct()
    weight_tolerance = config.get_weight_tolerance()
    coarse_threshold = coarse_pct * target_weight
    finish_threshold = finish_pct * target_weight

    try:
        _print_trickler_config()
        print(f"\nTarget weight: {target_weight:.4f} g")
        print(f"  Coarse threshold ({coarse_pct:.0%}): {coarse_threshold:.4f} g")
        print(f"  Finish threshold ({finish_pct:.0%}): {finish_threshold:.4f} g")
        print(f"  Weight tolerance: {weight_tolerance:.4f} g")

        print("\nConnecting to scale...")
        scale = Scale(port)
        scale.connect()
        print("Scale connected!")

        print(f"Connecting to Jubilee at {machine_address}...")
        machine = Machine(address=machine_address)
        machine.connect()
        print("Jubilee connected!")

        executor = MovementExecutor(machine, scale)

        for trial_num in range(1, num_trials + 1):
            print("\n" + "=" * 60)
            print(f"TRIAL {trial_num} of {num_trials}")
            print("=" * 60)

            if trial_num == 1:
                print("\nPlace container on scale and press Enter...")
            else:
                print(
                    "\nPrepare for next trial (empty container, refill hopper, etc.) "
                    "and press Enter when ready..."
                )
            input()

            print(
                f"\nStarting execute_fill_powder to {target_weight:.4f} g "
                f"(trial {trial_num})..."
            )
            print("Press Ctrl+C to abort.\n")

            start_time = time.perf_counter()
            success, weight_log = _execute_fill_powder_polling(executor, target_weight)
            duration = time.perf_counter() - start_time
            final_weight = executor.last_fill_weight

            if not success or final_weight is None:
                print(f"\nTrial {trial_num} failed.")
                all_trials_data.append(
                    {
                        "trial": trial_num,
                        "success": False,
                        "final_weight": None,
                        "error_g": None,
                        "duration_s": duration,
                        "weight_log": weight_log,
                    }
                )
                continue

            error_g = final_weight - target_weight
            within_tolerance = abs(error_g) <= weight_tolerance

            all_trials_data.append(
                {
                    "trial": trial_num,
                    "success": True,
                    "final_weight": final_weight,
                    "error_g": error_g,
                    "duration_s": duration,
                    "within_tolerance": within_tolerance,
                    "weight_log": weight_log,
                }
            )

            print(f"\nTrial {trial_num} complete!")
            print(f"  Final weight: {final_weight:.4f} g")
            print(f"  Target:       {target_weight:.4f} g")
            print(f"  Error:        {error_g:+.4f} g")
            print(f"  Duration:     {duration:.2f} s")
            print(
                f"  Within tolerance ({weight_tolerance:.4f} g): "
                f"{'yes' if within_tolerance else 'no'}"
            )

        successful_trials = [t for t in all_trials_data if t["success"]]
        if not successful_trials:
            print("\nNo successful trials completed.")
            return

        print("\n" + "=" * 60)
        print("All Trials Complete - Summary")
        print("=" * 60)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        csv_filename = f"execute_fill_powder_{timestamp}.csv"
        print(f"\nSaving results to CSV: {csv_filename}")

        with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(
                [
                    "Trial",
                    "Success",
                    "Target_Weight_g",
                    "Final_Weight_g",
                    "Error_g",
                    "Duration_s",
                    "Within_Tolerance",
                    "Coarse_Threshold_g",
                    "Finish_Threshold_g",
                ]
            )
            for trial_data in all_trials_data:
                writer.writerow(
                    [
                        trial_data["trial"],
                        trial_data["success"],
                        target_weight,
                        trial_data["final_weight"],
                        trial_data["error_g"],
                        trial_data["duration_s"],
                        trial_data.get("within_tolerance", False),
                        coarse_threshold,
                        finish_threshold,
                    ]
                )

        print(f"Data saved to: {csv_filename}")

        iteration_csv_filename = f"execute_fill_powder_iterations_{timestamp}.csv"
        print(f"Saving iteration log to CSV: {iteration_csv_filename}")

        with open(iteration_csv_filename, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(
                [
                    "Trial",
                    "Iteration",
                    "Time_s",
                    "Weight_g",
                    "Phase",
                    "Event",
                    "Stable",
                    "Step_mm",
                ]
            )
            for trial_data in all_trials_data:
                for entry in trial_data.get("weight_log", []):
                    writer.writerow(
                        [
                            trial_data["trial"],
                            entry["iteration"],
                            f"{entry['time_s']:.4f}",
                            f"{entry['weight_g']:.6f}",
                            entry["phase"],
                            entry["event"],
                            entry["stable"],
                            "" if entry["step_mm"] is None else f"{entry['step_mm']:.4f}",
                        ]
                    )

        print(f"Iteration log saved to: {iteration_csv_filename}")

        errors = [t["error_g"] for t in successful_trials]
        durations = [t["duration_s"] for t in successful_trials]
        final_weights = [t["final_weight"] for t in successful_trials]

        print(f"\nSuccessful trials: {len(successful_trials)} / {num_trials}")
        print(f"  Mean final weight: {np.mean(final_weights):.4f} g")
        print(f"  Mean error:        {np.mean(errors):+.4f} g")
        print(f"  Std dev error:     {np.std(errors):.4f} g")
        print(f"  Mean duration:     {np.mean(durations):.2f} s")

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

        trial_nums = [t["trial"] for t in successful_trials]
        ax1.bar(trial_nums, final_weights, color="steelblue", alpha=0.8)
        ax1.axhline(
            y=target_weight,
            color="red",
            linestyle="--",
            linewidth=2,
            label=f"Target: {target_weight:.4f} g",
        )
        ax1.axhline(
            y=finish_threshold,
            color="orange",
            linestyle=":",
            linewidth=1,
            label=f"Finish threshold: {finish_threshold:.4f} g",
        )
        ax1.set_xlabel("Trial")
        ax1.set_ylabel("Final Weight (g)")
        ax1.set_title("execute_fill_powder Final Weights (top 40% zoom)")
        weight_zoom_bottom = target_weight * 0.6
        weight_zoom_top = max(*final_weights, target_weight, finish_threshold) * 1.002
        ax1.set_ylim(weight_zoom_bottom, weight_zoom_top)
        ax1.grid(True, alpha=0.3)
        ax1.legend()

        ax2.bar(trial_nums, errors, color="seagreen", alpha=0.8)
        ax2.axhline(y=0, color="k", linestyle="-", alpha=0.3)
        ax2.axhline(
            y=weight_tolerance,
            color="red",
            linestyle="--",
            linewidth=1,
            label=f"+/- tolerance: {weight_tolerance:.4f} g",
        )
        ax2.axhline(y=-weight_tolerance, color="red", linestyle="--", linewidth=1)
        ax2.set_xlabel("Trial")
        ax2.set_ylabel("Error (g)")
        ax2.set_title("Weight Error vs Target")
        ax2.grid(True, alpha=0.3)
        ax2.legend()

        plt.tight_layout()
        png_filename = f"execute_fill_powder_{timestamp}.png"
        plt.savefig(png_filename, dpi=150)
        print(f"Graph saved as: {png_filename}")

        fig_time, ax_time = plt.subplots(figsize=(12, 6))
        colors = plt.cm.tab10(np.linspace(0, 1, max(len(successful_trials), 1)))

        for idx, trial_data in enumerate(successful_trials):
            weight_log = trial_data.get("weight_log", [])
            if not weight_log:
                continue
            times = [entry["time_s"] for entry in weight_log]
            weights = [entry["weight_g"] for entry in weight_log]
            ax_time.plot(
                times,
                weights,
                "-o",
                color=colors[idx],
                markersize=3,
                linewidth=1.5,
                label=f"Trial {trial_data['trial']}",
            )

        ax_time.axhline(
            y=target_weight,
            color="red",
            linestyle="--",
            linewidth=2,
            label=f"Target: {target_weight:.4f} g",
        )
        ax_time.axhline(
            y=finish_threshold,
            color="orange",
            linestyle=":",
            linewidth=1,
            label=f"Finish threshold: {finish_threshold:.4f} g",
        )
        ax_time.set_xlabel("Time (s)")
        ax_time.set_ylabel("Weight (g)")
        ax_time.set_title("Weight vs Time During Fill (each trial)")
        all_logged_weights = [
            entry["weight_g"]
            for trial_data in successful_trials
            for entry in trial_data.get("weight_log", [])
        ]
        weight_zoom_bottom = target_weight * 0.6
        weight_zoom_top = (
            max(
                max(all_logged_weights) if all_logged_weights else target_weight,
                target_weight,
                finish_threshold,
            )
            * 1.002
        )
        ax_time.set_ylim(weight_zoom_bottom, weight_zoom_top)
        ax_time.grid(True, alpha=0.3)
        ax_time.legend()
        plt.tight_layout()
        time_png_filename = f"execute_fill_powder_weight_vs_time_{timestamp}.png"
        fig_time.savefig(time_png_filename, dpi=150)
        print(f"Weight vs time graph saved as: {time_png_filename}")
        plt.show()

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback

        traceback.print_exc()
    finally:
        if machine:
            try:
                machine.gcode("G90")
            except Exception:
                pass
            try:
                machine.disconnect()
            except Exception:
                pass

        if scale:
            try:
                scale.disconnect()
            except Exception:
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
    default_port = config.get_scale_port()
    default_ip = config.get_duet_ip()

    port = input(
        f"Enter the serial port for the scale (default: {default_port}): "
    ).strip()
    if not port:
        port = default_port
        print(f"Using default port: {port}")
    print("Select mode:")
    print("1. Listener mode (raw serial output)")
    print("2. Scale test mode (tare and weigh once)")
    print("3. Continuous weight mode (tare and continuous monitoring)")
    print("4. Movement repeatability test (Jubilee + scale)")
    print("5. Spin-dispense to target weight (continuous W axis rotation)")
    print(
        "6. Production trickler test (execute_fill_powder via system_config.json)"
    )
    mode = input("Enter 1, 2, 3, 4, 5, or 6: ").strip()
    if mode == "1":
        listener_mode(port)
    elif mode == "2":
        scale_test_mode(port)
    elif mode == "3":
        continuous_weight_mode(port)
    elif mode == "4":
        machine_address = input(
            f"Enter Jubilee IP address (default: {default_ip}): "
        ).strip()
        if not machine_address:
            machine_address = default_ip
        iterations_str = input("Enter number of iterations (default: 100): ").strip()
        iterations = int(iterations_str) if iterations_str else 100
        feedrate = get_speed_selection()
        movement_repeatability_test(port, machine_address, iterations, feedrate)
    elif mode == "5":
        machine_address = input(
            f"Enter Jubilee IP address (default: {default_ip}): "
        ).strip()
        if not machine_address:
            machine_address = default_ip
        target_weight_str = input(
            "Enter target weight in grams (default: 0.5): "
        ).strip()
        target_weight = float(target_weight_str) if target_weight_str else 0.5
        feedrate = get_speed_selection()
        spin_dispense_to_target_mode(port, machine_address, target_weight, feedrate)
    elif mode == "6":
        machine_address = input(
            f"Enter Jubilee IP address (default: {default_ip}): "
        ).strip()
        if not machine_address:
            machine_address = default_ip
        target_weight_str = input(
            "Enter target weight in grams (default: 0.5): "
        ).strip()
        target_weight = float(target_weight_str) if target_weight_str else 0.5
        trials_str = input("Enter number of trials (default: 3): ").strip()
        num_trials = int(trials_str) if trials_str else 3
        execute_fill_powder_mode(
            port, machine_address, target_weight, num_trials=num_trials
        )
    else:
        print("Invalid selection.")


if __name__ == "__main__":
    main()
