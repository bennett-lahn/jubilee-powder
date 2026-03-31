"""
FastAPI server for the Jubilee Automation system.

Architecture
------------
  Model       — HardwareManager / MockHardwareManager (hardware state + operations)
  ViewModel   — Zustand store in the React frontend (current state, derived views)
  View        — React components (purely reactive, reads from Zustand)

This server is the API gateway between the two layers:
  REST endpoints  — discrete, low-frequency commands (connect, start job, stop job…)
  WebSocket /ws   — continuous 4 Hz telemetry pushed to every connected browser

Switching between mock and real hardware
-----------------------------------------
Set MOCK_HARDWARE = True  to use MockHardwareManager (UI development, no physical hardware).
Set MOCK_HARDWARE = False to use HardwareManager      (production, real Jubilee + scale).

Both classes expose an identical public API so no other code needs to change.

Usage (from the frontend directory):
    uvicorn server:app --host 0.0.0.0 --port 8000 --reload

Usage (from the project root):
    uvicorn frontend.server:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import json
import math
import random
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Optional, Union

# Allow imports from the project root (src.JobLog etc.) when the server is
# launched from either the frontend/ directory or the project root.
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

_FILES_DIR = Path(__file__).parent / "api" / "files"
_FILES_DIR.mkdir(parents=True, exist_ok=True)

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Toggle — flip to False when deploying on real hardware.
# ---------------------------------------------------------------------------
MOCK_HARDWARE: bool = True


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
# Pydantic models — configuration, requests, responses
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


class UpdateDispenserRequest(BaseModel):
    num_pistons: int = Field(ge=0)


class PowderWell(BaseModel):
    well_id:       str   = Field(min_length=1)
    target_weight: float = Field(gt=0.0, le=5_000.0, description="Target weight in grams")


class HardnessSample(BaseModel):
    sample_id: str = Field(min_length=1)
    mode:      Literal["shore_a", "shore_a_d", "shore_d"]


class StartPowderJobRequest(BaseModel):
    job_type: Literal["dispensing"] = "dispensing"
    wells:    list[PowderWell] = Field(min_length=1, max_length=24)


class StartHardnessJobRequest(BaseModel):
    job_type: Literal["hardness"] = "hardness"
    samples:  list[HardnessSample] = Field(min_length=1, max_length=24)


# Discriminated union: FastAPI picks the correct model from the job_type field.
JobRequest = Annotated[
    Union[StartPowderJobRequest, StartHardnessJobRequest],
    Body(discriminator="job_type"),
]


# =============================================================================
# Job-progress state  (shared between endpoint handlers and the telemetry loop)
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


# =============================================================================
# MockHardwareManager
#
# Standalone simulation of the Jubilee hardware for UI development.
# No physical hardware required.  Scale readings use a slow sine drift plus
# Gaussian noise to mimic the real A&D FX-120i serial scale output.  Job
# execution advances JobProgress in-place via async sleep to produce realistic
# per-well timing visible through the telemetry WebSocket.
#
# Public API is identical to HardwareManager — switch between them by
# changing MOCK_HARDWARE at the top of this file.
# =============================================================================

class MockHardwareManager:

    def __init__(self) -> None:
        self.state:   MachineState = MachineState.DISCONNECTED
        self._config: HardwareConfig = HardwareConfig()
        self._dispensers: list[DispenserStatus] = []
        self._t0:         float = time.monotonic()
        self._scale_base: float = 50.0

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self.state != MachineState.DISCONNECTED

    @property
    def jubilee_ip(self) -> str:
        return self._config.machine_address or "mock.local"

    # ── Connection lifecycle ───────────────────────────────────────────────────

    async def connect(self, config: HardwareConfig) -> None:
        self._config = config
        self._dispensers = [
            DispenserStatus(index=i, pistons_remaining=config.pistons_per_dispenser)
            for i in range(config.num_dispensers)
        ]
        self.state = MachineState.HOMING
        await asyncio.sleep(2.0)          # simulate homing sequence
        self.state = MachineState.IDLE

    async def disconnect(self) -> None:
        self._dispensers = []
        self.state = MachineState.DISCONNECTED

    # ── Scale reads ───────────────────────────────────────────────────────────

    async def get_weight_unstable(self) -> float:
        t     = time.monotonic() - self._t0
        drift = math.sin(t * 0.15) * 1.8
        noise = random.gauss(0.0, 0.04)
        return round(max(0.0, self._scale_base + drift + noise), 3)

    async def get_weight_stable(self) -> float:
        return round(self._scale_base + random.gauss(0.0, 0.008), 3)

    # ── Dispenser management ──────────────────────────────────────────────────

    def get_dispensers(self) -> list[DispenserStatus]:
        return list(self._dispensers)

    def update_dispenser_pistons(self, index: int, num_pistons: int) -> bool:
        if index >= len(self._dispensers):
            return False
        self._dispensers[index] = DispenserStatus(
            index=index, pistons_remaining=num_pistons
        )
        return True

    # ── Job execution ─────────────────────────────────────────────────────────

    async def run_dispensing_job(
        self, wells: list[dict], progress: JobProgress, job_log=None
    ) -> None:
        self.state = MachineState.RUNNING
        try:
            for i, well in enumerate(wells):
                if not progress.running:
                    break
                progress.current_item = well["well_id"]
                await asyncio.sleep(2.0)
                if job_log is not None:
                    simulated_weight = well["target_weight"] * (
                        1 + random.gauss(0, 0.008)
                    )
                    job_log.update_well(
                        well["well_id"], actual_weight=round(simulated_weight, 3)
                    )
                progress.completed = i + 1
        finally:
            # Do not overwrite ERROR set by an abort call
            if self.state == MachineState.RUNNING:
                self.state = MachineState.IDLE

    async def run_hardness_job(
        self, samples: list[dict], progress: JobProgress, job_log=None
    ) -> None:
        self.state = MachineState.RUNNING
        try:
            for i, sample in enumerate(samples):
                if not progress.running:
                    break
                progress.current_item = sample["sample_id"]
                await asyncio.sleep(1.5)
                if job_log is not None:
                    simulated_result = round(random.uniform(30.0, 80.0), 1)
                    job_log.update_sample(
                        sample["sample_id"], result=simulated_result
                    )
                progress.completed = i + 1
        finally:
            if self.state == MachineState.RUNNING:
                self.state = MachineState.IDLE


# =============================================================================
# HardwareManager
#
# Production wrapper around the real JubileeManager.  All blocking serial /
# network calls are offloaded to asyncio.to_thread() so the uvicorn event loop
# is never stalled.
#
# JubileeManager is imported lazily inside connect() so the server starts
# cleanly on developer machines that lack the science_jubilee package.
#
# Public API is identical to MockHardwareManager — switch between them by
# changing MOCK_HARDWARE at the top of this file.
# =============================================================================

class HardwareManager:

    def __init__(self) -> None:
        self.state:    MachineState  = MachineState.DISCONNECTED
        self._config:  HardwareConfig = HardwareConfig()
        self._manager                 = None   # JubileeManager instance

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self.state != MachineState.DISCONNECTED

    @property
    def jubilee_ip(self) -> str:
        return self._config.machine_address or "jubilee.local"

    # ── Connection lifecycle ───────────────────────────────────────────────────

    async def connect(self, config: HardwareConfig) -> None:
        """
        Initiate hardware connection.  Called from a background asyncio.Task
        so the HTTP 202 response returns immediately.

        State transitions:  DISCONNECTED → HOMING → IDLE  (success)
                            DISCONNECTED → HOMING → ERROR (failure)
        """
        self._config = config
        self.state   = MachineState.HOMING
        try:
            from src.JubileeManager import JubileeManager as _JM   # lazy import
            self._manager = _JM(
                num_piston_dispensers=config.num_dispensers,
                num_pistons_per_dispenser=config.pistons_per_dispenser,
            )
            success = await asyncio.to_thread(
                self._manager.connect,
                machine_address=config.machine_address,
                scale_port=config.scale_port,
            )
            if not success:
                raise RuntimeError("JubileeManager.connect() returned False")
            self.state = MachineState.IDLE
        except Exception:
            self.state    = MachineState.ERROR
            self._manager = None
            raise

    async def disconnect(self) -> None:
        if self._manager is not None:
            await asyncio.to_thread(self._manager.disconnect)
            self._manager = None
        self.state = MachineState.DISCONNECTED

    # ── Scale reads ───────────────────────────────────────────────────────────

    async def get_weight_unstable(self) -> float:
        if self._manager and self._manager.connected:
            return await asyncio.to_thread(self._manager.get_weight_unstable)
        return 0.0

    async def get_weight_stable(self) -> float:
        if self._manager and self._manager.connected:
            return await asyncio.to_thread(self._manager.get_weight_stable)
        return 0.0

    # ── Dispenser management ──────────────────────────────────────────────────

    def get_dispensers(self) -> list[DispenserStatus]:
        if self._manager and self._manager.connected:
            return [
                DispenserStatus(index=d.index, pistons_remaining=d.num_pistons)
                for d in self._manager.piston_dispensers
            ]
        return []

    def update_dispenser_pistons(self, index: int, num_pistons: int) -> bool:
        if not (self._manager and self._manager.connected):
            return False
        dispensers = self._manager.piston_dispensers
        if index >= len(dispensers):
            return False
        dispensers[index].num_pistons = num_pistons
        return True

    # ── Job execution ─────────────────────────────────────────────────────────

    async def run_dispensing_job(
        self, wells: list[dict], progress: JobProgress, job_log=None
    ) -> None:
        self.state = MachineState.RUNNING
        if job_log is not None and self._manager is not None:
            self._manager.active_job_log = job_log
        try:
            for i, well in enumerate(wells):
                if not progress.running:
                    break
                progress.current_item = well["well_id"]
                success = await asyncio.to_thread(
                    self._manager.dispense_to_well,
                    well["well_id"],
                    well["target_weight"],
                )
                if not success:
                    raise RuntimeError(
                        f"Dispense failed for well {well['well_id']!r}"
                    )
                progress.completed = i + 1
        finally:
            if self._manager is not None:
                self._manager.active_job_log = None
            if self.state == MachineState.RUNNING:
                self.state = MachineState.IDLE

    async def run_hardness_job(
        self, samples: list[dict], progress: JobProgress, job_log=None
    ) -> None:
        self.state = MachineState.RUNNING
        try:
            for i, sample in enumerate(samples):
                if not progress.running:
                    break
                progress.current_item = sample["sample_id"]
                # TODO: replace with asyncio.to_thread(hardness_tester.measure, ...) once integrated
                await asyncio.sleep(1.5)
                if job_log is not None:
                    job_log.update_sample(sample["sample_id"], result=None)
                progress.completed = i + 1
        finally:
            if self.state == MachineState.RUNNING:
                self.state = MachineState.IDLE


# =============================================================================
# WebSocket connection manager
# =============================================================================

class ConnectionManager:
    """Tracks every live browser WebSocket client."""

    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    @property
    def client_count(self) -> int:
        return len(self.active)

    async def broadcast(self, data: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self.active):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# =============================================================================
# Module-level singletons
# =============================================================================

hw:       MockHardwareManager | HardwareManager = (
    MockHardwareManager() if MOCK_HARDWARE else HardwareManager()
)
ws_mgr   = ConnectionManager()
progress = JobProgress()


# =============================================================================
# Background telemetry loop  (4 Hz)
# =============================================================================

async def telemetry_loop() -> None:
    """
    Runs continuously at 4 Hz.

    Broadcasts a unified telemetry frame to every connected browser.
    Weight is only queried when hardware is connected.
    Skips broadcast entirely when no browser clients are open.
    """
    while True:
        if ws_mgr.client_count > 0:
            weight = (await hw.get_weight_unstable()) if hw.connected else None
            await ws_mgr.broadcast({
                "weight":      weight,
                "state":       hw.state.value,
                "connected":   hw.connected,
                "jubilee_ip":  hw.jubilee_ip,
                "job":         progress.to_dict(),
                "dispensers":  [d.model_dump() for d in hw.get_dispensers()],
                "clients":     ws_mgr.client_count,
            })
        await asyncio.sleep(0.25)   # 4 Hz


# =============================================================================
# App + lifespan
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(telemetry_loop())
    yield
    task.cancel()


app = FastAPI(title="Jubilee Automation API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],   # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# REST — hardware lifecycle
# =============================================================================

@app.get("/api/status")
async def get_status():
    """Full machine snapshot: state, job progress, dispenser status, client count."""
    return {
        "connected":   hw.connected,
        "state":       hw.state.value,
        "jubilee_ip":  hw.jubilee_ip,
        "job":         progress.to_dict(),
        "dispensers":  [d.model_dump() for d in hw.get_dispensers()],
        "clients":     ws_mgr.client_count,
    }


@app.post("/api/hardware/connect", status_code=202)
async def hardware_connect(config: HardwareConfig):
    """
    Begin hardware connection with the supplied configuration.

    Returns HTTP 202 immediately; the connection runs in the background.
    Monitor the WebSocket state field for transitions:
      DISCONNECTED → HOMING → IDLE   (success)
      DISCONNECTED → HOMING → ERROR  (failure — check job.error for reason)
    """
    if hw.connected:
        raise HTTPException(status_code=400, detail="Already connected to hardware.")
    if hw.state == MachineState.HOMING:
        raise HTTPException(status_code=400, detail="Connection already in progress.")
    asyncio.create_task(_run_connect(config))
    return {"accepted": True, "message": "Connection initiated — monitor WebSocket state."}


@app.post("/api/hardware/disconnect", status_code=200)
async def hardware_disconnect():
    """
    Stop any running job and disconnect from hardware.

    Awaits disconnect completion (fast — just closes serial/HTTP sessions).
    After this returns the WebSocket will broadcast state=disconnected.
    """
    if progress.running:
        progress.running = False   # signal job loop to exit cleanly
    await hw.disconnect()
    return {"disconnected": True}


# =============================================================================
# REST — jobs
# =============================================================================

@app.post("/api/job/start", status_code=202)
async def start_job(body: JobRequest):
    """
    Enqueue a powder-dispensing or hardness-testing job.

    State guards (HTTP 400 if violated):
      - Machine must be in the IDLE state.
      - No job may already be in progress.

    Pydantic validates all field constraints before this function is called;
    invalid request bodies return HTTP 422 automatically.
    """
    if hw.state != MachineState.IDLE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Machine is not idle (current state: {hw.state.value!r}). "
                "Wait for the current operation to finish or resolve the error."
            ),
        )
    if progress.running:
        raise HTTPException(
            status_code=400,
            detail="A job is already in progress. Only one job may run at a time.",
        )

    now = datetime.now(timezone.utc).isoformat()

    if body.job_type == "dispensing":
        items = [w.model_dump() for w in body.wells]
        progress.job_type   = "dispensing"
        progress.total      = len(items)
        progress.completed  = 0
        progress.error      = None
        progress.started_at = now
        progress.items      = items
        progress.running    = True
        asyncio.create_task(_run_dispensing(items))
        return {"accepted": True, "job_type": "dispensing", "total": len(items)}

    else:  # hardness
        items = [s.model_dump() for s in body.samples]
        progress.job_type   = "hardness"
        progress.total      = len(items)
        progress.completed  = 0
        progress.error      = None
        progress.started_at = now
        progress.items      = items
        progress.running    = True
        asyncio.create_task(_run_hardness(items))
        return {"accepted": True, "job_type": "hardness", "total": len(items)}


@app.post("/api/job/stop", status_code=200)
async def stop_job():
    """
    Signal the running job to stop after the current well/sample completes.
    The job does not stop immediately — it exits at the next iteration check.
    """
    if not progress.running:
        raise HTTPException(status_code=400, detail="No job is currently running.")
    progress.running = False
    return {"stopping": True}


@app.post("/api/job/cancel", status_code=200)
async def cancel_job():
    """
    Graceful cancel: finish the current mold/sample, then stop and stow the tool.

    The job exits at the next iteration boundary (same as stop).  On real
    hardware the manager will home/stow the active tool before releasing IDLE.
    The machine returns to IDLE when the current operation completes.
    """
    if not progress.running:
        raise HTTPException(status_code=400, detail="No job is currently running.")
    progress.running = False
    return {"cancelling": True}


@app.post("/api/job/abort", status_code=200)
async def abort_job():
    """
    Emergency stop: immediately halt all motion.

    Sets machine state to ERROR.  The hardware must be re-homed before
    starting a new job.  On real hardware this triggers a Duet M112 e-stop.
    """
    progress.running = False
    hw.state = MachineState.ERROR   # prevents job finally-block from resetting to IDLE
    return {"aborted": True}


@app.get("/api/job/log")
async def get_job_log():
    """
    Return the most recent job log in the normalised live-progress format.

    Priority order:
      1. If a job ran in this server session (progress has data), synthesise
         from in-memory state so the home screen updates in real-time.
      2. Otherwise read the most recent file from _FILES_DIR — this is the
         path taken after a server restart, since in-memory state is lost.
    Returns {"log": null} when neither source has data.
    """
    if progress.job_type is not None:
        return {"log": _build_progress_log()}

    files = sorted(_FILES_DIR.glob("*.json"), reverse=True)
    if not files:
        return {"log": None}
    try:
        raw = json.loads(files[0].read_text())
        return {"log": _normalize_file_log(raw)}
    except Exception:
        return {"log": None}


def _build_progress_log() -> dict:
    """Synthesise a job log dict from the current in-memory JobProgress."""
    items_with_status = []
    for i, item in enumerate(progress.items):
        item_id = item.get("well_id") or item.get("sample_id")
        if i < progress.completed:
            status = "complete"
        elif item_id == progress.current_item:
            status = "active"
        else:
            status = "pending"
        items_with_status.append({**item, "status": status})

    date_str = progress.started_at[:10] if progress.started_at else None

    return {
        "job_type":   progress.job_type,
        "started_at": progress.started_at,
        "date":       date_str,
        "status":     "running" if progress.running else "complete",
        "completed":  progress.completed,
        "total":      progress.total,
        "error":      progress.error,
        "items":      items_with_status,
    }


def _normalize_file_log(raw: dict) -> dict:
    """
    Convert a persisted job JSON file to the normalised live-progress shape
    that the frontend store and HomeScreen already understand.

    File shape  →  normalised shape
    ────────────────────────────────────────────────────────────────────────
    metadata.job_type  "powder"/"hardness"  →  job_type  "dispensing"/"hardness"
    metadata.date                           →  date
    metadata.outcome                        →  status
    state.molds / state.samples             →  items  (already in correct shape)
    """
    meta  = raw.get("metadata", {})
    state = raw.get("state", {})

    job_type = meta.get("job_type", "")

    items = state.get("molds") or state.get("samples") or []
    completed = sum(1 for it in items if it.get("status") == "complete")

    return {
        "job_type":   job_type,
        "started_at": None,
        "date":       meta.get("date"),
        "status":     meta.get("outcome", "complete"),
        "completed":  completed,
        "total":      len(items),
        "error":      None,
        "items":      items,
    }


# =============================================================================
# REST — dispensers
# =============================================================================

@app.get("/api/dispensers")
async def get_dispensers():
    """Return the current status of all configured piston dispensers."""
    return {"dispensers": [d.model_dump() for d in hw.get_dispensers()]}


@app.put("/api/dispensers/{index}", status_code=200)
async def update_dispenser(index: int, body: UpdateDispenserRequest):
    """
    Update the remaining piston count for a specific dispenser.
    Used after the user manually reloads a dispenser tray.
    """
    success = hw.update_dispenser_pistons(index, body.num_pistons)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid dispenser index {index} or hardware not connected.",
        )
    return {"updated": True, "index": index, "num_pistons": body.num_pistons}


# =============================================================================
# REST — job log files
# =============================================================================

@app.get("/api/files")
async def list_job_files():
    """
    Return metadata for all job log JSON files in the files directory.

    Each entry contains the fields expected by the DataScreen:
      name, size, modified (ISO-8601), type ("file").
    Files are returned newest-first (by filename, which encodes a sequential ID).
    """
    entries = []
    for f in sorted(_FILES_DIR.glob("*.json"), reverse=True):
        stat = f.stat()
        entries.append({
            "name":     f.name,
            "path":     f.name,
            "size":     stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "type":     "file",
        })
    return entries


@app.get("/api/files/{filename}")
async def get_job_file(filename: str):
    """
    Return the full JSON content of a single job log file.

    filename must match exactly (e.g. "0001_2026-03-31_powder_5.json").
    Returns HTTP 404 if the file does not exist.
    """
    path = _FILES_DIR / filename
    if not path.exists() or path.suffix != ".json":
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read file: {exc}")


# =============================================================================
# Background task helpers
# =============================================================================

def _make_job_log(job_type: str, items: list[dict]):
    """
    Instantiate a JobLog.

    In mock mode the manager reference is None; in real mode we pass the
    underlying JubileeManager so the log can pull weight data from it.
    """
    try:
        from src.JobLog import JobLog
        manager_ref = getattr(hw, "_manager", None)
        return JobLog(job_type=job_type, items=items, manager=manager_ref)
    except Exception as exc:
        print(f"[JobLog] Could not create job log: {exc}")
        return None


async def _run_connect(config: HardwareConfig) -> None:
    try:
        await hw.connect(config)
    except BaseException as exc:
        progress.error = f"Connection failed: {exc}"
        # state is already set to ERROR inside each manager's connect()


async def _run_dispensing(items: list[dict]) -> None:
    job_log = _make_job_log("dispensing", items)
    outcome = "cancelled"
    try:
        await hw.run_dispensing_job(items, progress, job_log)
        if progress.completed == progress.total:
            outcome = "successful"
        elif hw.state == MachineState.ERROR:
            outcome = "aborted"
    except Exception as exc:
        progress.error = str(exc)
        hw.state = MachineState.ERROR
        outcome = "aborted"
    finally:
        progress.running = False
        if job_log is not None:
            try:
                job_log.finalize(outcome)
            except Exception as exc:
                print(f"[JobLog] Failed to write log: {exc}")


async def _run_hardness(items: list[dict]) -> None:
    job_log = _make_job_log("hardness", items)
    outcome = "cancelled"
    try:
        await hw.run_hardness_job(items, progress, job_log)
        if progress.completed == progress.total:
            outcome = "successful"
        elif hw.state == MachineState.ERROR:
            outcome = "aborted"
    except Exception as exc:
        progress.error = str(exc)
        hw.state = MachineState.ERROR
        outcome = "aborted"
    finally:
        progress.running = False
        if job_log is not None:
            try:
                job_log.finalize(outcome)
            except Exception as exc:
                print(f"[JobLog] Failed to write log: {exc}")


# =============================================================================
# WebSocket endpoint
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """
    Register a browser client.  The telemetry_loop pushes frames to all
    registered clients; this coroutine just keeps the connection alive.
    """
    await ws_mgr.connect(ws)
    try:
        while True:
            await ws.receive_text()   # discard client-sent messages
    except WebSocketDisconnect:
        ws_mgr.disconnect(ws)
