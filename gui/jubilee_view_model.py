"""
ViewModel for Jubilee Automation System.

This module provides the ViewModel layer in an MVVM-inspired architecture where
the ViewModel coordinates between the GUI and JubileeManager hardware layer.

The architecture follows:
    - Model: JubileeManager (hardware state and operations)
    - View: jubilee_gui.py (UI and user interaction)
    - ViewModel: This module (coordination and business logic)

The ViewModel drives the JubileeManager to execute operations systematically,
providing callbacks to update the GUI on progress and state changes.

Example:
    Basic usage of JubileeViewModel::
    
        from gui.jubilee_view_model import JubileeViewModel, DispensingJob
        
        # Create ViewModel with callbacks
        view_model = JubileeViewModel(
            on_status_changed=lambda s: print(s),
            on_job_progress=lambda c, t, w: print(f"{c}/{t}")
        )
        
        # Configure and connect
        view_model.set_hardware_config(num_dispensers=2, pistons_per_dispenser=10)
        view_model.connect()
        
        # Execute job
        jobs = [DispensingJob("A1", 50.0), DispensingJob("A2", 45.0)]
        view_model.start_job(jobs)
"""

import threading
import time
from typing import Callable, Optional, List, Dict
from dataclasses import dataclass
from pathlib import Path
import sys

# Add parent directory to path to import JubileeManager
sys.path.append(str(Path(__file__).parent.parent))
from src.JubileeManager import JubileeManager
from jubilee_api_config.constants import FeedRate


@dataclass
class DispensingJob:
    """Represents a single well in a dispensing job"""
    well_id: str
    target_weight: float
    current_weight: float = 0.0
    completed: bool = False
    error: Optional[str] = None


class JubileeViewModel:
    """
    ViewModel for coordinating GUI and JubileeManager.
    
    This class acts as the coordination layer between the View (GUI) and Model
    (JubileeManager). It drives the hardware through the JubileeManager while
    providing callbacks to update the GUI on progress and state changes.
    
    Responsibilities:
    - Manage connection to hardware via JubileeManager
    - Store and update hardware configuration (dispensers, pistons)
    - Execute dispensing jobs systematically
    - Provide progress updates via callbacks
    - Handle errors and provide meaningful feedback
    
    Example:
        ```python
        # Create ViewModel with callbacks
        view_model = JubileeViewModel(
            on_connection_changed=lambda connected: print(f"Connected: {connected}"),
            on_weight_changed=lambda weight: print(f"Weight: {weight}g"),
            on_status_changed=lambda status: print(status),
            on_job_progress=lambda completed, total, well: print(f"{completed}/{total}")
        )
        
        # Configure hardware
        view_model.set_hardware_config(num_dispensers=2, pistons_per_dispenser=10)
        
        # Connect to hardware
        if view_model.connect():
            # Start a job
            jobs = [
                DispensingJob("A1", 50.0),
                DispensingJob("A2", 45.0)
            ]
            view_model.start_job(jobs)
        ```
    """
    
    def __init__(
        self,
        on_connection_changed: Optional[Callable[[bool], None]] = None,
        on_weight_changed: Optional[Callable[[float], None]] = None,
        on_status_changed: Optional[Callable[[str], None]] = None,
        on_job_progress: Optional[Callable[[int, int, str], None]] = None,
        on_job_completed: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize the ViewModel.
        
        Args:
            on_connection_changed: Callback when connection state changes (connected: bool)
            on_weight_changed: Callback when scale weight updates (weight: float)
            on_status_changed: Callback when status message changes (status: str)
            on_job_progress: Callback for job progress (completed: int, total: int, current_well: str)
            on_job_completed: Callback when job finishes successfully
            on_error: Callback when an error occurs (error_message: str)
        """
        # Callbacks for GUI updates
        self._on_connection_changed = on_connection_changed
        self._on_weight_changed = on_weight_changed
        self._on_status_changed = on_status_changed
        self._on_job_progress = on_job_progress
        self._on_job_completed = on_job_completed
        self._on_error = on_error
        
        # Hardware configuration (stored in ViewModel, used by JubileeManager)
        self._num_dispensers: int = 2
        self._pistons_per_dispenser: int = 10
        self._feedrate: FeedRate = FeedRate.MEDIUM
        
        # JubileeManager instance (created on connect)
        self._jubilee_manager: Optional[JubileeManager] = None
        
        # Job state
        self._job_running: bool = False
        self._stop_job_flag: bool = False
        self._current_job: List[DispensingJob] = []
        self._job_thread: Optional[threading.Thread] = None
        
        # Weight monitoring
        self._weight_monitor_thread: Optional[threading.Thread] = None
        self._monitoring_weight: bool = False
        
        # Connection state
        self._connected: bool = False
    
    @property
    def connected(self) -> bool:
        """Check if connected to hardware"""
        return self._connected
    
    @property
    def job_running(self) -> bool:
        """Check if a job is currently running"""
        return self._job_running
    
    @property
    def num_dispensers(self) -> int:
        """Get current number of dispensers configured"""
        return self._num_dispensers
    
    @property
    def pistons_per_dispenser(self) -> int:
        """Get current number of pistons per dispenser configured"""
        return self._pistons_per_dispenser
    
    def set_hardware_config(
        self, 
        num_dispensers: int, 
        pistons_per_dispenser: int,
        feedrate: FeedRate = FeedRate.MEDIUM
    ) -> None:
        """
        Update hardware configuration.
        
        Sets the hardware configuration that will be used when connecting to
        the JubileeManager. Can only be called when not connected.
        
        Args:
            num_dispensers: Number of piston dispensers available
            pistons_per_dispenser: Number of pistons in each dispenser
            feedrate: Movement speed (SLOW, MEDIUM, FAST)
        
        Raises:
            RuntimeError: If called while connected to hardware
        """
        if self._connected:
            raise RuntimeError("Cannot change hardware config while connected")
        
        self._num_dispensers = num_dispensers
        self._pistons_per_dispenser = pistons_per_dispenser
        self._feedrate = feedrate
        
        self._notify_status(f"Hardware config updated: {num_dispensers} dispensers, "
                          f"{pistons_per_dispenser} pistons each")
    
    def connect(
        self,
        machine_address: Optional[str] = None,
        scale_port: str = "/dev/ttyUSB0"
    ) -> bool:
        """
        Connect to hardware using current configuration.
        
        Creates a JubileeManager with the current hardware configuration and
        connects to the Jubilee machine and scale. This is a blocking operation
        that can take 30-60 seconds due to homing.
        
        Args:
            machine_address: IP address of Jubilee (None = use config file)
            scale_port: Serial port for scale connection
        
        Returns:
            True if connection successful, False otherwise
        """
        if self._connected:
            self._notify_error("Already connected to hardware")
            return False
        
        try:
            self._notify_status("Connecting to hardware...")
            
            # Create JubileeManager with current configuration
            self._jubilee_manager = JubileeManager(
                num_piston_dispensers=self._num_dispensers,
                num_pistons_per_dispenser=self._pistons_per_dispenser,
                feedrate=self._feedrate
            )
            
            # Connect to hardware
            success = self._jubilee_manager.connect(
                machine_address=machine_address,
                scale_port=scale_port
            )
            
            if success:
                self._connected = True
                self._notify_connection_changed(True)
                self._notify_status("Connected to hardware")
                
                # Start weight monitoring
                self._start_weight_monitoring()
                return True
            else:
                self._notify_error("Failed to connect to hardware")
                self._notify_status("Connection failed")
                return False
                
        except Exception as e:
            self._notify_error(f"Connection error: {str(e)}")
            self._notify_status("Connection failed")
            return False
    
    def disconnect(self) -> None:
        """
        Disconnect from hardware and clean up resources.
        
        Stops any running jobs, stops weight monitoring, and disconnects
        from the JubileeManager.
        """
        if not self._connected:
            return
        
        try:
            # Stop any running job
            if self._job_running:
                self.stop_job()
            
            # Stop weight monitoring
            self._stop_weight_monitoring()
            
            # Disconnect from hardware
            if self._jubilee_manager:
                self._jubilee_manager.disconnect()
                self._jubilee_manager = None
            
            self._connected = False
            self._notify_connection_changed(False)
            self._notify_status("Disconnected from hardware")
            
        except Exception as e:
            self._notify_error(f"Disconnection error: {str(e)}")
    
    def get_current_weight(self) -> float:
        """
        Get current weight from scale.
        
        Returns:
            Current weight in grams, or 0.0 if not connected
        """
        if self._jubilee_manager and self._connected:
            return self._jubilee_manager.get_weight_unstable()
        return 0.0
    
    def start_job(self, jobs: List[DispensingJob]) -> bool:
        """
        Start a dispensing job with the given wells.
        
        Executes dispensing operations for each well in the job list,
        calling the progress callback after each well is completed.
        
        Args:
            jobs: List of DispensingJob objects specifying wells and target weights
        
        Returns:
            True if job started successfully, False if already running or not connected
        """
        if not self._connected:
            self._notify_error("Not connected to hardware")
            return False
        
        if self._job_running:
            self._notify_error("Job already running")
            return False
        
        if not jobs:
            self._notify_error("No wells to dispense")
            return False
        
        # Validate we have enough pistons
        total_pistons_needed = len(jobs)
        total_pistons_available = self._num_dispensers * self._pistons_per_dispenser
        if total_pistons_needed > total_pistons_available:
            self._notify_error(
                f"Not enough pistons: need {total_pistons_needed}, "
                f"have {total_pistons_available}"
            )
            return False
        
        # Reset job state
        self._current_job = jobs
        self._job_running = True
        self._stop_job_flag = False
        
        # Start job in background thread
        self._job_thread = threading.Thread(target=self._execute_job, daemon=True)
        self._job_thread.start()
        
        self._notify_status("Job started")
        return True
    
    def stop_job(self) -> None:
        """
        Stop the currently running job.
        
        Sets a flag to stop the job after the current well is completed.
        The job will not stop immediately.
        """
        if not self._job_running:
            return
        
        self._stop_job_flag = True
        self._notify_status("Stopping job...")
    
    def _execute_job(self) -> None:
        """
        Execute the dispensing job in background thread.
        
        This method runs in a separate thread to avoid blocking the GUI.
        It processes each well in the job list, updating progress after
        each well is completed.
        """
        try:
            total_wells = len(self._current_job)
            
            for i, job in enumerate(self._current_job):
                # Check for stop flag
                if self._stop_job_flag:
                    self._notify_status("Job stopped by user")
                    break
                
                # Update progress
                self._notify_job_progress(i, total_wells, job.well_id)
                self._notify_status(f"Processing well {job.well_id} ({i+1}/{total_wells})")
                
                # Execute dispensing operation
                try:
                    success = self._jubilee_manager.dispense_to_well(
                        job.well_id,
                        job.target_weight
                    )
                    
                    if success:
                        job.completed = True
                        job.current_weight = self._jubilee_manager.get_weight_stable()
                        self._notify_status(
                            f"Completed well {job.well_id}: {job.current_weight:.3f}g"
                        )
                    else:
                        job.error = "Dispensing operation failed"
                        self._notify_error(
                            f"Failed to dispense to well {job.well_id}"
                        )
                        break
                        
                except Exception as e:
                    job.error = str(e)
                    self._notify_error(
                        f"Error dispensing to well {job.well_id}: {str(e)}"
                    )
                    break
            
            # Job completed successfully
            if not self._stop_job_flag and all(job.completed for job in self._current_job):
                self._notify_status("Job completed successfully")
                self._notify_job_completed()
            
        except Exception as e:
            self._notify_error(f"Job execution error: {str(e)}")
            self._notify_status("Job failed")
        
        finally:
            self._job_running = False
    
    def _start_weight_monitoring(self) -> None:
        """Start background thread for weight monitoring"""
        self._monitoring_weight = True
        self._weight_monitor_thread = threading.Thread(
            target=self._weight_monitor_loop,
            daemon=True
        )
        self._weight_monitor_thread.start()
    
    def _stop_weight_monitoring(self) -> None:
        """Stop weight monitoring thread"""
        self._monitoring_weight = False
        if self._weight_monitor_thread:
            self._weight_monitor_thread.join(timeout=2.0)
    
    def _weight_monitor_loop(self) -> None:
        """Weight monitoring loop (runs in background thread)"""
        while self._monitoring_weight and self._connected:
            try:
                weight = self.get_current_weight()
                self._notify_weight_changed(weight)
                time.sleep(0.5)  # Update every 500ms
            except Exception as e:
                # Silently continue on weight read errors
                pass
    
    # Callback notification methods
    def _notify_connection_changed(self, connected: bool) -> None:
        """Notify GUI of connection state change"""
        if self._on_connection_changed:
            self._on_connection_changed(connected)
    
    def _notify_weight_changed(self, weight: float) -> None:
        """Notify GUI of weight change"""
        if self._on_weight_changed:
            self._on_weight_changed(weight)
    
    def _notify_status(self, status: str) -> None:
        """Notify GUI of status change"""
        if self._on_status_changed:
            self._on_status_changed(status)
    
    def _notify_job_progress(self, completed: int, total: int, current_well: str) -> None:
        """Notify GUI of job progress"""
        if self._on_job_progress:
            self._on_job_progress(completed, total, current_well)
    
    def _notify_job_completed(self) -> None:
        """Notify GUI that job completed successfully"""
        if self._on_job_completed:
            self._on_job_completed()
    
    def _notify_error(self, error_message: str) -> None:
        """Notify GUI of error"""
        if self._on_error:
            self._on_error(error_message)
    
    def get_dispenser_status(self) -> List[Dict[str, any]]:
        """
        Get status of all piston dispensers.
        
        Returns:
            List of dicts with dispenser information:
            - index: Dispenser index
            - pistons_remaining: Number of pistons left
        """
        if not self._connected or not self._jubilee_manager:
            return []
        
        status = []
        for dispenser in self._jubilee_manager.piston_dispensers:
            status.append({
                'index': dispenser.index,
                'pistons_remaining': dispenser.num_pistons
            })
        
        return status
    
    def update_dispenser_pistons(self, dispenser_index: int, num_pistons: int) -> bool:
        """
        Update the number of pistons in a specific dispenser.
        
        This allows the user to modify the piston count if they manually
        reload or change dispensers.
        
        Args:
            dispenser_index: Index of dispenser to update
            num_pistons: New number of pistons
        
        Returns:
            True if update successful, False if invalid index or not connected
        """
        if not self._connected or not self._jubilee_manager:
            self._notify_error("Not connected to hardware")
            return False
        
        try:
            dispensers = self._jubilee_manager.piston_dispensers
            if dispenser_index >= len(dispensers):
                self._notify_error(f"Invalid dispenser index: {dispenser_index}")
                return False
            
            dispenser = dispensers[dispenser_index]
            dispenser.num_pistons = num_pistons
            
            self._notify_status(
                f"Updated dispenser {dispenser_index} to {num_pistons} pistons"
            )
            return True
            
        except Exception as e:
            self._notify_error(f"Error updating dispenser: {str(e)}")
            return False
