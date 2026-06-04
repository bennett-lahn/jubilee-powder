"""
JobLog — persistent per-job JSON record for the Jubilee automation system.

One JobLog instance is created per job.  The constructor records metadata
(date, job type, planned items) and keeps a reference to the JubileeManager
so that all messy state extraction stays inside this class rather than
polluting JubileeManager.

Lifecycle
---------
1. Server creates a JobLog at the start of a job.
2. At key milestones (well placed, sample tested) either:
     a. JubileeManager calls job_log.update_well() / update_sample()  (real hw), or
     b. The server calls them directly with simulated values (mock mode).
3. Server calls job_log.finalize(outcome) when the job ends.
   This writes the JSON file to frontend/api/files/.

File naming
-----------
  {id:04d}_{YYYY-MM-DD}_{type}_{count}.json

  id    — sequential integer, derived from existing files at write time
  type  — "powder" or "hardness"
  count — number of successfully completed items
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.JubileeManager import JubileeManager

# Resolved at module load; works regardless of working directory.
_FILES_DIR = Path(__file__).parent.parent / "frontend" / "api" / "files"


class JobLog:
    """
    Accumulates per-item results for one job and persists them as a JSON file.

    Parameters
    ----------
    job_type:
        "powder" or "hardness".
    items:
        Ordered list of item dicts as sent from the UI.
        Powder:   [{"well_id": "0", "target_weight": 50.0}, ...]
        Hardness: [{"tray_index": 0, "sample_id": "0", "mode": "shore_a"}, ...]
    manager:
        Optional reference to JubileeManager.  When provided, update methods
        can extract state (e.g. last dispensed weight) directly from it.
        Pass None in mock / test mode.
    """

    def __init__(
        self,
        job_type: str,
        items: list[dict],
        manager: Optional["JubileeManager"] = None,
    ) -> None:
        self._job_type = job_type
        self._items = items
        self._manager = manager
        self._records: dict[str, dict] = {}
        self._start_time = datetime.now()
        self._outcome: Optional[str] = None

        _FILES_DIR.mkdir(parents=True, exist_ok=True)
        self._id: int = self._next_id()
        self.image_dir: Path = _FILES_DIR / "images" / f"{self._id:04d}"

    # ------------------------------------------------------------------
    # Update helpers — called per completed item
    # ------------------------------------------------------------------

    def update_well(
        self,
        well_id: str,
        actual_weight: Optional[float] = None,
    ) -> None:
        """
        Record the outcome of one powder-dispensing well.

        If actual_weight is not supplied and a manager reference is available,
        the weight is read from manager._last_dispense_weight (set by
        JubileeManager._fill_powder right after the fill completes, while the
        mold is still on the scale).
        """
        if actual_weight is None and self._manager is not None:
            actual_weight = self._manager.last_dispense_weight

        target = next(
            (i["target_weight"] for i in self._items if i["well_id"] == well_id),
            None,
        )
        self._records[well_id] = {
            "well_id": well_id,
            "target_weight": target,
            "actual_weight": actual_weight,
            "status": "complete",
        }

    def update_sample(
        self,
        sample_id: str,
        tray_index: int,
        result: Optional[float] = None,
        sample_error: Optional[str] = None,
        status: Optional[str] = None,
        measurement_mode: Optional[str] = None,
        image_path: Optional[str] = None,
    ) -> None:
        """
        Record the outcome of one hardness test sample.

        result is the measured hardness value.  When the hardness tester is
        integrated, the manager reference can be used here to extract the
        reading; for now it is passed in explicitly.
        """
        if result is None and self._manager is not None:
            result = getattr(self._manager, "last_hardness_result", None)
        if sample_error is None and self._manager is not None:
            sample_error = getattr(self._manager, "last_hardness_error", None)

        mode = next(
            (
                i["mode"]
                for i in self._items
                if i["sample_id"] == sample_id
                and i.get("tray_index") == tray_index
            ),
            None,
        )
        measured_mode = measurement_mode or mode
        key = self._sample_record_key(sample_id, tray_index)
        existing_record = self._records.get(key, {})
        result_shore_a = existing_record.get("result_shore_a")
        result_shore_d = existing_record.get("result_shore_d")
        image_path_shore_a = existing_record.get("image_path_shore_a")
        image_path_shore_d = existing_record.get("image_path_shore_d")

        if measured_mode == "shore_a":
            result_shore_a = result
            if image_path is not None:
                image_path_shore_a = image_path
        elif measured_mode == "shore_d":
            result_shore_d = result
            if image_path is not None:
                image_path_shore_d = image_path
        elif mode == "shore_a_d":
            # For mixed mode fallback, infer pass from existing values.
            if result_shore_a is None:
                result_shore_a = result
                if image_path is not None:
                    image_path_shore_a = image_path
            else:
                result_shore_d = result
                if image_path is not None:
                    image_path_shore_d = image_path
        else:
            # Single-mode (non-dual): store image under whichever shore side matches.
            if image_path is not None:
                image_path_shore_a = image_path

        result_value = result
        if mode == "shore_a_d":
            result_value = None

        resolved_status = status
        if resolved_status is None:
            if sample_error:
                resolved_status = "error"
            elif mode == "shore_a_d":
                if result_shore_a is not None and result_shore_d is not None:
                    resolved_status = "complete"
                else:
                    resolved_status = "incomplete"
            elif result is not None:
                resolved_status = "complete"
            else:
                resolved_status = "incomplete"
        self._records[key] = {
            "sample_id": sample_id,
            "tray_index": tray_index,
            "mode": mode,
            "result": result_value,
            "result_shore_a": result_shore_a,
            "result_shore_d": result_shore_d,
            "image_path_shore_a": image_path_shore_a,
            "image_path_shore_d": image_path_shore_d,
            "sample_error": sample_error,
            "status": resolved_status,
        }

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    def finalize(self, outcome: str) -> Path:
        """
        Write the completed log to disk and return the path.

        Parameters
        ----------
        outcome:
            One of "successful", "cancelled", or "aborted".
        """
        self._outcome = outcome
        return self._write()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        """Return the next sequential job ID by scanning existing files."""
        max_id = 0
        for f in _FILES_DIR.glob("*.json"):
            m = re.match(r"^(\d+)_", f.name)
            if m:
                max_id = max(max_id, int(m.group(1)))
        return max_id + 1

    def _build_state(self) -> dict:
        """Build the state section of the JSON, filling in incomplete items."""
        if self._job_type == "dispensing":
            molds = []
            for item in self._items:
                wid = item["well_id"]
                molds.append(
                    self._records.get(
                        wid,
                        {
                            "well_id": wid,
                            "target_weight": item["target_weight"],
                            "actual_weight": None,
                            "status": "incomplete",
                        },
                    )
                )
            return {"molds": molds}

        # hardness
        samples = []
        for item in self._items:
            sid = item["sample_id"]
            tray_index = item.get("tray_index")
            key = self._sample_record_key(sid, tray_index)
            samples.append(
                self._records.get(
                    key,
                    {
                        "sample_id": sid,
                        "tray_index": tray_index,
                        "mode": item["mode"],
                        "result": None,
                        "result_shore_a": None,
                        "result_shore_d": None,
                        "image_path_shore_a": None,
                        "image_path_shore_d": None,
                        "sample_error": None,
                        "status": "incomplete",
                    },
                )
            )
        return {"samples": samples}

    def _sample_record_key(self, sample_id: str, tray_index: int) -> str:
        return f"{tray_index}:{sample_id}"

    def _write(self) -> Path:
        job_id = self._id
        date_str = self._start_time.strftime("%Y-%m-%d")
        count = len(self._items)

        filename = f"{job_id:04d}_{date_str}_{self._job_type}_{count}.json"
        path = _FILES_DIR / filename

        payload = {
            "metadata": {
                "id": job_id,
                "date": date_str,
                "job_type": self._job_type,
                "outcome": self._outcome,
                "units_completed": count,
            },
            "state": self._build_state(),
        }

        path.write_text(json.dumps(payload, indent=2))
        return path
