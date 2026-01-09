from typing import Union
from dataclasses import dataclass
import requests

from science_jubilee.labware.Labware import Well, WellSet

# TODO: x,y,z coordinates for mold slots need to be handled properly once their location is decided in hardware

@dataclass
class Mold(Well):
    """A wrapper class for Well that uses weight (in grams) instead of liquid volume.

    This class represents a mold that can hold powder and tracks weight instead of volume.
    """
    valid: bool = True           # Whether the mold should be used (e.g. contains a mold)
    has_top_piston: bool = False # Whether the mold has a top piston
    current_weight: float = 0.0  # Current weight in grams
    target_weight: float = 0.0   # Target weight in grams
    max_weight: float = None     # Maximum weight capacity in grams
    ready_pos: str = None        # State machine position name (e.g., "mold_ready_A1")
    
    @property
    def well_id(self) -> str:
        """Extract well_id from ready_pos by removing 'mold_ready_' prefix.
        
        Returns the identifier part (e.g., 'A1' from 'mold_ready_A1').
        If ready_pos is not set, returns the mold name.
        """
        if self.ready_pos:
            # Remove 'mold_ready_' prefix if present
            if self.ready_pos.startswith('mold_ready_'):
                return self.ready_pos.replace('mold_ready_', '', 1)
            return self.ready_pos
        # Fallback to name if ready_pos not set
        return self.name
    
    def add_weight(self, weight: float):
        """Add weight to the mold.
        
        :param weight: Weight to add in grams
        :type weight: float
        """
        if self.max_weight is not None:
            if self.current_weight + weight > self.max_weight:
                raise ValueError(f"Adding {weight}g would exceed max weight of {self.max_weight}g")
        self.current_weight += weight
    
    def remove_weight(self, weight: float):
        """Remove weight from the mold.
        
        :param weight: Weight to remove in grams
        :type weight: float
        """
        if self.current_weight - weight < 0:
            raise ValueError(f"Removing {weight}g would result in negative weight")
        self.current_weight -= weight
    
    def set_weight(self, weight: float):
        """Set the current weight of the mold.
        
        :param weight: New weight in grams
        :type weight: float
        """
        if self.max_weight is not None and weight > self.max_weight:
            raise ValueError(f"Weight {weight}g exceeds max weight of {self.max_weight}g")
        self.current_weight = weight
    
    def get_weight(self) -> float:
        """Get the current weight of the mold.
        
        :return: Current weight in grams
        :rtype: float
        """
        return self.current_weight

@dataclass(repr=False)
class MoldSet(WellSet):
    """A wrapper class for WellSet that works with Mold objects.
    
    This class allows for weight-based operations on sets of molds.
    Use the name of the Mold to access the Mold object, just like the WellSet class.
    """
    
    def __getitem__(self, id_: Union[str, int]):
        """Override to return Mold objects."""
        try:
            if isinstance(id_, slice):
                well_list = []
                start = id_.start
                stop = id_.stop
                if id_.step is not None:
                    step = id_.step
                else:
                    step = 1
                for sub_id in range(start, stop, step):
                    well_list.append(self.wells[sub_id])
                return well_list
            else:
                return self.wells[id_]
        except KeyError:
            return list(self.wells.values())[id_] 
            