from science_jubilee.tools.Tool import (
    Tool,
    ToolConfigurationError,
    ToolStateError as _ExternalToolStateError,
)
from src.trickler_labware import Mold
from src.PistonDispenser import PistonDispenser
import time
from typing import Optional, Dict, Any, Union
from pathlib import Path
import json

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
    def current_well(self):
        """Access to current well through state machine."""
        if self.state_machine:
            return self.state_machine.context.current_well
        return None

    def home_tamper(self, machine_connection: Optional[Any] = None):
        """
        Perform homing for the tamper axis (V-axis).
        
        Can be performed while holding a mold WITHOUT a top piston. The homing 
        process uses the mold itself as a reference:
        - Start position: v=2 (tamper inserted into mold)
        - End position: v=-7 (tamper touching bottom of mold)
        
        This allows accurate positioning establishment using the mold as a reference.
        
        Validates and executes through MotionPlatformStateMachine.
        
        Args:
            machine_connection: Deprecated parameter (for backward compatibility)
            
        Note:
            Do not home when the mold has a top piston inserted.
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        # Validate and execute through state machine
        result = self.state_machine.validated_home_tamper(
            tamper_axis=self.tamper_axis
        )
        
        if not result.valid:
            raise RuntimeError(f"Tamper homing failed: {result.reason}")

    def tamp(self, tamp_depth: float = 40.0, tamp_speed: int = 2000):
        """
        Perform tamping action to compress powder in the held mold.
        
        Tamping reduces powder volume for two purposes:
        1. Allowing the top piston to fit in the mold if it otherwise wouldn't
        2. Reducing the amount of powder that becomes airborne when the top piston is inserted
        
        Only allowed if carrying a mold without a top piston. Typically performed at
        the scale_ready position after filling the mold with powder.
        
        After tamping, the V axis is automatically re-homed to ensure axis accuracy.
        
        Args:
            tamp_depth: Target depth for tamping movement in mm (default 40.0)
            tamp_speed: Speed for tamping movement in mm/min (default 2000)
            
        Returns:
            True if successful
            
        Raises:
            RuntimeError: If state machine not configured
            ToolStateError: If tamping is not allowed in current state or parameters out of bounds
            
        Note:
            Valid parameter ranges are defined in system_config.json under manipulator settings:
            - tamp_depth_min/tamp_depth_max (default: 10-60 mm)
            - tamp_speed_min/tamp_speed_max (default: 500-5000 mm/min)
        """
        if not self.state_machine:
            raise RuntimeError("State machine not configured")
        
        # Call state machine method which validates and executes
        result = self.state_machine.validated_tamp(
            manipulator_config=self._get_config_dict(),
            tamp_depth=tamp_depth,
            tamp_speed=tamp_speed
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
            well_id: Mold slot identifier using numerical indexing (e.g., "0", "1", "2")
        
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
