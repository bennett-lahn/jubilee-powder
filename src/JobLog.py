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
  type  — dispensing or hardness
  count — number of planned items in the job
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.JubileeManager import JubileeManager

from src.ConfigLoader import config as _config

_VALID_MEASUREMENT_MODES = frozenset({"shore_a", "shore_d"})


class JobLog:
    """
    Accumulates per-item results for one job and persists them as a JSON file.
    """

    def __init__(
        self,
        job_type: str,
        items: list[dict],
        manager: "JubileeManager" | None = None,
    ) -> None:
        self._job_type = job_type
        self._items = (
            [_normalize_hardness_item(i) for i in items]
            if job_type == "hardness"
            else items
        )
        self._manager = manager
        self._records: dict[str, dict] = {}
        self._start_time = datetime.now()
        self._outcome: str | None = None

        files_dir = _config.get_job_files_dir()
        files_dir.mkdir(parents=True, exist_ok=True)
        self._id: int = self._next_id()
        self.image_dir: Path = files_dir / "images" / f"{self._id:04d}"

    def update_well(
        self,
        well_id: str,
        actual_weight: float | None = None,
    ) -> None:
        """Record the outcome of one powder-dispensing well."""
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
        sample_index: int,
        tray_index: int,
        result: float | None = None,
        sample_error: str | None = None,
        status: str | None = None,
        measurement_mode: str | None = None,
        image_path: str | None = None,
    ) -> None:
        """Record the outcome of one hardness pass for a sample.

        ``measurement_mode`` must be ``shore_a`` or ``shore_d`` (the pass being
        recorded). Job configuration mode (``shore_a``, ``shore_d``, ``shore_a_d``)
        comes from the planned items list.
        """
        if result is None and self._manager is not None:
            result = getattr(self._manager, "last_hardness_result", None)
        if sample_error is None and self._manager is not None:
            sample_error = getattr(self._manager, "last_hardness_error", None)

        item = self._find_item(sample_index, tray_index)
        if item is None:
            return

        mode = item["mode"]
        if measurement_mode not in _VALID_MEASUREMENT_MODES:
            raise ValueError(
                f"measurement_mode must be 'shore_a' or 'shore_d', got {measurement_mode!r}"
            )
        key = self._sample_record_key(tray_index, sample_index)
        existing = self._records.get(key, self._default_sample_record(item))
        existing = self._ensure_pass_status_fields(existing)

        result_shore_a = existing.get("result_shore_a")
        result_shore_d = existing.get("result_shore_d")
        status_shore_a = existing.get("status_shore_a")
        status_shore_d = existing.get("status_shore_d")
        image_path_shore_a = existing.get("image_path_shore_a")
        image_path_shore_d = existing.get("image_path_shore_d")

        if sample_error:
            pass_status = "error"
        elif status:
            pass_status = status
        elif result is not None:
            pass_status = "complete"
        else:
            pass_status = "incomplete"

        if measurement_mode == "shore_a":
            if result is not None:
                result_shore_a = result
            if image_path is not None:
                image_path_shore_a = image_path
            status_shore_a = pass_status
        else:
            if result is not None:
                result_shore_d = result
            if image_path is not None:
                image_path_shore_d = image_path
            status_shore_d = pass_status

        resolved_status = self._resolve_sample_status(
            mode=mode,
            sample_error=sample_error,
            status_shore_a=status_shore_a,
            status_shore_d=status_shore_d,
            override=status,
        )

        self._records[key] = self._ensure_pass_status_fields({
            "tray_index": tray_index,
            "sample_index": sample_index,
            "mode": mode,
            "result": None,
            "result_shore_a": result_shore_a,
            "result_shore_d": result_shore_d,
            "status_shore_a": status_shore_a,
            "status_shore_d": status_shore_d,
            "image_path_shore_a": image_path_shore_a,
            "image_path_shore_d": image_path_shore_d,
            "sample_error": sample_error,
            "status": resolved_status,
        })

    def finalize(self, outcome: str) -> Path:
        """Write the completed log to disk and return the path."""
        self._outcome = outcome
        return self._write()

    def _find_item(self, sample_index: int, tray_index: int) -> dict | None:
        for item in self._items:
            if (
                JobLog._item_sample_index(item) == sample_index
                and int(item["tray_index"]) == tray_index
            ):
                return item
        return None

    @staticmethod
    def _item_sample_index(item: dict) -> int:
        return int(item["sample_index"])

    @staticmethod
    def _default_sample_record(item: dict) -> dict:
        mode = item["mode"]
        tray_index = int(item["tray_index"])
        record = {
            "tray_index": tray_index,
            "sample_index": JobLog._item_sample_index(item),
            "mode": mode,
            "result": None,
            "result_shore_a": None,
            "result_shore_d": None,
            "status_shore_a": None,
            "status_shore_d": None,
            "image_path_shore_a": None,
            "image_path_shore_d": None,
            "sample_error": None,
            "status": "incomplete",
        }
        return JobLog._ensure_pass_status_fields(record)

    @staticmethod
    def _ensure_pass_status_fields(record: dict) -> dict:
        """Set ``status_shore_a`` / ``status_shore_d`` for every pass this job uses."""
        mode = record["mode"]
        out = dict(record)
        if mode in ("shore_a", "shore_a_d"):
            if out.get("status_shore_a") is None:
                out["status_shore_a"] = "incomplete"
        if mode in ("shore_d", "shore_a_d"):
            if out.get("status_shore_d") is None:
                out["status_shore_d"] = "incomplete"
        return out

    @staticmethod
    def _resolve_sample_status(
        mode: str,
        sample_error: str | None,
        status_shore_a: str | None,
        status_shore_d: str | None,
        override: str | None,
    ) -> str:
        if override:
            return override
        if sample_error:
            return "error"

        if mode == "shore_a":
            if status_shore_a == "complete":
                return "complete"
            if status_shore_a == "error":
                return "error"
            return "incomplete"

        if mode == "shore_d":
            if status_shore_d == "complete":
                return "complete"
            if status_shore_d == "error":
                return "error"
            return "incomplete"

        if mode == "shore_a_d":
            if status_shore_a == "error" or status_shore_d == "error":
                return "error"
            if status_shore_a == "complete" and status_shore_d == "complete":
                return "complete"
            return "incomplete"

        return "incomplete"

    def _next_id(self) -> int:
        """Return the next sequential job ID by scanning existing files."""
        max_id = 0
        for f in _config.get_job_files_dir().glob("*.json"):
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
            tray_index = int(item["tray_index"])
            sample_index = JobLog._item_sample_index(item)
            key = self._sample_record_key(tray_index, sample_index)
            samples.append(
                self._records.get(key, self._default_sample_record(item))
            )
        return {"samples": samples}

    def _sample_record_key(self, tray_index: int, sample_index: int) -> str:
        return f"{tray_index}:{sample_index}"

    def _completed_sample_count(self) -> int:
        state = self._build_state()
        return sum(
            1 for s in state.get("samples", []) if s.get("status") == "complete"
        )

    def _write(self) -> Path:
        job_id = self._id
        date_str = self._start_time.strftime("%Y-%m-%d")
        count = len(self._items)
        units_completed = (
            self._completed_sample_count()
            if self._job_type == "hardness"
            else sum(
                1 for m in self._build_state().get("molds", [])
                if m.get("status") == "complete"
            )
        )

        filename = f"{job_id:04d}_{date_str}_{self._job_type}_{count}.json"
        path = _config.get_job_files_dir() / filename

        payload = {
            "metadata": {
                "id": job_id,
                "date": date_str,
                "job_type": self._job_type,
                "outcome": self._outcome,
                "units_completed": units_completed,
            },
            "state": self._build_state(),
        }

        path.write_text(json.dumps(payload, indent=2))
        return path


_VALID_JOB_MODES = frozenset({"shore_a", "shore_d", "shore_a_d"})


def _normalize_hardness_item(item: dict) -> dict:
    """Ensure planned hardness items use integer tray_index, sample_index, and mode."""
    normalized = dict(item)
    normalized["tray_index"] = int(item["tray_index"])
    normalized["sample_index"] = int(item["sample_index"])
    mode = item["mode"]
    if mode not in _VALID_JOB_MODES:
        raise ValueError(
            f"hardness item mode must be one of {sorted(_VALID_JOB_MODES)}, got {mode!r}"
        )
    normalized["mode"] = mode
    return normalized
