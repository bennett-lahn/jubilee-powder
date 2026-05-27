"""
Hardware managers for the Jubilee Automation server.

Both classes below expose an identical public API. Switch between them by
setting ``MOCK_HARDWARE`` in ``server.py``; no other code needs to change.

MockHardwareManager:
    Standalone simulation of the Jubilee hardware for UI development. No
    physical hardware required. Scale readings use a slow sine drift plus
    Gaussian noise to mimic the real A&D FX-120i serial scale output. Job
    execution advances ``JobProgress`` in-place via ``asyncio.sleep()`` to
    produce realistic per-well timing visible through the telemetry WebSocket.

HardwareManager:
    Production wrapper around the real ``JubileeManager``. All blocking serial
    or network calls are offloaded to ``asyncio.to_thread()`` so the uvicorn
    event loop is never stalled. ``JubileeManager`` is imported lazily inside
    ``connect()`` so the server starts cleanly on developer machines that lack
    the ``science_jubilee`` package.
"""

import asyncio
import math
import random
import sys
import time
import traceback
from pathlib import Path

# Ensure project root is on sys.path for the lazy src.JubileeManager import.
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# models.py is a sibling in the same directory; it is already importable by
# the time this module is loaded because server.py adds frontend/src/ to
# sys.path before importing hardware_manager.
from models import DispenserStatus, HardwareConfig, JobProgress, MachineState


def _sample_display_id(sample: dict) -> str:
    """Build a stable sample identifier for UI progress tracking."""
    t_idx = sample.get('tray_index', 'UnknownTray')
    s_id = sample.get('sample_id', 'UnknownID')
    
    return f"{t_idx}:{s_id}"


def _safe_float(value):
    """Convert a measurement to float when possible."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _hardness_passes(sample_mode: str) -> list[str]:
    """Return pass sequence required for the configured hardness mode."""
    if sample_mode == "shore_a":
        return ["shore_a"]
    if sample_mode == "shore_d":
        return ["shore_d"]
    if sample_mode == "shore_a_d":
        return ["shore_a", "shore_d"]
    return []


def _apply_hardness_progress_update(
    progress: JobProgress,
    index: int,
    pass_mode: str,
    measured_result: float | None,
    sample_error: str | None,
) -> None:
    """Apply one pass result to a sample item in JobProgress."""
    item = progress.items[index]
    configured_mode = item.get("mode")
    if sample_error:
        progress.mark_item_error(
            index,
            sample_error=sample_error,
            result=item.get("result"),
            result_shore_a=item.get("result_shore_a"),
            result_shore_d=item.get("result_shore_d"),
        )
        return

    if configured_mode == "shore_a_d":
        updates = {
            "result": None,
            "sample_error": None,
        }
        if pass_mode == "shore_a":
            updates["result_shore_a"] = measured_result
        elif pass_mode == "shore_d":
            updates["result_shore_d"] = measured_result

        item.update(updates)
        has_a = item.get("result_shore_a") is not None
        has_d = item.get("result_shore_d") is not None
        if has_a and has_d:
            progress.mark_item_complete(
                index,
                result=None,
                result_shore_a=item.get("result_shore_a"),
                result_shore_d=item.get("result_shore_d"),
                sample_error=None,
            )
        else:
            item["status"] = "pending"
        return

    progress.mark_item_complete(
        index,
        result=measured_result,
        result_shore_a=measured_result if pass_mode == "shore_a" else None,
        result_shore_d=measured_result if pass_mode == "shore_d" else None,
        sample_error=None,
    )


# =============================================================================
# MockHardwareManager
# =============================================================================

class MockHardwareManager:
    """Simulated hardware manager for UI development without physical hardware.

    Scale readings use a sine-wave drift plus Gaussian noise to approximate
    the output of the A&D FX-120i scale. Job loops advance ``JobProgress``
    via ``asyncio.sleep()`` with per-well delays that match real hardware
    timing, so the WebSocket telemetry looks realistic during development.
    """

    def __init__(self) -> None:
        self.state:   MachineState  = MachineState.DISCONNECTED
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
        """Simulate a hardware connection and homing sequence.

        Transitions ``state`` from ``DISCONNECTED`` → ``HOMING`` → ``IDLE``
        with a 2-second sleep to mimic the real homing sequence.

        Args:
            config: Hardware configuration (dispensers, pistons, addresses).
        """
        self._config = config
        self._dispensers = [
            DispenserStatus(index=i, pistons_remaining=config.pistons_per_dispenser)
            for i in range(config.num_dispensers)
        ]
        self.state = MachineState.HOMING
        await asyncio.sleep(2.0)          # simulate homing sequence
        self.state = MachineState.IDLE

    async def disconnect(self) -> None:
        """Clear dispenser state and set machine state to DISCONNECTED."""
        self._dispensers = []
        self.state = MachineState.DISCONNECTED

    # ── Scale reads ───────────────────────────────────────────────────────────

    async def get_weight_unstable(self) -> float:
        """Return a simulated live scale reading with drift and noise.

        Returns:
            float: Simulated weight in grams (sine drift + Gaussian noise),
            always >= 0.
        """
        t     = time.monotonic() - self._t0
        drift = math.sin(t * 0.15) * 1.8
        noise = random.gauss(0.0, 0.04)
        return round(max(0.0, self._scale_base + drift + noise), 3)

    async def get_weight_stable(self) -> float:
        """Return a simulated stable scale reading with minimal noise.

        Returns:
            float: Simulated stable weight in grams (Gaussian noise only).
        """
        return round(self._scale_base + random.gauss(0.0, 0.008), 3)

    # ── Dispenser management ──────────────────────────────────────────────────

    def get_dispensers(self) -> list[DispenserStatus]:
        """Return a snapshot of all dispenser statuses.

        Returns:
            list[DispenserStatus]: Copy of the internal dispenser list.
        """
        return list(self._dispensers)

    def update_dispenser_pistons(self, index: int, num_pistons: int) -> bool:
        """Update the remaining piston count for a single dispenser.

        Args:
            index: Zero-based dispenser index.
            num_pistons: New piston count.

        Returns:
            bool: ``True`` on success, ``False`` if the index is out of range.
        """
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
        """Simulate a powder dispensing job.

        Iterates over ``wells`` sequentially, sleeping 2 s per well to mimic
        real hardware timing. Updates ``progress`` in-place and optionally
        records simulated actual weights in ``job_log``.

        Args:
            wells: Ordered list of well dicts with ``well_id`` and
                ``target_weight`` keys.
            progress: Shared ``JobProgress`` instance updated as wells complete.
            job_log: Optional ``JobLog`` instance for recording results.
        """
        self.state = MachineState.RUNNING
        try:
            for i, well in enumerate(wells):
                if not progress.running:
                    break
                progress.mark_item_active(i)
                await asyncio.sleep(2.0)
                simulated_weight = None
                if job_log is not None:
                    simulated_weight = well["target_weight"] * (
                        1 + random.gauss(0, 0.008)
                    )
                    job_log.update_well(
                        well["well_id"], actual_weight=round(simulated_weight, 3)
                    )
                progress.mark_item_complete(
                    i,
                    actual_weight=round(simulated_weight, 3)
                    if simulated_weight is not None
                    else None,
                )
        finally:
            # Do not overwrite ERROR set by an abort call
            if self.state == MachineState.RUNNING:
                self.state = MachineState.IDLE

    async def run_hardness_job(
        self, samples: list[dict], progress: JobProgress, job_log=None
    ) -> None:
        """Simulate a hardness testing job.

        Iterates over ``samples`` sequentially, sleeping 1.5 s per sample.
        Simulated hardness results are drawn from a uniform distribution.

        Args:
            samples: Ordered list of sample dicts with ``tray_index``,
                ``sample_id``, and ``mode`` keys.
            progress: Shared ``JobProgress`` instance updated as samples complete.
            job_log: Optional ``JobLog`` instance for recording results.
        """
        self.state = MachineState.RUNNING
        try:
            for pass_mode in ("shore_a", "shore_d"):
                for i, sample in enumerate(samples):
                    if not progress.running:
                        break
                    required_passes = _hardness_passes(sample.get("mode", "none"))
                    if pass_mode not in required_passes:
                        continue
                    if progress.items[i].get("status") == "error":
                        continue

                    progress.mark_item_active(i)
                    await asyncio.sleep(1.5)
                    simulated_result = round(random.uniform(30.0, 80.0), 1)
                    if job_log is not None:
                        job_log.update_sample(
                            sample["sample_id"],
                            tray_index=sample["tray_index"],
                            result=simulated_result,
                            measurement_mode=pass_mode,
                        )
                    _apply_hardness_progress_update(
                        progress,
                        i,
                        pass_mode,
                        measured_result=simulated_result,
                        sample_error=None,
                    )
        finally:
            if self.state == MachineState.RUNNING:
                self.state = MachineState.IDLE

    async def abort(self) -> None:
        """Simulate an emergency stop. Transitions state to ERROR immediately."""
        self.state = MachineState.ERROR


# =============================================================================
# HardwareManager
# =============================================================================

class HardwareManager:
    """Production wrapper around ``JubileeManager`` for real hardware.

    All blocking serial or network calls are offloaded via ``asyncio.to_thread()``
    so the uvicorn event loop is never stalled. ``JubileeManager`` is imported
    lazily inside ``connect()`` so the server starts cleanly on machines that
    lack the ``science_jubilee`` package.
    """

    def __init__(self) -> None:
        self.state:    MachineState   = MachineState.DISCONNECTED
        self._config:  HardwareConfig = HardwareConfig()
        self._manager                 = None   # JubileeManager instance

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self.state != MachineState.DISCONNECTED

    @property
    def jubilee_ip(self) -> str:
        return self._config.machine_address or "http://192.168.1.2:8080"

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
            traceback.print_exc()
            self.state    = MachineState.ERROR
            self._manager = None
            raise

    async def disconnect(self) -> None:
        """Disconnect from hardware and reset manager state."""
        if self._manager is not None:
            await asyncio.to_thread(self._manager.disconnect)
            self._manager = None
        self.state = MachineState.DISCONNECTED

    # ── Scale reads ───────────────────────────────────────────────────────────

    async def get_weight_unstable(self) -> float:
        """Read the current (unstable) scale weight without waiting for stability.

        Returns:
            float: Scale reading in grams, or ``0.0`` if hardware is not connected.
        """
        if self._manager and self._manager.connected:
            return await asyncio.to_thread(self._manager.get_weight_unstable)
        return 0.0

    async def get_weight_stable(self) -> float:
        """Read the scale weight after waiting for a stable reading.

        Returns:
            float: Stable scale reading in grams, or ``0.0`` if not connected.
        """
        if self._manager and self._manager.connected:
            return await asyncio.to_thread(self._manager.get_weight_stable)
        return 0.0

    # ── Dispenser management ──────────────────────────────────────────────────

    def get_dispensers(self) -> list[DispenserStatus]:
        """Return the current status of all connected piston dispensers.

        Returns:
            list[DispenserStatus]: Per-dispenser piston counts, or an empty list
            if hardware is not connected.
        """
        if self._manager and self._manager.connected:
            return [
                DispenserStatus(index=d.index, pistons_remaining=d.num_pistons)
                for d in self._manager.piston_dispensers
            ]
        return []

    def update_dispenser_pistons(self, index: int, num_pistons: int) -> bool:
        """Update the remaining piston count for a single dispenser.

        Args:
            index: Zero-based dispenser index.
            num_pistons: New piston count.

        Returns:
            bool: ``True`` on success, ``False`` if hardware is not connected or
            the index is out of range.
        """
        if not (self._manager and self._manager.connected):
            return False
        return self._manager.set_dispenser_pistons(index, num_pistons)

    # ── Job execution ─────────────────────────────────────────────────────────

    async def run_dispensing_job(
        self, wells: list[dict], progress: JobProgress, job_log=None
    ) -> None:
        """Execute a real powder dispensing job via ``JubileeManager``.

        Iterates over ``wells`` sequentially, calling
        ``JubileeManager.dispense_to_well()`` in a thread for each well.
        Updates ``progress`` in-place after each well completes.

        Args:
            wells: Ordered list of well dicts with ``well_id`` and
                ``target_weight`` keys.
            progress: Shared ``JobProgress`` instance updated as wells complete.
            job_log: Optional ``JobLog`` instance attached to the manager for
                recording actual weights.

        Raises:
            RuntimeError: If ``dispense_to_well()`` returns ``False`` for any well.
        """
        self.state = MachineState.RUNNING
        if job_log is not None and self._manager is not None:
            self._manager.active_job_log = job_log
        try:
            for i, well in enumerate(wells):
                if not progress.running:
                    break
                progress.mark_item_active(i)
                success = await asyncio.to_thread(
                    self._manager.dispense_to_well,
                    well["well_id"],
                    well["target_weight"],
                )
                if not success:
                    raise RuntimeError(
                        f"Dispense failed for well {well['well_id']!r}"
                    )
                progress.mark_item_complete(
                    i,
                    actual_weight=_safe_float(getattr(self._manager, "last_dispense_weight", None)),
                )
        finally:
            if self._manager is not None:
                self._manager.active_job_log = None
            if self.state == MachineState.RUNNING:
                self.state = MachineState.IDLE

    async def run_hardness_job(
        self, samples: list[dict], progress: JobProgress, job_log=None
    ) -> None:
        """Execute a hardness testing job via ``JubileeManager``.

        Args:
            samples: Ordered list of sample dicts with ``tray_index``,
                ``sample_id``, and ``mode`` keys.
            progress: Shared ``JobProgress`` instance updated as samples complete.
            job_log: Optional ``JobLog`` instance for recording results.
        """
        self.state = MachineState.RUNNING
        if job_log is not None and self._manager is not None:
            self._manager.active_job_log = job_log
        try:
            for pass_mode in ("shore_a", "shore_d"):
                for i, sample in enumerate(samples):
                    if not progress.running:
                        break
                    required_passes = _hardness_passes(sample.get("mode", "none"))
                    if pass_mode not in required_passes:
                        continue
                    if progress.items[i].get("status") == "error":
                        continue

                    progress.mark_item_active(i)
                    success = await asyncio.to_thread(
                        self._manager.test_sample,
                        sample["tray_index"],
                        sample["sample_id"],
                        pass_mode,
                    )
                    if not success:
                        raise RuntimeError(
                            "Hardness test failed for "
                            f"tray {sample['tray_index']} sample {sample['sample_id']!r}"
                        )

                    measured_result = _safe_float(
                        getattr(self._manager, "last_hardness_result", None)
                    )
                    sample_error = getattr(self._manager, "last_hardness_error", None)
                    if measured_result is None:
                        sample_error = sample_error or "OCR did not return a numeric hardness value."

                    _apply_hardness_progress_update(
                        progress,
                        i,
                        pass_mode,
                        measured_result=measured_result,
                        sample_error=sample_error,
                    )
        finally:
            if self._manager is not None:
                self._manager.active_job_log = None
            if self.state == MachineState.RUNNING:
                self.state = MachineState.IDLE

    async def abort(self) -> None:
        """
        Send M112 to the Duet controller and transition to ERROR state.

        Delegates to JubileeManager.abort(), which bypasses the
        MotionPlatformStateMachine intentionally — see that method's docstring
        for more information about invariant preservation.  The state is set to ERROR
        here so the job finally-block cannot silently reset it back to IDLE.
        """
        if self._manager is not None:
            await asyncio.to_thread(self._manager.abort)   # Bypass state machine
        self.state = MachineState.ERROR                    # Prevents job finally-block reset
