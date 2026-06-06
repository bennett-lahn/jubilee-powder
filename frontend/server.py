"""
FastAPI server for the Jubilee Automation system.

This module is the API gateway between the React frontend and the hardware layer.

Architecture:
    Model     - HardwareManager / MockHardwareManager (hardware state + operations)
    ViewModel - Zustand store in the React frontend (current state, derived views)
    View      - React components (purely reactive, reads from Zustand)

Transport:
    REST endpoints - discrete, low-frequency commands (connect, start job, stop job...)
    WebSocket /ws  - continuous 4 Hz telemetry pushed to every connected browser

Mock vs real hardware:
    Set ``server.mock_hardware`` in ``jubilee_api_config/system_config.json``, or
    override at process start with ``JUBILEE_MOCK_HARDWARE=1`` (see ``_mock_hardware_enabled()``).
    Both manager classes expose the same API.

Example:
    From the frontend directory::

        uvicorn server:app --host 0.0.0.0 --port 8000 --reload

    From the project root::

        uvicorn frontend.server:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

# Allow imports from the project root (src.JobLog etc.) when the server is
# launched from either the frontend/ directory or the project root.
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Add frontend/src/ directly so that models and hardware_manager can be imported
# by their bare module names without colliding with the project-root src/ package
# (which contains JubileeManager, Scale, etc.).
_backend_src = Path(__file__).parent / "src"
if str(_backend_src) not in sys.path:
    sys.path.insert(0, str(_backend_src))

from src.ConfigLoader import config

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from models import HardwareConfig, JobProgress, MachineState
from hardware_manager import HardwareManager, MockHardwareManager
from jubilee_api_config.constants import (
    HARDNESS_COLS,
    HARDNESS_ROWS,
    HARDNESS_TRAY_CAPACITY,
    HARDNESS_TRAY_COUNT,
)

# ---------------------------------------------------------------------------
# Optional Google Drive job log backup
# ---------------------------------------------------------------------------
_drive_backup: "JobDriveBackup" | None = None  # noqa: F821 — set in lifespan
_drive_init_error: str | None = None  # set when config enables Drive but init fails
_pending_uploads: list[dict] = []  # {"path": Path, "attempts": int}


def _files_dir() -> Path:
    """Job log output directory from system_config.json."""
    path = config.get_job_files_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_drive_backup() -> tuple["JobDriveBackup" | None, str | None]:
    """Return (JobDriveBackup, None) if enabled and init succeeds.

    Returns (None, None) when the feature is intentionally disabled in config.
    Returns (None, error_message) when enabled in config but initialisation fails.
    """
    try:
        if not config.get_google_drive_enabled():
            return None, None
        from src.google_drive.drive_backup import JobDriveBackup

        return JobDriveBackup(), None
    except Exception as exc:
        msg = str(exc)
        print(f"[Drive] Could not initialise JobDriveBackup: {msg}")
        return None, msg


def _cors_origins() -> list[str]:
    env = os.environ.get("JUBILEE_CORS_ORIGINS", "").strip()
    if env:
        return [o.strip() for o in env.split(",") if o.strip()]
    return config.get_cors_origins()


def _merge_hardware_config(body: HardwareConfig) -> HardwareConfig:
    """Fill omitted connect fields from system_config.json."""
    data = body.model_dump()
    if data.get("machine_address") is None:
        data["machine_address"] = config.get_duet_ip()
    if data.get("scale_port") is None:
        data["scale_port"] = config.get_scale_port()
    if data.get("num_dispensers") is None:
        data["num_dispensers"] = config.get_num_dispensers()
    if data.get("pistons_per_dispenser") is None:
        data["pistons_per_dispenser"] = config.get_pistons_per_dispenser()
    return HardwareConfig(**data)


def _mock_hardware_enabled() -> bool:
    """Use mock hardware when config or env says so (env wins when set)."""
    env = os.environ.get("JUBILEE_MOCK_HARDWARE", "").strip().lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False
    return config.get_mock_hardware()


# =============================================================================
# Pydantic models — endpoint-specific requests
# =============================================================================
    

class UpdateDispenserRequest(BaseModel):
    num_pistons: int = Field(ge=0)


class PowderWell(BaseModel):
    well_id: str = Field(min_length=1)
    target_weight: float = Field(
        gt=0.0, le=5_000.0, description="Target weight in grams"
    )


class HardnessSample(BaseModel):
    tray_index: int = Field(ge=0, le=HARDNESS_TRAY_COUNT - 1)
    sample_index: int = Field(ge=0, le=HARDNESS_TRAY_CAPACITY - 1)
    mode: Literal["shore_a", "shore_a_d", "shore_d"]


class StartPowderJobRequest(BaseModel):
    job_type: Literal["dispensing"] = "dispensing"
    wells: list[PowderWell] = Field(
        min_length=1,
        max_length=24,
        description="At most 24 wells per job (fixed API limit).",
    )


class StartHardnessJobRequest(BaseModel):
    job_type: Literal["hardness"] = "hardness"
    samples: list[HardnessSample] = Field(
        min_length=1,
        max_length=HARDNESS_TRAY_CAPACITY * HARDNESS_TRAY_COUNT,
        description=(
            f"At most {HARDNESS_TRAY_CAPACITY * HARDNESS_TRAY_COUNT} samples per job "
            f"({HARDNESS_TRAY_COUNT} trays × {HARDNESS_TRAY_CAPACITY} slots)."
        ),
    )


# Discriminated union: FastAPI picks the correct model from the job_type field.
JobRequest = Annotated[
    StartPowderJobRequest | StartHardnessJobRequest,
    Body(discriminator="job_type"),
]


# =============================================================================
# WebSocket connection manager
# =============================================================================


class ConnectionManager:
    """Tracks every live browser WebSocket client.

    Maintains the list of active connections and provides broadcast helpers.
    Dead connections (clients that have closed their tab) are detected during
    broadcast and removed automatically.
    """

    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        """Accept a new WebSocket connection and register it.

        Args:
            ws: The WebSocket instance from FastAPI.
        """
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        """Remove a WebSocket from the active list.

        Args:
            ws: The WebSocket instance to remove. No-op if not registered.
        """
        if ws in self.active:
            self.active.remove(ws)

    @property
    def client_count(self) -> int:
        """Number of currently active WebSocket clients."""
        return len(self.active)

    async def broadcast(self, data: dict) -> None:
        """Send a JSON payload to every active client.

        Any client whose send raises an exception is assumed to have
        disconnected and is removed from ``self.active``.

        Args:
            data: JSON-serialisable dict to broadcast.
        """
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

hw: MockHardwareManager | HardwareManager = (
    MockHardwareManager() if _mock_hardware_enabled() else HardwareManager()
)
ws_mgr = ConnectionManager()
progress = JobProgress()


# =============================================================================
# Background telemetry loop  (4 Hz)
# =============================================================================


async def telemetry_loop() -> None:
    """Broadcast a unified telemetry frame to every connected browser at 4 Hz.

    Runs indefinitely as an ``asyncio.Task`` created in the app lifespan.
    Weight is only queried when hardware is connected. The broadcast is skipped
    entirely when no browser tabs are open (``ws_mgr.client_count == 0``).
    """
    while True:
        if ws_mgr.client_count > 0:
            weight = (await hw.get_weight_unstable()) if hw.connected else None
            await ws_mgr.broadcast(
                {
                    "weight": weight,
                    "state": hw.state.value,
                    "connected": hw.connected,
                    "jubilee_ip": hw.jubilee_ip,
                    "job": progress.to_dict(),
                    "dispensers": [d.model_dump() for d in hw.get_dispensers()],
                    "clients": ws_mgr.client_count,
                }
            )
        await asyncio.sleep(0.25)  # 4 Hz


# =============================================================================
# App + lifespan
# =============================================================================


async def drive_upload_retry_loop(backup: "JobDriveBackup") -> None:
    """Periodically retry failed job log uploads until they succeed."""
    interval = config.get_retry_interval_seconds()
    while True:
        await asyncio.sleep(interval)
        if _pending_uploads:
            try:
                _retry_pending_uploads(backup)
            except Exception as exc:
                print(f"[Drive] retry loop error: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _drive_backup, _drive_init_error
    _drive_backup, _drive_init_error = _load_drive_backup()
    tasks = [asyncio.create_task(telemetry_loop())]
    if _drive_backup is not None:
        tasks.append(asyncio.create_task(drive_upload_retry_loop(_drive_backup)))
        print("[Drive] Job log backup enabled.")
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Jubilee Automation API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# REST — hardware lifecycle
# =============================================================================


@app.get("/api/config")
async def get_machine_config():
    """Return machine settings from system_config.json for UI hydration."""
    return {
        "duet_ip": config.get_duet_ip(),
        "scale_port": config.get_scale_port(),
        "num_dispensers": config.get_num_dispensers(),
        "pistons_per_dispenser": config.get_pistons_per_dispenser(),
        "hardness_tray": {
            "rows": HARDNESS_ROWS,
            "cols": HARDNESS_COLS,
            "tray_count": HARDNESS_TRAY_COUNT,
        },
        "google_drive_enabled": config.get_google_drive_enabled(),
        "mock_hardware": _mock_hardware_enabled(),
    }


@app.get("/api/status")
async def get_status():
    """Return a full machine snapshot.

    Returns:
        dict: Connected flag, machine state, Jubilee IP, current job progress,
        dispenser statuses, and active WebSocket client count.
    """
    return {
        "connected": hw.connected,
        "state": hw.state.value,
        "jubilee_ip": hw.jubilee_ip,
        "job": progress.to_dict(),
        "dispensers": [d.model_dump() for d in hw.get_dispensers()],
        "clients": ws_mgr.client_count,
    }


@app.post("/api/hardware/connect", status_code=202)
async def hardware_connect(config: HardwareConfig):
    """Begin hardware connection with the supplied configuration.

    Returns HTTP 202 immediately; the connection runs in the background as an
    ``asyncio.Task``. Monitor the WebSocket ``state`` field for transitions::

        DISCONNECTED → HOMING → IDLE   (success)
        DISCONNECTED → HOMING → ERROR  (failure — check job.error for reason)

    Args:
        config: Hardware configuration (dispensers, pistons, IP, serial port).

    Raises:
        HTTPException: 400 if already connected or a connection is in progress.
    """
    if hw.connected:
        raise HTTPException(status_code=400, detail="Already connected to hardware.")
    if hw.state == MachineState.HOMING:
        raise HTTPException(status_code=400, detail="Connection already in progress.")
    merged = _merge_hardware_config(config)
    asyncio.create_task(_run_connect(merged))
    return {
        "accepted": True,
        "message": "Connection initiated — monitor WebSocket state.",
    }


@app.post("/api/hardware/disconnect", status_code=200)
async def hardware_disconnect():
    """Stop any running job and disconnect from hardware.

    Awaits disconnect completion synchronously (fast — just closes serial/HTTP
    sessions). After this returns, the WebSocket broadcasts ``state=disconnected``.
    """
    if progress.running:
        progress.running = False  # signal job loop to exit cleanly
    await hw.disconnect()
    return {"disconnected": True}


# =============================================================================
# REST — jobs
# =============================================================================


@app.post("/api/job/start", status_code=202)
async def start_job(body: JobRequest):
    """Enqueue a powder-dispensing or hardness-testing job.

    The job type is selected by the ``job_type`` discriminator field in the
    request body. Pydantic validates all field constraints before this function
    is called; invalid payloads return HTTP 422 automatically.

    Args:
        body: A ``StartPowderJobRequest`` or ``StartHardnessJobRequest`` instance,
            selected by the ``job_type`` discriminator.

    Raises:
        HTTPException: 400 if the machine is not in the IDLE state or a job is
            already in progress.
    """
    if hw.state != MachineState.IDLE:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Machine is not idle (current state: {hw.state.value!r}). "
                "Wait for the current operation to finish or resolve the error."
            ),
        )
    if hasattr(hw, "_manager") and hw._manager is None:
        # Catches the race where disconnect() was called while a connect() was
        # still running: connect() can finish after disconnect() and leave state
        # as IDLE with _manager = None.  Force a clean disconnected state so
        # the UI reflects reality before the user retries.
        hw.state = MachineState.DISCONNECTED
        raise HTTPException(
            status_code=400,
            detail=(
                "Hardware is not connected (internal manager is missing). "
                "Please disconnect and reconnect before starting a job."
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
        progress.start_job("dispensing", items, now)
        asyncio.create_task(_run_dispensing(items))
        return {"accepted": True, "job_type": "dispensing", "total": len(items)}

    else:  # hardness
        items = [s.model_dump() for s in body.samples]
        print(f"[JobStart] hardness job: {len(items)} samples: {items}")
        progress.start_job("hardness", items, now)
        asyncio.create_task(_run_hardness(items))
        return {"accepted": True, "job_type": "hardness", "total": len(items)}


@app.post("/api/job/stop", status_code=200)
async def stop_job():
    """Signal the running job to stop after the current well/sample completes.

    The job does not stop immediately — it exits at the next iteration boundary
    when it checks ``progress.running``.

    Raises:
        HTTPException: 400 if no job is currently running.
    """
    if not progress.running:
        raise HTTPException(status_code=400, detail="No job is currently running.")
    progress.running = False
    return {"stopping": True}


@app.post("/api/job/cancel", status_code=200)
async def cancel_job():
    """Graceful cancel: finish the current mold/sample, then stow the tool.

    The job exits at the next iteration boundary (same mechanism as ``stop``).
    On real hardware the manager homes and stows the active tool before
    releasing the IDLE state.

    Raises:
        HTTPException: 400 if no job is currently running.
    """
    if not progress.running:
        raise HTTPException(status_code=400, detail="No job is currently running.")
    progress.running = False
    return {"cancelling": True}


@app.post("/api/job/abort", status_code=200)
async def abort_job():
    """Emergency stop: immediately halt all motion.

    Signals the job loop to exit, then calls ``hw.abort()``, which sends M112
    to the Duet controller on real hardware. Sets machine state to ERROR so the
    job ``finally`` block cannot silently reset it back to IDLE. Hardware must
    be fully reconnected before starting a new job.
    """
    progress.running = False
    await hw.abort()
    return {"aborted": True}


@app.post("/api/job/clear_jam", status_code=200)
async def clear_jam():
    """Resume a dispensing job that is paused due to a powder jam.

    The dispensing loop blocks on a threading event when it detects that
    powder flow has stalled.  This endpoint clears the jam flag in
    ``JobProgress`` (so the UI dialog is dismissed on the next telemetry
    frame) and then calls ``hw.clear_jam()`` to set the threading event,
    unblocking the dispensing loop.

    Returns 400 if no jam is currently active.
    """
    if not progress.jam_detected:
        raise HTTPException(status_code=400, detail="No jam currently active")
    progress.clear_jam()
    hw.clear_jam()
    return {"cleared": True}


@app.get("/api/job/log")
async def get_job_log():
    """Return the most recent job log in the normalised live-progress format.

    Priority order:

    1. If a job ran in this server session (``progress`` has data), synthesise
       from in-memory state so the home screen updates in real time.
    2. Otherwise read the most recent file from the configured job files dir - the path taken
       after a server restart when in-memory state is lost.

    Returns:
        dict: ``{"log": <normalised job dict>}`` or ``{"log": null}`` when
        neither source has data.
    """
    if progress.job_type is not None:
        return {"log": _build_progress_log()}

    files = sorted(_files_dir().glob("*.json"), reverse=True)
    if not files:
        return {"log": None}
    try:
        raw = json.loads(files[0].read_text())
        return {"log": _normalize_file_log(raw)}
    except Exception:
        return {"log": None}


def _build_progress_log() -> dict:
    """Synthesise a normalised job log dict from the current in-memory ``JobProgress``.

    Returns:
        dict: Job log in the normalised live-progress shape understood by the
        frontend store and HomeScreen.
    """
    items_with_status = []
    for i, item in enumerate(progress.items):
        if "well_id" in item:
            item_id = item.get("well_id")
        else:
            item_id = f"{item['tray_index']}:{item['sample_index']}"
        if item.get("status"):
            status = item.get("status")
        elif i < progress.completed:
            status = "complete"
        elif item_id == progress.current_item:
            status = "active"
        else:
            status = "incomplete"
        items_with_status.append({**item, "status": status})

    date_str = progress.started_at[:10] if progress.started_at else None
    progress_completed, progress_total = progress._compute_pass_progress()

    return {
        "job_type": progress.job_type,
        "started_at": progress.started_at,
        "date": date_str,
        "status": "running" if progress.running else "complete",
        "completed": progress.completed,
        "total": progress.total,
        "progress_completed": progress_completed,
        "progress_total": progress_total,
        "progress_pct": progress._compute_progress_pct(),
        "error": progress.error,
        "items": items_with_status,
    }


def _all_items_terminal(items: list[dict]) -> bool:
    """Return True when every item reached a terminal status."""
    if not items:
        return False
    return all(item.get("status") in {"complete", "error"} for item in items)


def _normalize_file_log(raw: dict) -> dict:
    """Convert a persisted job JSON file to the normalised live-progress shape.

    Maps the on-disk file format to the shape understood by the frontend store
    and HomeScreen:

    +--------------------------+---------------------------+
    | File field               | Normalised field          |
    +==========================+===========================+
    | metadata.job_type        | job_type                  |
    | metadata.date            | date                      |
    | metadata.outcome         | status                    |
    | state.molds / state.samples | items                 |
    +--------------------------+---------------------------+

    Args:
        raw: Parsed JSON content of a job log file.

    Returns:
        dict: Normalised job log dict compatible with the frontend store.
    """
    meta = raw.get("metadata", {})
    state = raw.get("state", {})

    job_type = meta.get("job_type", "")

    items = state.get("molds") or state.get("samples") or []
    completed = sum(1 for it in items if it.get("status") == "complete")

    error = raw.get("error")
    if error is None:
        error = meta.get("error")

    return {
        "job_type": job_type,
        "started_at": None,
        "date": meta.get("date"),
        "status": meta.get("outcome", "unknown"),
        "completed": completed,
        "total": len(items),
        "error": error,
        "items": items,
    }


# =============================================================================
# REST — dispensers
# =============================================================================


@app.get("/api/dispensers")
async def get_dispensers():
    """Return the current status of all configured piston dispensers.

    Returns:
        dict: ``{"dispensers": [{"index": int, "pistons_remaining": int}, ...]}``
    """
    return {"dispensers": [d.model_dump() for d in hw.get_dispensers()]}


@app.put("/api/dispensers/{index}", status_code=200)
async def update_dispenser(index: int, body: UpdateDispenserRequest):
    """Update the remaining piston count for a specific dispenser.

    Called after the user manually reloads a dispenser tray.

    Args:
        index: Zero-based dispenser index.
        body: New piston count (``num_pistons >= 0``).

    Raises:
        HTTPException: 400 if the index is out of range or hardware is not connected.
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
    """Return metadata for all job log JSON files in the files directory.

    Files are returned newest-first by filename, which encodes a sequential ID.

    Returns:
        list[dict]: Each entry has ``name``, ``path``, ``size``, ``modified``
        (ISO-8601 UTC), and ``type`` fields matching the shape expected by the
        DataScreen.
    """
    entries = []
    for f in sorted(_files_dir().glob("*.json"), reverse=True):
        stat = f.stat()
        entries.append(
            {
                "name": f.name,
                "path": f.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                "type": "file",
            }
        )
    return entries


@app.get("/api/files/{filename}")
async def get_job_file(filename: str):
    """Return the full JSON content of a single job log file.

    Args:
        filename: Exact filename including extension, e.g.
            ``"0001_2026-03-31_dispensing_5.json"``. Only ``.json`` files are
            served.

    Returns:
        dict: Parsed JSON content of the log file.

    Raises:
        HTTPException: 404 if the file does not exist or has the wrong extension.
        HTTPException: 500 if the file cannot be read or parsed.
    """
    path = _files_dir() / filename
    if not path.exists() or path.suffix != ".json":
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read file: {exc}")


# =============================================================================
# REST — Google Drive job log backup
# =============================================================================


@app.get("/api/drive/status")
async def get_drive_status():
    """Return Google Drive backup status for the Settings UI.

    Returns:
        dict: ``enabled``, ``folder_configured``, ``last_upload``, ``last_error``,
        ``pending_uploads``.
    """
    if _drive_backup is None:
        return {
            "enabled": _drive_init_error is not None,
            "folder_configured": False,
            "last_upload": None,
            "last_error": _drive_init_error,
            "pending_uploads": len(_pending_uploads),
        }
    return {
        "enabled": True,
        "folder_configured": _drive_backup.folder_configured,
        "last_upload": _drive_backup.last_upload,
        "last_error": _drive_backup.last_error,
        "pending_uploads": len(_pending_uploads),
    }


# =============================================================================
# Background task helpers
# =============================================================================


def _make_job_log(job_type: str, items: list[dict]):
    """Instantiate a ``JobLog`` for the current job.

    In mock mode the manager reference is ``None``; in real mode the underlying
    ``JubileeManager`` is passed so the log can pull actual weight data from it.

    Args:
        job_type: ``"dispensing"`` or ``"hardness"``.
        items: Ordered list of item dicts from the job request (wells or samples).

    Returns:
        JobLog | None: A ``JobLog`` instance, or ``None`` if the import fails.
    """
    try:
        from src.JobLog import JobLog

        manager_ref = getattr(hw, "_manager", None)
        return JobLog(job_type=job_type, items=items, manager=manager_ref)
    except Exception as exc:
        print(f"[JobLog] Could not create job log: {exc}")
        return None


def _maybe_upload_to_drive(log_path: Path) -> None:
    """Upload the finished job log to Drive, queuing for retry on failure.

    Never raises — job completion must not be blocked by a network issue.
    """
    if _drive_backup is None:
        return
    try:
        _drive_backup.upload_result(log_path)
    except Exception as exc:
        print(f"[Drive] Upload failed, queuing for retry: {exc}")
        _pending_uploads.append({"path": log_path, "attempts": 1})
        _drive_backup.record_error(str(exc))


def _retry_pending_uploads(backup: "JobDriveBackup") -> None:
    """Upload any previously-failed job logs."""
    for item in list(_pending_uploads):
        try:
            backup.upload_result(item["path"])
            _pending_uploads.remove(item)
            print(f"[Drive] Retry upload succeeded: {item['path'].name}")
        except Exception as exc:
            item["attempts"] += 1
            backup.record_error(str(exc))
            print(f"[Drive] Retry upload failed (attempt {item['attempts']}): {exc}")


async def _run_connect(config: HardwareConfig) -> None:
    """Run hardware connection in the background.

    Errors are recorded in ``progress.error``; the hardware state is already
    set to ERROR inside each manager's ``connect()`` implementation.

    Args:
        config: Hardware configuration forwarded to ``hw.connect()``.
    """
    try:
        await hw.connect(config)
    except BaseException as exc:
        traceback.print_exc()
        progress.error = f"Connection failed: {exc}"
        # state is already set to ERROR inside each manager's connect()


async def _run_dispensing(items: list[dict]) -> None:
    """Execute a dispensing job in the background and finalise the log on completion.

    Args:
        items: Ordered list of well dicts (``well_id``, ``target_weight``).
    """
    job_log = _make_job_log("dispensing", items)
    outcome = "cancelled"
    try:
        await hw.run_dispensing_job(items, progress, job_log)
        if progress.completed == progress.total or _all_items_terminal(progress.items):
            outcome = "successful"
        elif hw.state == MachineState.ERROR:
            outcome = "aborted"
    except Exception as exc:
        traceback.print_exc()
        progress.error = str(exc)
        hw.state = MachineState.ERROR
        outcome = "aborted"
    finally:
        progress.running = False
        if job_log is not None:
            try:
                log_path = job_log.finalize(outcome)
                _maybe_upload_to_drive(log_path)
            except Exception as exc:
                print(f"[JobLog] Failed to write log: {exc}")


async def _run_hardness(items: list[dict]) -> None:
    """Execute a hardness testing job in the background and finalise the log on completion.

    Args:
        items: Ordered list of sample dicts (``tray_index``, ``sample_index``, ``mode``).
    """
    job_log = _make_job_log("hardness", items)
    outcome = "cancelled"
    try:
        await hw.run_hardness_job(items, progress, job_log)
        if progress.completed == progress.total or _all_items_terminal(progress.items):
            outcome = "successful"
        elif hw.state == MachineState.ERROR:
            outcome = "aborted"
    except Exception as exc:
        traceback.print_exc()
        progress.error = str(exc)
        hw.state = MachineState.ERROR
        outcome = "aborted"
        print(f"[HardnessJob] Exception: {exc!r}")
    finally:
        progress.running = False
        if job_log is not None:
            try:
                log_path = job_log.finalize(outcome)
                _maybe_upload_to_drive(log_path)
            except Exception as exc:
                print(f"[JobLog] Failed to write log: {exc}")


# =============================================================================
# WebSocket endpoint
# =============================================================================


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """Register a browser client and keep its connection alive.

    The ``telemetry_loop`` pushes 4 Hz frames to all registered clients.
    This coroutine discards any messages sent by the client (the protocol is
    server-push only) and deregisters the client on disconnect.

    Args:
        ws: The incoming WebSocket connection from FastAPI.
    """
    await ws_mgr.connect(ws)
    try:
        while True:
            await ws.receive_text()  # discard client-sent messages
    except WebSocketDisconnect:
        ws_mgr.disconnect(ws)


# =============================================================================
# Static file serving (production build)
# =============================================================================
# When the React app has been built (`npm run build` in frontend/), serve it
# directly from uvicorn so no separate Vite dev server is needed.  The SPA
# catch-all below ensures deep-link routes (e.g. /settings) return index.html
# instead of 404 when the page is refreshed.
#
# This block is intentionally placed after every API and WebSocket route so
# that /api/* and /ws are never shadowed by the static mount.

_images_dir = _files_dir() / "images"
_images_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/api/files/images",
    StaticFiles(directory=str(_images_dir), html=False),
    name="sample_images",
)

_DIST_DIR = Path(__file__).parent / "dist"

if _DIST_DIR.exists():

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> FileResponse:
        candidate = _DIST_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST_DIR / "index.html")

    app.mount("/", StaticFiles(directory=_DIST_DIR, html=True), name="static")
