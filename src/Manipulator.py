from science_jubilee.tools.Tool import (
    Tool,
    ToolConfigurationError,
    ToolStateError as _ExternalToolStateError,
)
from src.trickler_labware import Mold
from src.PistonDispenser import PistonDispenser
import time
from typing import List, Optional, Dict, Any, Union
from pathlib import Path
import json
import os
from src.ConfigLoader import config
from functools import wraps

# Re-export ToolStateError for documentation purposes
class ToolStateError(_ExternalToolStateError):
    """
    Exception raised when a tool operation is attempted in an invalid state.
    
    This error is raised when trying to perform operations that require
    specific tool or payload states that are not currently met.
    
    Examples:
        - Attempting to pick a mold when already holding one
        - Trying to place a mold when not holding one
        - Operating at wrong position for the requested action
    """
    pass

def requires_safe_z_manipulator(func):
    """
    Decorator for Manipulator methods that require safe Z height.
    Assumes the decorated method belongs to a class with:
    - self.machine_connection (Machine object)
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.machine_connection:
            raise RuntimeError("Machine connection not available")
        
        # Get current Z position
        current_z = float(self.machine_connection.get_position()["Z"])
        
        # Get safe Z height from config
        safe_z = config.get_safe_z()
        
        # Move to safe height if needed
        if current_z < safe_z:
            safe_height = safe_z + config.get_safe_z_offset()
            self.machine_connection.move_to(z=safe_height)
        
        return func(self, *args, **kwargs)
    
    return wrapper

def requires_carrying_mold(func):
    """
    Decorator for methods that require carrying a mold.
    Checks that self.current_well is not None.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.current_well is None:
            raise ToolStateError("Must be carrying a mold to perform this operation.")
        return func(self, *args, **kwargs)
    
    return wrapper

def requires_not_carrying_mold(func):
    """
    Decorator for methods that require NOT carrying a mold.
    Checks that self.current_well is None.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.current_well is not None:
            raise ToolStateError("Already carrying a mold. Place current mold before performing this operation.")
        return func(self, *args, **kwargs)
    
    return wrapper

def requires_mold_without_piston(func):
    """
    Decorator for methods that require the current mold to not have a top piston.
    Checks that self.current_well.has_top_piston is False.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.current_well is None:
            raise ToolStateError("Must be carrying a mold to perform this operation.")
        if self.current_well.has_top_piston:
            raise ToolStateError("Cannot perform operation on mold that already has a top piston.")
        return func(self, *args, **kwargs)
    
    return wrapper

def requires_valid_mold(func):
    """
    Decorator for methods that require a valid mold parameter.
    Checks that the first argument (mold) is valid.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if args and hasattr(args[0], 'valid'):
            mold = args[0]
            if not mold.valid:
                raise ToolStateError("Cannot perform operation on an invalid mold.")
        return func(self, *args, **kwargs)
    
    return wrapper

def requires_machine_connection(func):
    """
    Decorator for methods that require a machine connection.
    Checks that self.machine_connection is available.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.machine_connection:
            raise RuntimeError("Machine connection not available for this operation.")
        return func(self, *args, **kwargs)
    
    return wrapper

# Error checks have been moved into decorators above

class Manipulator(Tool):
    """
    Jubilee toolhead for mold handling and tamping operations.
    Tracks a Mold object representing the current mold being carried.
    
    State tracking:
    - current_well: Mold object representing the current mold (None if not carrying one)
    - The Mold object tracks has_top_piston, valid, weight, and other mold properties
    
    Operations:
    - Tamping: Only allowed when carrying a mold without a top piston
    - Top piston placement: Only allowed when carrying a mold without a top piston
    - Mold handling: Pick up and place Mold objects

    Tamping is primarily controlled using sensorless homing/stall detection, which is configured
    using the M915 command in config.g and homet.g, not this file. driver-stall.g is used to 
    control tamping after contact with the material.
    """

    # ============================================================================
    # CONFIGURATION PARAMETERS
    # ============================================================================
    # NOTE: The tamper axis letter is configured via self.tamper_axis (default 'V')
    # in __init__. Changing self.tamper_axis will update all axis references 
    # throughout this class, including gcode commands.
    # ============================================================================
    
 
    def __init__(self, index, name, state_machine=None, config_source=None):
        super().__init__(index, name)
        self.state_machine = state_machine  # Reference to MotionPlatformStateMachine
        
        # Tamper axis configuration (loaded from system_config.json)
        self.tamper_axis = 'V'  # Default axis for tamper movement
        
        # Status flags
        self.stall_detection_configured = False
        self.sensorless_homing_configured = False
        
        # TODO: tamper_speed should be derived from state machine feedrate default
        # For now, removed as it was only used in get_status() for reporting

        
        # Load configuration from system_config.json if not provided
        if config_source is None:
            config_source = "system_config"
        
        config_dict = self._load_config(config_source)
        if config_dict:
            self._load_manipulator_config(config_dict)

    def _load_config(self, config_source_param: Union[str, Dict[str, Any], None]) -> Optional[Dict[str, Any]]:
        """
        Load configuration from either a file path string or a dict.
        
        Args:
            config_source_param: Either a string (path to JSON file) or a dict (already loaded config)
            
        Returns:
            Configuration dictionary, or None if loading failed
        """
        if isinstance(config_source_param, dict):
            # Config is already a dictionary
            return config_source_param
        elif isinstance(config_source_param, str):
            # Config is a file path - load from JSON
            try:
                # Get project root (parent of src directory)
                project_root = Path(__file__).parent.parent
                # Try as path relative to jubilee_api_config
                config_path = project_root / "jubilee_api_config" / f"{config_source_param}.json"
                if not config_path.exists():
                    # Try as absolute or relative path as-is
                    config_path = Path(config_source_param)
                    if not config_path.suffix == '.json':
                        config_path = Path(f"{config_source_param}.json")
                
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except FileNotFoundError:
                raise FileNotFoundError("Could not find Manipulator configuration file")
            except json.JSONDecodeError as e:
                raise(f"Error: Invalid JSON in manipulator config file: {config_path}")
                print(f"JSON Error: {e}")
                raise json.JSONDecodeError("")
            except Exception as e:
                print(f"Error loading manipulator config: {e}")
                raise Exception()
                return None
        else:
            print(f"Warning: Invalid config type: {type(config_source_param)}. Expected str or dict.")
            print("Exiting program.")
            exit()
    
    def _load_manipulator_config(self, config_data: Dict[str, Any]):
        """Load manipulator-specific configuration from config dict (only tamper_axis)."""
        manipulator_config = config_data.get('manipulator', {})
        
        # Only load tamper axis
        self.tamper_axis = manipulator_config.get('tamper_axis', self.tamper_axis)
    
    def _get_config_dict(self) -> Dict[str, Any]:
        """
        Helper to package manipulator configuration for state machine calls.
        
        Note: Only returns tamper_axis now. State machine should provide:
        - tamper_travel_pos (from motion_platform_positions.json z_heights)
        - safe_z (from motion_platform_positions.json z_heights)
        - dispenser_safe_z (from motion_platform_positions.json z_heights)
        """
        return {
            'tamper_axis': self.tamper_axis,
        }
    
    @property
    def machine(self):
        """Access to machine through state machine for read-only queries."""
        if self.state_machine:
            return self.state_machine.machine
        return None
    
    @property
    def current_well(self):
        """Access to current well through state machine."""
        if self.state_machine:
            return self.state_machine.context.current_well
        return None
    
    @property
    def placed_mold_on_scale(self):
        """Access to mold_on_scale state through state machine."""
        if self.state_machine:
            return self.state_machine.context.mold_on_scale
        return False

    def home_tamper(self, machine_connection: Optional[Any] = None):
        """
        Perform sensorless homing for the tamper axis.
        
        Validates and executes through MotionPlatformStateMachine.
        
        Args:
            machine_connection: Deprecated parameter (for backward compatibility)
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        # Validate and execute through state machine
        result = self.state_machine.validated_home_tamper(
            tamper_axis=self.tamper_axis
        )
        
        if not result.valid:
            raise RuntimeError(f"Tamper homing failed: {result.reason}")

    # TODO: Figure out how to merge stall detection with this function so that we can handle stall detection gracefully
    @requires_carrying_mold
    @requires_mold_without_piston
    def tamp(self, target_depth: float = None):
        """
        Perform tamping action. Only allowed if carrying a mold without a top piston.
        
        Args:
            target_depth: Target depth to tamp to (mm). If None, uses default depth.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        if not self.placed_mold_on_scale:
            raise ToolStateError("Cannot tamp, no mold on scale.")
        
        # Call state machine method which validates and executes
        result = self.state_machine.validated_tamp(
            manipulator_config=self._get_config_dict()
        )
        
        if not result.valid:
            raise ToolStateError(f"Cannot tamp: {result.reason}")
        
        return True

    def vibrate_tamper(self, machine_connection=None):
        # TODO: Update when vibration functionality added
        pass

    def get_status(self) -> Dict[str, Any]:
        """
        Get current manipulator status and configuration.
        
        Returns:
            Dictionary containing manipulator status information
        """
        status = {
            'has_mold': self.current_well is not None,
            'stall_detection_configured': self.stall_detection_configured,
            'sensorless_homing_configured': self.sensorless_homing_configured,
            'tamper_axis': self.tamper_axis,
        }
        
        if self.current_well is not None:
            status['current_well'] = {
                'name': getattr(self.current_well, 'name', 'unnamed'),
                'has_top_piston': self.current_well.has_top_piston,
                'valid': self.current_well.valid,
                'current_weight': self.current_well.current_weight,
                'target_weight': self.current_well.target_weight,
                'max_weight': self.current_well.max_weight
            }
        else:
            status['current_well'] = None
            
        return status

    def get_current_mold(self) -> Optional[Mold]:
        """
        Get the current mold being carried.
        
        Returns:
            Mold object if carrying a mold, None otherwise
        """
        return self.current_well

    def is_carrying_mold(self) -> bool:
        """
        Check if the manipulator is currently carrying a mold.
        
        Returns:
            True if carrying a mold, False otherwise
        """
        return self.current_well is not None

    def pick_mold(self, well_id: str):
        """
        Pick up mold from mold slot.
        
        Assumes toolhead is directly above the mold slot at safe_z height with tamper axis in travel position.
        Validates move through state machine before execution.
        
        Args:
            well_id: Mold slot identifier (numerical string "0" through "17")
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        result = self.state_machine.validated_pick_mold(
            well_id=well_id,
            manipulator_config=self._get_config_dict()
        )
        
        if not result.valid:
            raise ToolStateError(f"Cannot pick mold: {result.reason}")

    def place_mold(self, well_id: str) -> Optional[Mold]:
        """
        Place down the current mold and return it.
        
        Assumes toolhead is directly above the mold slot at safe_z height with tamper axis in travel position.
        Validates move through state machine before execution.
        
        Args:
            well_id: Mold slot identifier (e.g., "A1")
        
        Returns:
            The Mold object that was placed, or None if no mold was being carried
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        mold_to_place = self.current_well
        result = self.state_machine.validated_place_mold(
            well_id=well_id,
            manipulator_config=self._get_config_dict()
        )
        
        if not result.valid:
            raise ToolStateError(f"Cannot place mold: {result.reason}")
        
        return mold_to_place

    def place_top_piston(self, piston_dispenser: PistonDispenser):
        """
        Place the top piston on the current mold. Only allowed if carrying a mold without a top piston.
        
        Assumes toolhead is at dispenser position.
        Validates move through state machine before execution.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        # Call state machine method which validates and executes
        result = self.state_machine.validated_place_top_piston(
            piston_dispenser=piston_dispenser,
            manipulator_config=self._get_config_dict()
        )
        
        if not result.valid:
            raise ToolStateError(f"Cannot place top piston: {result.reason}")
        
        return True

    def place_mold_on_scale(self):
        """
        Place the current mold on the scale. Only allowed if carrying a mold without a top piston.
        
        Validates move through state machine before execution.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        # Call state machine method which validates and executes
        result = self.state_machine.validated_place_mold_on_scale(
            manipulator_config=self._get_config_dict()
        )
        
        if not result.valid:
            raise ToolStateError(f"Cannot place mold on scale: {result.reason}")
        
        return True

    def pick_mold_from_scale(self):
        """
        Pick up the current mold from the scale. Only allowed if carrying a mold without a top piston.
        
        Validates move through state machine before execution.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        # Call state machine method which validates and executes
        result = self.state_machine.validated_pick_mold_from_scale(
            manipulator_config=self._get_config_dict()
        )
        
        if not result.valid:
            raise ToolStateError(f"Cannot pick mold from scale: {result.reason}")
        
        return True
