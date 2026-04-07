"""
Shared data models for the Jubilee Automation server.

Imported by both server.py and hardware_manager.py so neither file depends
on the other at import time.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class MachineState(str, Enum):
    IDLE         = "idle"
    HOMING       = "homing"       # connection / homing in progress
    RUNNING      = "running"      # job executing
    ERROR        = "error"
    DISCONNECTED = "disconnected"


# =============================================================================
# Hardware configuration
# =============================================================================

class HardwareConfig(BaseModel):
    """Sent from the Settings screen when the user clicks Connect."""
    num_dispensers:        int           = Field(default=2,  ge=0)
    pistons_per_dispenser: int           = Field(default=10, ge=0)
    machine_address:       Optional[str] = None   # None → read from system_config.json
    scale_port:            str           = "/dev/ttyUSB0"


class DispenserStatus(BaseModel):
    index:             int
    pistons_remaining: int


# =============================================================================
# Job-progress state  (shared between server endpoints and hardware managers)
# =============================================================================

class JobProgress:
    def __init__(self) -> None:
        self.running:      bool          = False
        self.job_type:     Optional[str] = None
        self.completed:    int           = 0
        self.total:        int           = 0
        self.current_item: Optional[str] = None
        self.error:        Optional[str] = None
        self.started_at:   Optional[str] = None   # ISO-8601 UTC string
        self.items:        list          = []      # ordered list of item dicts from the job request

    def reset(self) -> None:
        self.__init__()

    def to_dict(self) -> dict:
        return {
            "running":      self.running,
            "job_type":     self.job_type,
            "completed":    self.completed,
            "total":        self.total,
            "current_item": self.current_item,
            "error":        self.error,
            "started_at":   self.started_at,
            "items":        self.items,
        }
