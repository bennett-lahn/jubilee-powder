"""
Shared data models for the Jubilee Automation server.

Imported by both ``server.py`` and ``hardware_manager.py`` so neither file
depends on the other at import time. All Pydantic models here are used for
request validation and serialisation; ``JobProgress`` is a plain Python class
shared as mutable state between server endpoints and the hardware manager.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class MachineState(str, Enum):
    """String enum representing the five possible hardware states.

    Serialised as a lowercase string in WebSocket telemetry frames and REST
    responses so the React frontend can compare states without importing this
    enum.
    """

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
    num_dispensers:        int           = Field(default=1, ge=0)
    pistons_per_dispenser: int           = Field(default=2, ge=0)
    machine_address:       Optional[str] = None   # None → read from system_config.json
    scale_port:            str           = "/dev/ttyUSB0"


class DispenserStatus(BaseModel):
    """Per-dispenser status reported in telemetry frames and REST responses."""

    index:             int
    pistons_remaining: int


# =============================================================================
# Job-progress state  (shared between server endpoints and hardware managers)
# =============================================================================

class JobProgress:
    """Mutable in-memory job state shared between server endpoints and the hardware manager.

    A single instance is created at module level in ``server.py`` and passed by
    reference to the hardware manager's ``run_dispensing_job`` /
    ``run_hardness_job`` methods so that both the job loop and REST endpoints
    can read and mutate progress atomically.

    Attributes:
        running: ``True`` while the job loop is executing.
        job_type: ``"dispensing"`` or ``"hardness"``, set at job start.
        completed: Number of wells/samples successfully processed.
        total: Total wells/samples in the current job.
        current_item: ID of the well/sample currently being processed.
        error: Error message string if the job failed, otherwise ``None``.
        started_at: ISO-8601 UTC timestamp set when the job starts.
        items: Ordered list of item dicts from the original job request.
    """

    def __init__(self) -> None:
        self.running:      bool          = False
        self.job_type:     Optional[str] = None
        self.completed:    int           = 0
        self.total:        int           = 0
        self.current_item: Optional[str] = None
        self.error:        Optional[str] = None
        self.started_at:   Optional[str] = None   # ISO-8601 UTC string
        self.items:        list          = []      # ordered list of item dicts from the job request
        self.jam_detected: bool          = False
        self.jam_well_id:  Optional[str] = None

    @staticmethod
    def item_id(item: dict) -> str:
        """Return the stable display ID used by progress tracking."""
        if "well_id" in item:
            return str(item.get("well_id"))
        return f"{item['tray_index']}:{item['sample_index']}"

    def _normalize_item(self, item: dict, job_type: str) -> dict:
        """Attach default progress/result fields for a job item."""
        next_item = dict(item)
        next_item.setdefault("status", "incomplete")
        if job_type == "dispensing":
            next_item.setdefault("actual_weight", None)
        elif job_type == "hardness":
            next_item.setdefault("result", None)
            next_item.setdefault("result_shore_a", None)
            next_item.setdefault("result_shore_d", None)
            next_item["sample_index"] = int(item["sample_index"])
            mode = item.get("mode", "")
            if mode in ("shore_a", "shore_a_d"):
                next_item.setdefault("status_shore_a", "incomplete")
            if mode in ("shore_d", "shore_a_d"):
                next_item.setdefault("status_shore_d", "incomplete")
            next_item.setdefault("image_path_shore_a", None)
            next_item.setdefault("image_path_shore_d", None)
            next_item.setdefault("sample_error", None)
        return next_item

    def start_job(self, job_type: str, items: list[dict], started_at: str) -> None:
        """Initialize all progress fields at job start."""
        self.job_type = job_type
        self.total = len(items)
        self.completed = 0
        self.current_item = None
        self.error = None
        self.started_at = started_at
        self.items = [self._normalize_item(item, job_type) for item in items]
        self.running = True

    def mark_item_active(self, index: int) -> None:
        """Mark one item active and reset other active slots to incomplete."""
        if index < 0 or index >= len(self.items):
            return
        self.current_item = self.item_id(self.items[index])
        current_status = self.items[index].get("status")
        if current_status not in {"complete", "error"}:
            self.items[index]["status"] = "active"
        for idx, item in enumerate(self.items):
            if idx != index and item.get("status") == "active":
                item["status"] = "incomplete"

    def mark_item_complete(self, index: int, **updates) -> None:
        """Mark one item complete and attach optional result fields."""
        if index < 0 or index >= len(self.items):
            return
        self.items[index].update(updates)
        self.items[index]["status"] = "complete"
        self.completed += 1

    def mark_item_error(self, index: int, sample_error: str, **updates) -> None:
        """Mark one item as an error while leaving it not-complete."""
        if index < 0 or index >= len(self.items):
            return
        self.items[index].update(updates)
        self.items[index]["status"] = "error"
        self.items[index]["sample_error"] = sample_error

    def set_jam(self, well_id: str) -> None:
        """Mark a powder jam as active for the given well."""
        self.jam_detected = True
        self.jam_well_id  = well_id

    def clear_jam(self) -> None:
        """Clear an active jam so the UI dialog is dismissed."""
        self.jam_detected = False
        self.jam_well_id  = None

    def reset(self) -> None:
        """Reset all fields to their initial defaults."""
        self.__init__()

    def to_dict(self) -> dict:
        """Serialise all fields to a JSON-compatible dict for WebSocket telemetry.

        Returns:
            dict: All progress fields suitable for inclusion in a telemetry frame.
        """
        return {
            "running":      self.running,
            "job_type":     self.job_type,
            "completed":    self.completed,
            "total":        self.total,
            "current_item": self.current_item,
            "error":        self.error,
            "started_at":   self.started_at,
            "items":        self.items,
            "jam_detected": self.jam_detected,
            "jam_well_id":  self.jam_well_id,
        }
