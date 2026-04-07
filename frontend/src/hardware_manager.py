"""
Hardware managers for the Jubilee Automation server.

MockHardwareManager
-------------------
Standalone simulation of the Jubilee hardware for UI development.
No physical hardware required.  Scale readings use a slow sine drift plus
Gaussian noise to mimic the real A&D FX-120i serial scale output.  Job
execution advances JobProgress in-place via async sleep to produce realistic
per-well timing visible through the telemetry WebSocket.

HardwareManager
---------------
Production wrapper around the real JubileeManager.  All blocking serial /
network calls are offloaded to asyncio.to_thread() so the uvicorn event loop
is never stalled.

JubileeManager is imported lazily inside connect() so the server starts
cleanly on developer machines that lack the science_jubilee package.

Both classes expose an identical public API — switch between them by setting
MOCK_HARDWARE in server.py.
"""

import asyncio
import math
import random
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path for the lazy src.JubileeManager import.
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# models.py is a sibling in the same directory; it is already importable by
# the time this module is loaded because server.py adds frontend/src/ to
# sys.path before importing hardware_manager.
from models import DispenserStatus, HardwareConfig, JobProgress, MachineState


# =============================================================================
# MockHardwareManager
# =============================================================================

class MockHardwareManager:

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

    async def abort(self) -> None:
        """Simulate an emergency stop.  State goes to ERROR immediately."""
        self.state = MachineState.ERROR


# =============================================================================
# HardwareManager
# =============================================================================

class HardwareManager:

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
        pass # TODO: Remove when hardness testing is implemented
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
